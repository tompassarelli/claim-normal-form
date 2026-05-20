#lang racket

(require "cnf.rkt")

(provide var atom dl-rule
         ?
         define-rule
         query
         run-query
         show-results
         reset-rules!
         supersedes-pred-id
         set-supersedes-pred!
         current-claims-where
         materialize!
         invalidate-views!
         setup-rule-predicates!
         define-rule!/claims
         supersede-rule!
         list-rule-entities
         rule-head-rel-pred
         rule-source-pred)

;; Datalog over CNF — semi-naive evaluation with index-aware joins.
;;
;; Two-tier relation model:
;;   EDB (base): claim, triple, current-claim, current-triple, value, object
;;     — dispatched to the live claim store via hash indexes
;;   IDB (derived): everything else
;;     — accumulated during fixpoint in set-based hash tables
;;
;; Semi-naive evaluation:
;;   1. EDB-only rules fire once (Phase 1). Skipped in all iterations.
;;   2. IDB rules iterate with delta restriction: on each iteration,
;;      at least one IDB body atom uses only NEW facts from the
;;      previous iteration. Avoids re-deriving known tuples.
;;   3. Fixpoint when no new facts are derived.

(struct var (name) #:transparent)
(struct atom (rel args) #:transparent)
(struct dl-rule (head body) #:transparent)

(define-syntax-rule (? name)
  (var 'name))

;; --- Rules and supersession state ---

(define (supersedes-pred-id)
  (ctx-ref 'supersedes-pred-id #f))

(define (set-supersedes-pred! id)
  (ctx-set! 'supersedes-pred-id id))

(define (current-claims-where #:l [l #f] #:p [p #f] #:r [r #f])
  (define all (claims-where #:l l #:p p #:r r))
  (filter (lambda (c) (not (superseded? (first c)))) all))

(define (reset-rules!)
  (ctx-set! 'rules '())
  (ctx-set! 'matview-valid? #f)
  (define ents (ctx-ref 'rule-entities #f))
  (when (hash? ents) (hash-clear! ents)))

;; --- Syntax ---

(define-syntax parse-atom
  (syntax-rules ()
    [(_ (rel arg ...))
     (atom 'rel (list arg ...))]))

(define-syntax-rule (define-rule (head-rel head-arg ...) body ...)
  (ctx-set! 'rules
    (cons (dl-rule (atom 'head-rel (list head-arg ...))
                   (list (parse-atom body) ...))
          (ctx-ref 'rules '()))))

(define-syntax query
  (syntax-rules ()
    [(_ body-clause ...)
     (run-query (list (parse-atom body-clause) ...))]))

;; --- Literal resolution ---

(define (resolve-literal v)
  (cond
    [(var? v) v]
    [(object-exists? v) v]
    [else
     (define vid (value-id v))
     (or vid v)]))

(define (resolve-atom-literals a)
  (atom (atom-rel a)
        (map resolve-literal (atom-args a))))

;; --- Pattern matching ---

(define (match-tuple pattern tuple subst)
  (cond
    [(and (null? pattern) (null? tuple)) subst]
    [(or (null? pattern) (null? tuple)) #f]
    [else
     (define term (car pattern))
     (define val (car tuple))
     (define s
       (cond
         [(var? term)
          (define bound (hash-ref subst (var-name term) #f))
          (cond
            [bound (if (equal? bound val) subst #f)]
            [else (hash-set subst (var-name term) val)])]
         [(equal? term val) subst]
         [else #f]))
     (and s (match-tuple (cdr pattern) (cdr tuple) s))]))

;; --- Relation classification ---

(define edb-relations '(claim triple current-claim current-triple value object))

(define (edb-rel? rel)
  (memq rel edb-relations))

(define (idb-body-positions body-atoms)
  (for/list ([a (in-list body-atoms)]
             [i (in-naturals)]
             #:when (not (edb-rel? (atom-rel a))))
    i))

;; --- Index-aware EDB evaluation ---
;;
;; claims-where returns rows as (cid p l r).
;; Base relation tuple layouts:
;;   triple:         (L P R)    = (row[2] row[1] row[3])
;;   claim:          (Id L P R) = (row[0] row[2] row[1] row[3])

(define (resolve-arg arg subst)
  (if (var? arg)
      (hash-ref subst (var-name arg) arg)
      arg))

(define (bound? v) (not (var? v)))

(define (row->triple c)
  (list (list-ref c 2) (list-ref c 1) (list-ref c 3)))

(define (row->claim-tuple c)
  (list (list-ref c 0) (list-ref c 2) (list-ref c 1) (list-ref c 3)))

(define (eval-triple-base args resolved subst use-current?)
  (define l (and (bound? (list-ref resolved 0)) (list-ref resolved 0)))
  (define p (and (bound? (list-ref resolved 1)) (list-ref resolved 1)))
  (define r (and (bound? (list-ref resolved 2)) (list-ref resolved 2)))
  (define claims
    (if use-current?
        (current-claims-where #:l l #:p p #:r r)
        (claims-where #:l l #:p p #:r r)))
  (filter-map
   (lambda (c) (match-tuple args (row->triple c) subst))
   claims))

(define (eval-claim-base args resolved subst use-current?)
  (define cid-val (and (bound? (list-ref resolved 0)) (list-ref resolved 0)))
  (cond
    [cid-val
     (define fields (get-claim cid-val))
     (if (and fields (or (not use-current?) (not (superseded? cid-val))))
         (filter-map
          (lambda (t) (match-tuple args t subst))
          (list (list cid-val (first fields) (second fields) (third fields))))
         '())]
    [else
     (define l (and (bound? (list-ref resolved 1)) (list-ref resolved 1)))
     (define p (and (bound? (list-ref resolved 2)) (list-ref resolved 2)))
     (define r (and (bound? (list-ref resolved 3)) (list-ref resolved 3)))
     (define claims
       (if use-current?
           (current-claims-where #:l l #:p p #:r r)
           (claims-where #:l l #:p p #:r r)))
     (filter-map
      (lambda (c) (match-tuple args (row->claim-tuple c) subst))
      claims)]))

(define (eval-value-base args resolved subst)
  (define id-val (and (bound? (list-ref resolved 0)) (list-ref resolved 0)))
  (define lit-val (and (bound? (list-ref resolved 1)) (list-ref resolved 1)))
  (cond
    [id-val
     (if (value-object? id-val)
         (filter-map
          (lambda (t) (match-tuple args t subst))
          (list (list id-val (resolve-value id-val))))
         '())]
    [lit-val
     (define vid (value-id lit-val))
     (if vid
         (filter-map
          (lambda (t) (match-tuple args t subst))
          (list (list vid lit-val)))
         '())]
    [else
     (filter-map
      (lambda (t) (match-tuple args t subst))
      (for/list ([id (all-objects)] #:when (value-object? id))
        (list id (resolve-value id))))]))

(define (eval-object-base args resolved subst)
  (define id-val (and (bound? (list-ref resolved 0)) (list-ref resolved 0)))
  (cond
    [id-val
     (if (object-exists? id-val)
         (list subst)
         '())]
    [else
     (filter-map
      (lambda (t) (match-tuple args t subst))
      (for/list ([id (all-objects)]) (list id)))]))

(define (match-atom-edb a subst)
  (define args (atom-args a))
  (define resolved (map (lambda (x) (resolve-arg x subst)) args))
  (case (atom-rel a)
    [(current-triple) (eval-triple-base args resolved subst #t)]
    [(triple)         (eval-triple-base args resolved subst #f)]
    [(current-claim)  (eval-claim-base args resolved subst #t)]
    [(claim)          (eval-claim-base args resolved subst #f)]
    [(value)          (eval-value-base args resolved subst)]
    [(object)         (eval-object-base args resolved subst)]))

;; --- Set-based IDB storage ---

(define (db-add! db rel tuple)
  (define existing (hash-ref db rel (set)))
  (cond
    [(set-member? existing tuple) #f]
    [else
     (hash-set! db rel (set-add existing tuple))
     #t]))

(define (db-tuples db rel)
  (set->list (hash-ref db rel (set))))

(define (db-empty? db)
  (for/and ([(rel tuples) (in-hash db)])
    (set-empty? tuples)))

;; --- Atom matching (query-time, list-based db) ---

(define (match-atom db a subst)
  (define rel (atom-rel a))
  (cond
    [(edb-rel? rel) (match-atom-edb a subst)]
    [else
     (define tuples (hash-ref db rel '()))
     (filter-map (lambda (t) (match-tuple (atom-args a) t subst)) tuples)]))

;; --- Atom matching (fixpoint-time, set-based db) ---

(define (match-atom-idb db a subst)
  (define tuples (db-tuples db (atom-rel a)))
  (filter-map (lambda (t) (match-tuple (atom-args a) t subst)) tuples))

;; --- Body evaluation (query-time) ---

(define (eval-body db atoms subst)
  (cond
    [(null? atoms) (list subst)]
    [else
     (define matches (match-atom db (car atoms) subst))
     (for*/list ([s (in-list matches)]
                 [result (in-list (eval-body db (cdr atoms) s))])
       result)]))

;; --- Semi-naive engine ---

(define (classify-rules rules)
  (partition
   (lambda (r)
     (for/and ([a (in-list (dl-rule-body r))])
       (edb-rel? (atom-rel a))))
   rules))

(define (instantiate-head r subst)
  (cons (atom-rel (dl-rule-head r))
        (for/list ([a (in-list (atom-args (dl-rule-head r)))])
          (if (var? a)
              (hash-ref subst (var-name a))
              a))))

;; Evaluate rule body where all IDB atoms use full-db.
(define (eval-body-full full-db atoms subst)
  (cond
    [(null? atoms) (list subst)]
    [else
     (define a (car atoms))
     (define matches
       (if (edb-rel? (atom-rel a))
           (match-atom-edb a subst)
           (match-atom-idb full-db a subst)))
     (for*/list ([s (in-list matches)]
                 [result (in-list (eval-body-full full-db (cdr atoms) s))])
       result)]))

;; Evaluate rule body where atom at delta-pos uses delta-db,
;; other IDB atoms use full-db, EDB atoms use claim store.
(define (eval-body-semi full-db delta-db atoms delta-pos subst)
  (define (go atoms idx subst)
    (cond
      [(null? atoms) (list subst)]
      [else
       (define a (car atoms))
       (define rel (atom-rel a))
       (define matches
         (cond
           [(edb-rel? rel) (match-atom-edb a subst)]
           [(= idx delta-pos) (match-atom-idb delta-db a subst)]
           [else (match-atom-idb full-db a subst)]))
       (for*/list ([s (in-list matches)]
                   [result (in-list (go (cdr atoms) (add1 idx) s))])
         result)]))
  (go atoms 0 subst))

(define (fixpoint-semi-naive rules)
  (define-values (edb-only-rules idb-rules) (classify-rules rules))

  ;; Phase 1: evaluate all rules once against empty IDB.
  ;; Only EDB-only rules produce results here.
  (define full-db (make-hash))
  (define delta-db (make-hash))

  (for* ([r (in-list rules)]
         [subst (in-list (eval-body-full full-db (dl-rule-body r) (hasheq)))])
    (define d (instantiate-head r subst))
    (when (db-add! full-db (car d) (cdr d))
      (db-add! delta-db (car d) (cdr d))))

  ;; Phase 2: iterate with delta restriction.
  ;; Only IDB rules participate. For each rule, evaluate N variants
  ;; where N = number of IDB body positions. Each variant restricts
  ;; one IDB atom to delta (new facts only).
  (let loop ()
    (define new-delta (make-hash))

    (for* ([r (in-list idb-rules)])
      (define body (dl-rule-body r))
      (define positions (idb-body-positions body))
      (for* ([delta-pos (in-list positions)]
             [subst (in-list (eval-body-semi full-db delta-db body
                                             delta-pos (hasheq)))])
        (define d (instantiate-head r subst))
        (define existing (hash-ref full-db (car d) (set)))
        (unless (set-member? existing (cdr d))
          (db-add! new-delta (car d) (cdr d)))))

    (cond
      [(db-empty? new-delta)
       ;; Fixpoint reached. Convert to list-based format for query eval.
       (define result (make-hash))
       (for ([(rel tuples) (in-hash full-db)])
         (hash-set! result rel (set->list tuples)))
       result]
      [else
       ;; Merge new-delta into full-db and iterate.
       (for* ([(rel tuples) (in-hash new-delta)]
              [t (in-set tuples)])
         (db-add! full-db rel t))
       (set! delta-db new-delta)
       (loop)])))

;; --- Provenance-aware evaluation ---
;;
;; Returns (listof (cons subst claim-id-set)) instead of (listof subst).
;; Only tracks claim IDs accessed via current-triple / current-claim,
;; since those are the relations affected by supersession.

(define (idb-tuples/set db rel)
  (set->list (hash-ref db rel (set))))

(define (idb-tuples/list db rel)
  (hash-ref db rel '()))

(define (eval-claim-base/prov args resolved subst use-current?)
  (define cid-val (and (bound? (list-ref resolved 0)) (list-ref resolved 0)))
  (cond
    [cid-val
     (define fields (get-claim cid-val))
     (if (and fields (or (not use-current?) (not (superseded? cid-val))))
         (let ([t (list cid-val (first fields) (second fields) (third fields))])
           (define s (match-tuple args t subst))
           (if s (list (cons s (if use-current? (set cid-val) (set)))) '()))
         '())]
    [else
     (define l (and (bound? (list-ref resolved 1)) (list-ref resolved 1)))
     (define p (and (bound? (list-ref resolved 2)) (list-ref resolved 2)))
     (define r (and (bound? (list-ref resolved 3)) (list-ref resolved 3)))
     (define rows
       (if use-current?
           (current-claims-where #:l l #:p p #:r r)
           (claims-where #:l l #:p p #:r r)))
     (filter-map
      (lambda (c)
        (define s (match-tuple args (row->claim-tuple c) subst))
        (and s (cons s (if use-current? (set (list-ref c 0)) (set)))))
      rows)]))

(define (match-atom-edb/prov a subst)
  (define args (atom-args a))
  (define resolved (map (lambda (x) (resolve-arg x subst)) args))
  (case (atom-rel a)
    [(current-triple)
     (let* ([l (and (bound? (list-ref resolved 0)) (list-ref resolved 0))]
            [p (and (bound? (list-ref resolved 1)) (list-ref resolved 1))]
            [r (and (bound? (list-ref resolved 2)) (list-ref resolved 2))]
            [rows (current-claims-where #:l l #:p p #:r r)])
       (filter-map
        (lambda (c)
          (define s (match-tuple args (row->triple c) subst))
          (and s (cons s (set (list-ref c 0)))))
        rows))]
    [(triple)
     (let* ([l (and (bound? (list-ref resolved 0)) (list-ref resolved 0))]
            [p (and (bound? (list-ref resolved 1)) (list-ref resolved 1))]
            [r (and (bound? (list-ref resolved 2)) (list-ref resolved 2))]
            [rows (claims-where #:l l #:p p #:r r)])
       (filter-map
        (lambda (c)
          (define s (match-tuple args (row->triple c) subst))
          (and s (cons s (set))))
        rows))]
    [(current-claim) (eval-claim-base/prov args resolved subst #t)]
    [(claim)         (eval-claim-base/prov args resolved subst #f)]
    [(value)  (map (lambda (s) (cons s (set))) (eval-value-base args resolved subst))]
    [(object) (map (lambda (s) (cons s (set))) (eval-object-base args resolved subst))]))

(define (eval-body/prov db prov-map atoms subst claims get-idb)
  (cond
    [(null? atoms) (list (cons subst claims))]
    [else
     (define a (car atoms))
     (define matches
       (if (edb-rel? (atom-rel a))
           (match-atom-edb/prov a subst)
           (filter-map
            (lambda (t)
              (define s (match-tuple (atom-args a) t subst))
              (and s (cons s (hash-ref prov-map (cons (atom-rel a) t) (set)))))
            (get-idb db (atom-rel a)))))
     (for*/list ([m (in-list matches)]
                 [result (in-list (eval-body/prov db prov-map (cdr atoms)
                                   (car m) (set-union claims (cdr m)) get-idb))])
       result)]))

(define (eval-body-semi/prov db prov-map delta-db atoms delta-pos
                             subst claims get-idb)
  (define (go atoms idx subst claims)
    (cond
      [(null? atoms) (list (cons subst claims))]
      [else
       (define a (car atoms))
       (define rel (atom-rel a))
       (define matches
         (cond
           [(edb-rel? rel) (match-atom-edb/prov a subst)]
           [(= idx delta-pos)
            (filter-map
             (lambda (t)
               (define s (match-tuple (atom-args a) t subst))
               (and s (cons s (hash-ref prov-map (cons rel t) (set)))))
             (get-idb delta-db rel))]
           [else
            (filter-map
             (lambda (t)
               (define s (match-tuple (atom-args a) t subst))
               (and s (cons s (hash-ref prov-map (cons rel t) (set)))))
             (get-idb db rel))]))
       (for*/list ([m (in-list matches)]
                   [result (in-list (go (cdr atoms) (add1 idx) (car m)
                                       (set-union claims (cdr m))))])
         result)]))
  (go atoms 0 subst claims))

;; --- Provenance-aware fixpoint ---

(define (record-prov! prov-map claim-rev rel tuple claims)
  (define key (cons rel tuple))
  (define existing (hash-ref prov-map key (set)))
  (define merged (set-union existing claims))
  (hash-set! prov-map key merged)
  (for ([c (in-set (set-subtract merged existing))])
    (hash-update! claim-rev c (lambda (s) (set-add s key)) (set))))

(define (fixpoint-semi-naive/prov rules)
  (define-values (edb-only-rules idb-rules) (classify-rules rules))
  (define full-db (make-hash))
  (define delta-db (make-hash))
  (define prov-map (make-hash))
  (define claim-rev (make-hash))

  (for* ([r (in-list rules)]
         [sp (in-list (eval-body/prov full-db prov-map
                        (dl-rule-body r) (hasheq) (set) idb-tuples/set))])
    (define subst (car sp))
    (define claims (cdr sp))
    (define d (instantiate-head r subst))
    (when (db-add! full-db (car d) (cdr d))
      (db-add! delta-db (car d) (cdr d)))
    (record-prov! prov-map claim-rev (car d) (cdr d) claims))

  (let loop ()
    (define new-delta (make-hash))
    (for* ([r (in-list idb-rules)])
      (define body (dl-rule-body r))
      (define positions (idb-body-positions body))
      (for* ([delta-pos (in-list positions)]
             [sp (in-list (eval-body-semi/prov full-db prov-map delta-db
                            body delta-pos (hasheq) (set) idb-tuples/set))])
        (define subst (car sp))
        (define claims (cdr sp))
        (define d (instantiate-head r subst))
        (define existing (hash-ref full-db (car d) (set)))
        (unless (set-member? existing (cdr d))
          (db-add! new-delta (car d) (cdr d)))
        (record-prov! prov-map claim-rev (car d) (cdr d) claims)))

    (cond
      [(db-empty? new-delta)
       (define result (make-hash))
       (for ([(rel tuples) (in-hash full-db)])
         (hash-set! result rel (set->list tuples)))
       (values result prov-map claim-rev)]
      [else
       (for* ([(rel tuples) (in-hash new-delta)]
              [t (in-set tuples)])
         (db-add! full-db rel t))
       (set! delta-db new-delta)
       (loop)])))

;; --- Query ---

(define (resolve-if-edb a)
  (if (edb-rel? (atom-rel a))
      (resolve-atom-literals a)
      a))

(define (resolve-current-rules)
  (for/list ([r (in-list (ctx-ref 'rules '()))])
    (dl-rule (dl-rule-head r)
             (map resolve-if-edb (dl-rule-body r)))))

(define (run-query body-atoms)
  (define resolved-query (map resolve-if-edb body-atoms))
  (define cached-db (ctx-ref 'matview-db #f))
  (define db
    (cond
      [(and cached-db (ctx-ref 'matview-valid? #f))
       cached-db]
      [(ctx-ref 'matview-hooks-registered? #f)
       (define resolved-rules (resolve-current-rules))
       (define-values (fresh-db prov-map claim-rev)
         (fixpoint-semi-naive/prov resolved-rules))
       (ctx-set! 'matview-db fresh-db)
       (ctx-set! 'matview-prov prov-map)
       (ctx-set! 'matview-claim-rev claim-rev)
       (ctx-set! 'matview-resolved-rules resolved-rules)
       (ctx-set! 'matview-valid? #t)
       fresh-db]
      [else
       (fixpoint-semi-naive (resolve-current-rules))]))
  (eval-body db resolved-query (hasheq)))

;; --- Materialized views (with provenance) ---
;;
;; materialize! runs the initial fixpoint with provenance tracking, caches
;; results, and registers hooks on claim!:
;;   - Insertion: delta-propagate with provenance tracking
;;   - Supersession: retract only tuples whose provenance includes the
;;     superseded claim, then re-derive through alternate paths

(define (materialize!)
  (define resolved-rules (resolve-current-rules))
  (define-values (db prov-map claim-rev)
    (fixpoint-semi-naive/prov resolved-rules))
  (ctx-set! 'matview-db db)
  (ctx-set! 'matview-prov prov-map)
  (ctx-set! 'matview-claim-rev claim-rev)
  (ctx-set! 'matview-resolved-rules resolved-rules)
  (ctx-set! 'matview-valid? #t)
  (unless (ctx-ref 'matview-hooks-registered? #f)
    (ctx-set! 'on-claim-hooks
      (cons on-new-claim-prov! (ctx-ref 'on-claim-hooks '())))
    (ctx-set! 'on-supersede-hooks
      (cons on-supersede-prov! (ctx-ref 'on-supersede-hooks '())))
    (ctx-set! 'matview-hooks-registered? #t)))

(define (invalidate-views!)
  (ctx-set! 'matview-valid? #f))

(define (on-new-claim-prov! cid l p r)
  (define db (ctx-ref 'matview-db #f))
  (when (and db (ctx-ref 'matview-valid? #f))
    (define rules (ctx-ref 'matview-resolved-rules '()))
    (define prov-map (ctx-ref 'matview-prov))
    (define claim-rev (ctx-ref 'matview-claim-rev))
    (propagate-edb-delta/prov! db prov-map claim-rev rules
      (list (list 'triple l p r)
            (list 'claim cid l p r)
            (list 'current-triple l p r)
            (list 'current-claim cid l p r))
      cid)))

(define (propagate-edb-delta/prov! db prov-map claim-rev rules entries source-cid)
  (define new-idb (make-hash))

  (for ([r (in-list rules)])
    (define body (dl-rule-body r))
    (for ([i (in-range (length body))])
      (define a (list-ref body i))
      (when (edb-rel? (atom-rel a))
        (for ([entry (in-list entries)]
              #:when (eq? (car entry) (atom-rel a)))
          (define tuple (cdr entry))
          (define subst (match-tuple (atom-args a) tuple (hasheq)))
          (when subst
            (define entry-claims
              (if (memq (car entry) '(current-triple current-claim))
                  (set source-cid)
                  (set)))
            (define other-body (append (take body i) (drop body (add1 i))))
            (for ([sp (in-list (eval-body/prov db prov-map other-body
                                 subst entry-claims idb-tuples/list))])
              (define s (car sp))
              (define claims (cdr sp))
              (define d (instantiate-head r s))
              (define rel (car d))
              (define tup (cdr d))
              (unless (member tup (hash-ref db rel '()))
                (unless (member tup (hash-ref new-idb rel '()))
                  (hash-update! new-idb rel
                    (lambda (old) (cons tup old)) '()))
                (record-prov! prov-map claim-rev rel tup claims))))))))

  (unless (hash-empty? new-idb)
    (for ([(rel tuples) (in-hash new-idb)])
      (hash-set! db rel (append tuples (hash-ref db rel '()))))
    (propagate-idb-delta/prov! db prov-map claim-rev rules new-idb)))

(define (propagate-idb-delta/prov! db prov-map claim-rev rules delta-idb)
  (define new-idb (make-hash))

  (for ([r (in-list rules)])
    (define body (dl-rule-body r))
    (define positions (idb-body-positions body))
    (for ([pos (in-list positions)])
      (define a (list-ref body pos))
      (define delta-tuples (hash-ref delta-idb (atom-rel a) #f))
      (when delta-tuples
        (for ([dt (in-list delta-tuples)])
          (define subst (match-tuple (atom-args a) dt (hasheq)))
          (when subst
            (define dt-claims
              (hash-ref prov-map (cons (atom-rel a) dt) (set)))
            (define other-body (append (take body pos) (drop body (add1 pos))))
            (for ([sp (in-list (eval-body/prov db prov-map other-body
                                 subst dt-claims idb-tuples/list))])
              (define s (car sp))
              (define claims (cdr sp))
              (define d (instantiate-head r s))
              (define rel (car d))
              (define tup (cdr d))
              (unless (member tup (hash-ref db rel '()))
                (unless (member tup (hash-ref new-idb rel '()))
                  (hash-update! new-idb rel
                    (lambda (old) (cons tup old)) '()))
                (record-prov! prov-map claim-rev rel tup claims))))))))

  (unless (hash-empty? new-idb)
    (for ([(rel tuples) (in-hash new-idb)])
      (hash-set! db rel (append tuples (hash-ref db rel '()))))
    (propagate-idb-delta/prov! db prov-map claim-rev rules new-idb)))

(define (on-supersede-prov! superseded-cid)
  (define db (ctx-ref 'matview-db #f))
  (define prov-map (ctx-ref 'matview-prov #f))
  (define claim-rev (ctx-ref 'matview-claim-rev #f))
  (when (and db prov-map claim-rev (ctx-ref 'matview-valid? #f))
    (define affected (hash-ref claim-rev superseded-cid (set)))
    (unless (set-empty? affected)
      (define retracted-keys (set->list affected))
      (for ([key (in-list retracted-keys)])
        (define rel (car key))
        (define tuple (cdr key))
        (hash-set! db rel (remove tuple (hash-ref db rel '())))
        (define old-claims (hash-ref prov-map key (set)))
        (hash-remove! prov-map key)
        (for ([c (in-set old-claims)])
          (hash-update! claim-rev c
            (lambda (s) (set-remove s key)) (set))))
      (define rules (ctx-ref 'matview-resolved-rules '()))
      (let rederive-loop ()
        (define progress? #f)
        (for ([key (in-list retracted-keys)])
          (define rel (car key))
          (define tuple (cdr key))
          (unless (member tuple (hash-ref db rel '()))
            (for ([r (in-list rules)]
                  #:when (eq? (atom-rel (dl-rule-head r)) rel)
                  #:unless (member tuple (hash-ref db rel '())))
              (define head-subst
                (match-tuple (atom-args (dl-rule-head r)) tuple (hasheq)))
              (when head-subst
                (define results
                  (eval-body/prov db prov-map (dl-rule-body r)
                    head-subst (set) idb-tuples/list))
                (when (not (null? results))
                  (define new-claims (cdr (first results)))
                  (hash-update! db rel
                    (lambda (old) (cons tuple old)) '())
                  (record-prov! prov-map claim-rev rel tuple new-claims)
                  (set! progress? #t))))))
        (when progress? (rederive-loop))))))

;; --- Incremental rule addition ---
;;
;; When the matview is valid and a new rule is added, evaluate just that
;; rule against the existing DB. Any new facts delta-propagate through
;; ALL rules (including the new one). Avoids full fixpoint recompute.

(define (propagate-new-rule/prov! new-rule)
  (define db (ctx-ref 'matview-db))
  (define prov-map (ctx-ref 'matview-prov))
  (define claim-rev (ctx-ref 'matview-claim-rev))

  (define resolved
    (dl-rule (dl-rule-head new-rule)
             (map resolve-if-edb (dl-rule-body new-rule))))

  (define all-rules (cons resolved (ctx-ref 'matview-resolved-rules '())))
  (ctx-set! 'matview-resolved-rules all-rules)

  (define delta (make-hash))
  (for ([sp (in-list (eval-body/prov db prov-map
                       (dl-rule-body resolved) (hasheq) (set) idb-tuples/list))])
    (define subst (car sp))
    (define claims (cdr sp))
    (define d (instantiate-head resolved subst))
    (define rel (car d))
    (define tup (cdr d))
    (unless (member tup (hash-ref db rel '()))
      (unless (member tup (hash-ref delta rel '()))
        (hash-update! delta rel (lambda (old) (cons tup old)) '()))
      (record-prov! prov-map claim-rev rel tup claims)))

  (unless (hash-empty? delta)
    (for ([(rel tuples) (in-hash delta)])
      (hash-set! db rel (append tuples (hash-ref db rel '()))))
    (propagate-idb-delta/prov! db prov-map claim-rev all-rules delta)))

;; --- Homoiconic rules (rules as claims) ---
;;
;; Rules become entities in the claim graph with two properties:
;;   rule-head-rel  → relation name (string value)
;;   rule-source    → serialized s-expression (string value)
;;
;; Legacy define-rule macro still works for built-in rules (eval, graph, lang).
;; define-rule!/claims creates a rule entity, stores it as claims, AND pushes
;; it to the in-memory rules list so the engine can use it.

(define (rule-head-rel-pred)
  (ctx-ref 'rule-head-rel-pred-id))

(define (rule-source-pred)
  (ctx-ref 'rule-source-pred-id))

(define (setup-rule-predicates!)
  (ctx-set! 'rule-head-rel-pred-id (named! "rule-head-rel"))
  (ctx-set! 'rule-source-pred-id (named! "rule-source"))
  (ctx-set! 'rule-entities (make-hash)))

(define (serialize-atom a)
  (define args-strs
    (for/list ([arg (atom-args a)])
      (cond
        [(var? arg) (format "(? ~a)" (var-name arg))]
        [(string? arg) (format "~s" arg)]
        [else (format "~a" arg)])))
  (format "(~a~a)"
    (atom-rel a)
    (if (null? args-strs) ""
        (string-append " " (string-join args-strs " ")))))

(define (serialize-rule head body)
  (format "~a :- ~a"
    (serialize-atom head)
    (string-join (map serialize-atom body) " ")))

(define (define-rule!/claims head-atom body-atoms)
  (define rule (dl-rule head-atom body-atoms))
  (define rule-ent (entity!))
  (claim! rule-ent (rule-head-rel-pred) (value! (symbol->string (atom-rel head-atom))))
  (claim! rule-ent (rule-source-pred) (value! (serialize-rule head-atom body-atoms)))
  (ctx-set! 'rules (cons rule (ctx-ref 'rules '())))
  (hash-set! (ctx-ref 'rule-entities) rule-ent rule)
  (if (and (ctx-ref 'matview-db #f) (ctx-ref 'matview-valid? #f))
      (propagate-new-rule/prov! rule)
      (invalidate-views!))
  rule-ent)

(define (supersede-rule! old-rule-ent new-head-atom new-body-atoms)
  (define rule-ents (ctx-ref 'rule-entities))
  (define old-rule (hash-ref rule-ents old-rule-ent #f))
  (unless old-rule
    (error 'supersede-rule! "unknown rule entity: ~a" old-rule-ent))
  (ctx-set! 'rules (remq old-rule (ctx-ref 'rules '())))
  (hash-remove! rule-ents old-rule-ent)
  (define sup-pred (supersedes-pred-id))
  (for ([c (in-list (current-claims-where #:l old-rule-ent))])
    (claim! (entity!) sup-pred (first c)))
  (invalidate-views!)
  (define-rule!/claims new-head-atom new-body-atoms))

(define (list-rule-entities)
  (define ents (ctx-ref 'rule-entities #f))
  (if (hash? ents) (hash-keys ents) '()))

(define (show-results results)
  (if (null? results)
      (displayln "No results.")
      (for ([s (in-list results)]
            [i (in-naturals 1)])
        (printf "~a. " i)
        (displayln
         (string-join
          (sort
           (for/list ([(k v) (in-hash s)])
             (define display-v (if (value-object? v) (resolve-value v) v))
             (format "?~a = ~a" k display-v))
           string<?)
          ", ")))))

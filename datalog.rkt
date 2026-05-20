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
         current-claims-where)

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
  (ctx-set! 'rules '()))

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

;; --- Query ---

(define (resolve-if-edb a)
  (if (edb-rel? (atom-rel a))
      (resolve-atom-literals a)
      a))

(define (run-query body-atoms)
  (define resolved-query (map resolve-if-edb body-atoms))
  (define resolved-rules
    (for/list ([r (in-list (ctx-ref 'rules '()))])
      (dl-rule (dl-rule-head r)
               (map resolve-if-edb (dl-rule-body r)))))
  (define db (fixpoint-semi-naive resolved-rules))
  (eval-body db resolved-query (hasheq)))

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

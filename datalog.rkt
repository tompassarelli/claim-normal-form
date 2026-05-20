#lang racket

(require "cnf.rkt")

(provide var atom dl-rule
         ?
         define-rule
         query
         show-results
         reset-rules!
         supersedes-pred-id
         set-supersedes-pred!
         current-claims-where)

;; Datalog over CNF — index-aware evaluation.
;;
;; Base relations (EDB) dispatch to the live claim store using
;; hash indexes. Bound variables from prior joins constrain the
;; lookup, avoiding full scans.
;;
;; Derived relations (IDB) accumulate during fixpoint iteration
;; in a separate hash.
;;
;; Base relations:
;;   (claim Id L P R)
;;   (triple L P R)
;;   (current-claim Id L P R) — unsuperseded only
;;   (current-triple L P R)   — unsuperseded only
;;   (value Id Literal)
;;   (object Id)

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

;; --- Index-aware base relation evaluation ---
;;
;; claims-where returns rows as (cid p l r).
;; Base relation tuple layouts:
;;   triple:         (L P R)       = (row[2] row[1] row[3])
;;   claim:          (Id L P R)    = (row[0] row[2] row[1] row[3])
;;   current-triple: same as triple, filtered by superseded?
;;   current-claim:  same as claim, filtered by superseded?

(define edb-relations '(claim triple current-claim current-triple value object))

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

(define (match-atom db a subst)
  (define rel (atom-rel a))
  (define args (atom-args a))
  (cond
    [(memq rel edb-relations)
     (define resolved (map (lambda (x) (resolve-arg x subst)) args))
     (case rel
       [(current-triple) (eval-triple-base args resolved subst #t)]
       [(triple)         (eval-triple-base args resolved subst #f)]
       [(current-claim)  (eval-claim-base args resolved subst #t)]
       [(claim)          (eval-claim-base args resolved subst #f)]
       [(value)          (eval-value-base args resolved subst)]
       [(object)         (eval-object-base args resolved subst)])]
    [else
     (define tuples (hash-ref db rel '()))
     (filter-map (lambda (t) (match-tuple args t subst)) tuples)]))

;; --- Body evaluation ---

(define (eval-body db atoms subst)
  (cond
    [(null? atoms) (list subst)]
    [else
     (define matches (match-atom db (car atoms) subst))
     (for*/list ([s (in-list matches)]
                 [result (in-list (eval-body db (cdr atoms) s))])
       result)]))

;; --- Rule application ---

(define (apply-dl-rule db r)
  (define substs (eval-body db (dl-rule-body r) (hasheq)))
  (for/list ([s (in-list substs)])
    (cons (atom-rel (dl-rule-head r))
          (for/list ([a (in-list (atom-args (dl-rule-head r)))])
            (if (var? a)
                (hash-ref s (var-name a))
                a)))))

;; --- Fixpoint ---

(define (iterate-once db rs)
  (define new-db (hash-copy db))
  (define changed? #f)
  (for* ([r (in-list rs)]
         [d (in-list (apply-dl-rule db r))])
    (define rel (car d))
    (define tuple (cdr d))
    (define existing (hash-ref new-db rel '()))
    (unless (member tuple existing)
      (hash-set! new-db rel (cons tuple existing))
      (set! changed? #t)))
  (values new-db changed?))

(define (fixpoint db rs)
  (define-values (new-db changed?) (iterate-once db rs))
  (if changed?
      (fixpoint new-db rs)
      new-db))

;; --- Query ---

(define (run-query body-atoms)
  (define resolved-query (map resolve-atom-literals body-atoms))
  (define resolved-rules
    (for/list ([r (in-list (ctx-ref 'rules '()))])
      (dl-rule (resolve-atom-literals (dl-rule-head r))
               (map resolve-atom-literals (dl-rule-body r)))))
  (define db (fixpoint (make-hash) resolved-rules))
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

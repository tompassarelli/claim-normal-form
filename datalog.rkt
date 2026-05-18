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

;; Datalog over CNF — naive bottom-up fixpoint evaluation.
;;
;; Base relations (EDB):
;;   (claim Id L P R) — claim with its own object ID
;;   (triple L P R)   — projection without claim ID
;;   (current-claim Id L P R) — unsuperseded claims only
;;   (current-triple L P R)   — unsuperseded triples only
;;   (value Id Literal) — value objects and their grounded literals
;;   (object Id)      — all object IDs

(struct var (name) #:transparent)
(struct atom (rel args) #:transparent)
(struct dl-rule (head body) #:transparent)

(define-syntax-rule (? name)
  (var 'name))

;; --- Rules and supersession state (stored in context extensions) ---

(define (supersedes-pred-id)
  (ctx-ref 'supersedes-pred-id #f))

(define (set-supersedes-pred! id)
  (ctx-set! 'supersedes-pred-id id))

(define (current-claims-where #:l [l #f] #:p [p #f] #:r [r #f])
  (define sup-id (supersedes-pred-id))
  (define all (claims-where #:l l #:p p #:r r))
  (if sup-id
      (let ([superseded (make-hash)])
        (for ([row (claims-where #:p sup-id)])
          (hash-set! superseded (list-ref row 3) #t))
        (filter (lambda (c) (not (hash-ref superseded (first c) #f))) all))
      all))

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

;; --- EDB extraction ---

(define (extract-edb)
  (define db (make-hash))
  (define all-claims (claims-where))
  (define sup-id (supersedes-pred-id))
  (define superseded (make-hash))
  (when sup-id
    (for ([row (in-list all-claims)]
          #:when (equal? (list-ref row 1) sup-id))
      (hash-set! superseded (list-ref row 3) #t)))
  (hash-set! db 'claim
    (for/list ([row all-claims])
      (list (list-ref row 0)
            (list-ref row 2)
            (list-ref row 1)
            (list-ref row 3))))
  (hash-set! db 'triple
    (for/list ([row all-claims])
      (list (list-ref row 2)
            (list-ref row 1)
            (list-ref row 3))))
  (define current
    (filter (lambda (row) (not (hash-ref superseded (list-ref row 0) #f)))
            all-claims))
  (hash-set! db 'current-claim
    (for/list ([row current])
      (list (list-ref row 0)
            (list-ref row 2)
            (list-ref row 1)
            (list-ref row 3))))
  (hash-set! db 'current-triple
    (for/list ([row current])
      (list (list-ref row 2)
            (list-ref row 1)
            (list-ref row 3))))
  (hash-set! db 'value
    (for/list ([id (all-objects)]
               #:when (value-object? id))
      (list id (resolve-value id))))
  (hash-set! db 'object
    (for/list ([id (all-objects)])
      (list id)))
  db)

;; --- Literal resolution ---

(define (resolve-literal v)
  (cond
    [(var? v) v]
    [(member v (all-objects)) v]
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

(define (match-atom-against-db db a subst)
  (define tuples (hash-ref db (atom-rel a) '()))
  (filter-map (lambda (tuple) (match-tuple (atom-args a) tuple subst))
              tuples))

;; --- Body evaluation ---

(define (eval-body db atoms subst)
  (cond
    [(null? atoms) (list subst)]
    [else
     (define matches (match-atom-against-db db (car atoms) subst))
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
  (define db (fixpoint (extract-edb) resolved-rules))
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

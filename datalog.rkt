#lang racket

(require "cnf.rkt")

(provide var atom dl-rule
         ?
         define-rule
         query
         show-results
         reset-rules!)

;; Datalog over CNF — naive bottom-up fixpoint evaluation.
;;
;; Base relations (EDB):
;;   (claim Id L P R) — claim with its own object ID
;;   (triple L P R)   — projection without claim ID
;;   (object Id)      — all object IDs
;;
;; Literals in query patterns resolve to their interned value ID
;; automatically. No value/2 join needed:
;;   (triple ?x name "Tom")  just works.

(struct var (name) #:transparent)
(struct atom (rel args) #:transparent)
(struct dl-rule (head body) #:transparent)

(define-syntax-rule (? name)
  (var 'name))

(define rules (make-parameter '()))

(define (reset-rules!)
  (rules '()))

;; --- Syntax ---

(define-syntax parse-atom
  (syntax-rules ()
    [(_ (rel arg ...))
     (atom 'rel (list arg ...))]))

(define-syntax-rule (define-rule (head-rel head-arg ...) body ...)
  (rules (cons (dl-rule (atom 'head-rel (list head-arg ...))
                        (list (parse-atom body) ...))
               (rules))))

(define-syntax query
  (syntax-rules ()
    [(_ body-clause ...)
     (run-query (list (parse-atom body-clause) ...))]))

;; --- EDB extraction ---

(define (extract-edb)
  (define db (make-hash))
  (define all-claims (claims-where))
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
  (hash-set! db 'object
    (for/list ([id (all-objects)])
      (list id)))
  db)

;; --- Literal resolution ---
;; When a constant in a pattern is not an object ID but IS a host literal
;; that has an interned value object, resolve it to that object's ID.
;; This lets users write "Tom" in patterns instead of joining through value/2.

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
  (filter-map (λ (tuple) (match-tuple (atom-args a) tuple subst))
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
    (for/list ([r (in-list (rules))])
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
             (define display-v (or (resolve-value v) v))
             (format "?~a = ~a" k display-v))
           string<?)
          ", ")))))

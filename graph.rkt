#lang racket

(require "cnf.rkt" "datalog.rkt" "eval.rkt")

(provide setup-graph!
         name-pred supersedes-pred
         give-name! rename!
         supersede! invalidate!
         current-name render-ref
         change-operand!
         affected-by
         invalidate-eval-events!
         recompute-affected!)

;; --- Predicates ---

(define name-pred (make-parameter #f))
(define supersedes-pred (make-parameter #f))

;; --- Setup ---

(define (setup-graph!)
  (name-pred (named! "name"))
  (supersedes-pred (named! "supersedes"))
  (set-supersedes-pred! (supersedes-pred))
  ;; Structural dependency: expr depends on operand if operand is itself an expression
  (define-rule (expr-depends-on (? expr) (? dep))
    (current-triple (? expr) (left-pred) (? dep))
    (current-triple (? dep) (op-pred) (? _op1)))
  (define-rule (expr-depends-on (? expr) (? dep))
    (current-triple (? expr) (right-pred) (? dep))
    (current-triple (? dep) (op-pred) (? _op2)))
  ;; Transitive affectedness
  (define-rule (affected (? x) (? changed))
    (expr-depends-on (? x) (? changed)))
  (define-rule (affected (? x) (? changed))
    (expr-depends-on (? x) (? y))
    (affected (? y) (? changed)))
  (void))

;; --- Supersession ---

(define (supersede! old-cid new-l new-p new-r)
  (define new-cid (claim! new-l new-p new-r))
  (claim! new-cid (supersedes-pred) old-cid)
  new-cid)

(define (invalidate! cid)
  (define marker (entity!))
  (claim! marker (supersedes-pred) cid)
  (void))

;; --- Naming ---

(define (give-name! entity-id name-str)
  (claim! entity-id (name-pred) (value! name-str)))

(define (rename! entity-id new-name-str)
  (define old-name-claims
    (current-claims-where #:l entity-id #:p (name-pred)))
  (define new-cid (claim! entity-id (name-pred) (value! new-name-str)))
  (for ([c (in-list old-name-claims)])
    (claim! new-cid (supersedes-pred) (first c)))
  new-cid)

(define (current-name entity-id)
  (define cs (current-claims-where #:l entity-id #:p (name-pred)))
  (and (not (null? cs))
       (resolve-value (list-ref (first cs) 3))))

(define (render-ref entity-id)
  (or (current-name entity-id) entity-id))

;; --- Operand change ---

(define (change-operand! expr-id pred old-val new-val)
  (define old-claims
    (current-claims-where #:l expr-id #:p pred #:r old-val))
  (when (null? old-claims)
    (error 'change-operand! "no matching current claim"))
  (supersede! (first (first old-claims)) expr-id pred new-val))

;; --- Affectedness ---

(define (affected-by changed-expr-id)
  (define results (query (affected (? x) changed-expr-id)))
  (remove-duplicates
   (cons changed-expr-id
         (map (λ (s) (hash-ref s 'x)) results))))

;; --- Incremental recompute ---

(define (invalidate-eval-events! expr-id)
  (define ev-claims
    (current-claims-where #:p (evaluated-pred) #:r expr-id))
  (for ([c (in-list ev-claims)])
    (define ev-entity (list-ref c 2))
    (invalidate! (first c))
    (for ([rc (in-list (current-claims-where #:l ev-entity #:p (result-pred)))])
      (invalidate! (first rc)))
    (for ([ec (in-list (current-claims-where #:l ev-entity #:p (under-env-pred)))])
      (invalidate! (first ec)))))

(define (recompute-affected! env changed-expr-id)
  (define affected-ids (affected-by changed-expr-id))
  (for ([expr-id (in-list affected-ids)])
    (invalidate-eval-events! expr-id))
  (define new-evs (run! env #:only affected-ids))
  (values affected-ids new-evs))

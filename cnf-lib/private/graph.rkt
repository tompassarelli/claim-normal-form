#lang racket

(require "kernel.rkt" "datalog.rkt" "eval.rkt")

(provide setup-graph!
         name-pred supersedes-pred
         give-name! rename!
         supersede! invalidate!
         current-name render-ref
         change-operand!
         affected-by
         invalidate-reductions!
         recompute-affected!)

;; --- Predicate accessors (stored in context extensions) ---

(define (name-pred) (ctx-ref 'name-pred))
(define (supersedes-pred) (ctx-ref 'supersedes-pred))

;; --- Setup ---

(define (setup-graph!)
  (ctx-set! 'name-pred (named! "name"))
  (ctx-set! 'supersedes-pred (named! "supersedes"))
  (set-supersedes-pred! (supersedes-pred))
  ;; Dependency rules: expr depends on its sub-expressions
  (define-rule (expr-depends-on (? expr) (? dep))
    (current-triple (? expr) (left-pred) (? dep))
    (current-triple (? dep) (kind-pred) (? _k)))
  (define-rule (expr-depends-on (? expr) (? dep))
    (current-triple (? expr) (right-pred) (? dep))
    (current-triple (? dep) (kind-pred) (? _k)))
  (define-rule (expr-depends-on (? expr) (? dep))
    (current-triple (? expr) (fn-pred) (? dep))
    (current-triple (? dep) (kind-pred) (? _k)))
  (define-rule (expr-depends-on (? expr) (? dep))
    (current-triple (? expr) (arg-pred) (? dep))
    (current-triple (? dep) (kind-pred) (? _k)))
  (define-rule (expr-depends-on (? expr) (? dep))
    (current-triple (? expr) (body-pred) (? dep))
    (current-triple (? dep) (kind-pred) (? _k)))
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
         (map (lambda (s) (hash-ref s 'x)) results))))

;; --- Incremental recompute ---

(define (invalidate-reductions! expr-id)
  (define red-claims
    (current-claims-where #:p (reduced-from-pred) #:r expr-id))
  (for ([c (in-list red-claims)])
    (define red-entity (list-ref c 2))
    (invalidate! (first c))
    (for ([rc (in-list (current-claims-where #:l red-entity #:p (reduced-to-pred)))])
      (invalidate! (first rc)))
    (for ([rc (in-list (current-claims-where #:l red-entity #:p (reduced-rule-pred)))])
      (invalidate! (first rc)))))

(define (recompute-affected! env changed-expr-id)
  (define affected-ids (affected-by changed-expr-id))
  (for ([expr-id (in-list affected-ids)])
    (invalidate-reductions! expr-id))
  (for/list ([expr-id (in-list affected-ids)])
    (graph-eval expr-id env)))

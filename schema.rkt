#lang racket

(require "cnf.rkt" "datalog.rkt")

(provide setup-schema!
         define-predicates
         assert!
         link!
         entity/claims
         lookup
         lookup-all
         find-by
         update!
         retract!
         unlink!)

;; Ergonomic data modeling over CNF.
;;
;; assert! / link! / update! / retract! / unlink! — CRUD via claims.
;; lookup / find-by — query sugar over current-claims-where.
;; define-predicates — batch predicate creation.
;; entity/claims — entity + initial properties in one form.

;; --- Setup ---

(define (setup-schema!)
  (unless (ctx-ref 'supersedes-pred)
    (ctx-set! 'supersedes-pred (named! "supersedes"))
    (set-supersedes-pred! (ctx-ref 'supersedes-pred)))
  (void))

;; --- Predicate definition ---

(define-syntax define-predicates
  (syntax-rules ()
    [(_ name ...)
     (begin
       (define name (named! (symbol->string 'name))) ...)]))

;; --- Entity creation ---

(define-syntax-rule (entity/claims [pred val] ...)
  (let ([e (entity!)])
    (assert! e pred val) ...
    e))

;; --- Assertions ---

(define (assert! entity pred val)
  (claim! entity pred (value! val)))

(define (link! entity pred target)
  (claim! entity pred target))

;; --- Lookup ---

(define (lookup entity pred)
  (define cs (current-claims-where #:l entity #:p pred))
  (and (not (null? cs))
       (let ([right-obj (list-ref (first cs) 3)])
         (if (value-object? right-obj)
             (resolve-value right-obj)
             right-obj))))

(define (lookup-all entity pred)
  (define cs (current-claims-where #:l entity #:p pred))
  (for/list ([c (in-list cs)])
    (let ([right-obj (list-ref c 3)])
      (if (value-object? right-obj)
          (resolve-value right-obj)
          right-obj))))

(define (find-by pred val)
  (define vid (value-id val))
  (define right-obj (or vid val))
  (define cs (current-claims-where #:p pred #:r right-obj))
  (map (lambda (c) (list-ref c 2)) cs))

;; --- Mutation (via supersession) ---

(define (update! entity pred new-val)
  (define new-obj (value! new-val))
  (define old-claims (current-claims-where #:l entity #:p pred))
  (define new-cid (claim! entity pred new-obj))
  (define sup (ctx-ref 'supersedes-pred))
  (for ([c (in-list old-claims)])
    (claim! new-cid sup (first c)))
  new-cid)

(define (retract! entity pred)
  (define old-claims (current-claims-where #:l entity #:p pred))
  (define sup (ctx-ref 'supersedes-pred))
  (for ([c (in-list old-claims)])
    (define marker (entity!))
    (claim! marker sup (first c)))
  (void))

(define (unlink! entity pred target)
  (define old-claims (current-claims-where #:l entity #:p pred #:r target))
  (define sup (ctx-ref 'supersedes-pred))
  (for ([c (in-list old-claims)])
    (define marker (entity!))
    (claim! marker sup (first c)))
  (void))

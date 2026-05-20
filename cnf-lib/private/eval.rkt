#lang racket

(require "kernel.rkt" "datalog.rkt")

(provide setup-eval!
         register-primitive!
         expr!
         eval-step!
         run!
         eval-result
         op-pred left-pred right-pred
         evaluated-pred result-pred under-env-pred)

;; Small-step graph evaluator over CNF.
;;
;; Datalog  = eyes  (derive which expressions are ready to step)
;; Racket   = hands (execute registered primitives)
;; Claims   = memory (record eval events and results)

;; --- Predicate accessors (stored in context extensions) ---

(define (op-pred) (ctx-ref 'op-pred))
(define (left-pred) (ctx-ref 'left-pred))
(define (right-pred) (ctx-ref 'right-pred))
(define (evaluated-pred) (ctx-ref 'evaluated-pred))
(define (result-pred) (ctx-ref 'result-pred))
(define (under-env-pred) (ctx-ref 'under-env-pred))

;; --- Setup ---

(define (setup-eval!)
  (ctx-set! 'op-pred (named! "op"))
  (ctx-set! 'left-pred (named! "left"))
  (ctx-set! 'right-pred (named! "right"))
  (ctx-set! 'evaluated-pred (named! "evaluated"))
  (ctx-set! 'result-pred (named! "result"))
  (ctx-set! 'under-env-pred (named! "under-env"))
  (ctx-set! 'primitives (make-hash))
  (define-rule (operand-val (? operand) (? operand))
    (value (? operand) (? _lit)))
  (define-rule (operand-val (? operand) (? result-val))
    (current-triple (? ev) (evaluated-pred) (? operand))
    (current-triple (? ev) (result-pred) (? result-val)))
  (define-rule (ready (? expr) (? op) (? lval) (? rval))
    (current-triple (? expr) (op-pred) (? op))
    (current-triple (? expr) (left-pred) (? left))
    (current-triple (? expr) (right-pred) (? right))
    (operand-val (? left) (? lval))
    (operand-val (? right) (? rval)))
  (void))

;; --- Primitive registry ---

(define (register-primitive! obj-id proc)
  (hash-set! (ctx-ref 'primitives) obj-id proc))

;; --- Expression builder ---

(define (expr! op left right)
  (define e (entity!))
  (claim! e (op-pred) op)
  (claim! e (left-pred) left)
  (claim! e (right-pred) right)
  e)

;; --- Stepping ---

(define (has-eval-event? expr-id)
  (not (null? (current-claims-where #:p (evaluated-pred) #:r expr-id))))

(define (eval-step! env #:only [only #f])
  (define results (query (ready (? expr) (? op) (? lval) (? rval))))
  (define prims (ctx-ref 'primitives))
  (define candidates
    (filter (lambda (s)
              (define expr-id (hash-ref s 'expr))
              (and (hash-ref prims (hash-ref s 'op) #f)
                   (not (has-eval-event? expr-id))
                   (or (not only) (member expr-id only))))
            results))
  (cond
    [(null? candidates) #f]
    [else
     (define s (first candidates))
     (define expr-id (hash-ref s 'expr))
     (define op-id (hash-ref s 'op))
     (define lval-id (hash-ref s 'lval))
     (define rval-id (hash-ref s 'rval))
     (define proc (hash-ref prims op-id))
     (define result-lit (proc (resolve-value lval-id)
                              (resolve-value rval-id)))
     (define result-val (value! result-lit))
     (define ev (entity!))
     (claim! ev (evaluated-pred) expr-id)
     (claim! ev (result-pred) result-val)
     (claim! ev (under-env-pred) env)
     ev]))

;; --- Run to fixpoint ---

(define (run! env #:only [only #f])
  (define ev (eval-step! env #:only only))
  (if ev
      (cons ev (run! env #:only only))
      '()))

;; --- Result reader ---

(define (eval-result ev-id)
  (define cs (claims-where #:l ev-id #:p (result-pred)))
  (and (not (null? cs))
       (resolve-value (list-ref (first cs) 3))))

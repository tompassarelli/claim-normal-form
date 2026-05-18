#lang racket

(require "cnf.rkt" "datalog.rkt")

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
;;
;; Evaluation is not a query. Evaluation is a controlled graph
;; transition that uses queries to find where to step.

;; --- Predicates (created fresh by setup-eval!) ---

(define op-pred (make-parameter #f))
(define left-pred (make-parameter #f))
(define right-pred (make-parameter #f))
(define evaluated-pred (make-parameter #f))
(define result-pred (make-parameter #f))
(define under-env-pred (make-parameter #f))

;; --- Primitive registry ---

(define primitives (make-parameter (make-hash)))

(define (register-primitive! obj-id proc)
  (hash-set! (primitives) obj-id proc))

;; --- Setup ---

(define (setup-eval!)
  (op-pred (named! "op"))
  (left-pred (named! "left"))
  (right-pred (named! "right"))
  (evaluated-pred (named! "evaluated"))
  (result-pred (named! "result"))
  (under-env-pred (named! "under-env"))
  (primitives (make-hash))
  ;; An operand resolves to a value directly
  (define-rule (operand-val (? operand) (? operand))
    (value (? operand) (? _lit)))
  ;; An operand resolves via a prior eval event's result
  (define-rule (operand-val (? operand) (? result-val))
    (triple (? ev) (evaluated-pred) (? operand))
    (triple (? ev) (result-pred) (? result-val)))
  ;; An expression is ready when it has op + both operands resolve
  (define-rule (ready (? expr) (? op) (? lval) (? rval))
    (triple (? expr) (op-pred) (? op))
    (triple (? expr) (left-pred) (? left))
    (triple (? expr) (right-pred) (? right))
    (operand-val (? left) (? lval))
    (operand-val (? right) (? rval)))
  (void))

;; --- Expression builder ---

(define (expr! op left right)
  (define e (entity!))
  (claim! e (op-pred) op)
  (claim! e (left-pred) left)
  (claim! e (right-pred) right)
  e)

;; --- Stepping ---

(define (has-eval-event? expr-id)
  (not (null? (claims-where #:p (evaluated-pred) #:r expr-id))))

(define (eval-step! env)
  (define results (query (ready (? expr) (? op) (? lval) (? rval))))
  (define candidates
    (filter (λ (s)
              (and (hash-ref (primitives) (hash-ref s 'op) #f)
                   (not (has-eval-event? (hash-ref s 'expr)))))
            results))
  (cond
    [(null? candidates) #f]
    [else
     (define s (first candidates))
     (define expr-id (hash-ref s 'expr))
     (define op-id (hash-ref s 'op))
     (define lval-id (hash-ref s 'lval))
     (define rval-id (hash-ref s 'rval))
     (define proc (hash-ref (primitives) op-id))
     (define result-lit (proc (resolve-value lval-id)
                              (resolve-value rval-id)))
     (define result-val (value! result-lit))
     (define ev (entity!))
     (claim! ev (evaluated-pred) expr-id)
     (claim! ev (result-pred) result-val)
     (claim! ev (under-env-pred) env)
     ev]))

;; --- Run to fixpoint ---

(define (run! env)
  (define ev (eval-step! env))
  (if ev
      (cons ev (run! env))
      '()))

;; --- Result reader ---

(define (eval-result ev-id)
  (define cs (claims-where #:l ev-id #:p (result-pred)))
  (and (not (null? cs))
       (resolve-value (list-ref (first cs) 3))))

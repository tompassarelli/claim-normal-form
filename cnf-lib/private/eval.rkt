#lang racket

(require "kernel.rkt" "datalog.rkt")

(provide setup-eval!
         register-primitive!
         ;; node constructors
         lit! var! lam! app! binop! let! if! letrec!
         ;; environments
         empty-env extend-env
         ;; evaluation
         graph-eval
         (struct-out exn:fuel)
         ;; predicate accessors (for query/inspection)
         kind-pred param-pred body-pred
         binding-pred binding-name-pred
         fn-pred arg-pred
         op-pred left-pred right-pred
         cond-pred then-pred else-pred
         let-binding-pred let-val-pred let-body-pred
         reduced-from-pred reduced-to-pred reduced-rule-pred
         env-parent-pred env-binding-pred env-value-pred
         fuel-limit-pred fuel-used-pred
         run-root-pred run-status-pred run-result-pred
         run-reason-pred run-error-node-pred
         ;; inspection
         node-kind node-value node-ref
)

;; ══════════════════════════════════════════════════════════════════
;; Graph evaluator over CNF claims.
;;
;; The graph IS the program. No source files. Agents write claims,
;; the reducer evaluates by creating new nodes + provenance edges.
;; Nothing is destroyed — reductions are new facts.
;;
;; Core calculus: literal, var, lambda, apply, binop, let, if.
;; Environments and closures are graph nodes too.
;; ══════════════════════════════════════════════════════════════════

;; --- Predicates (stored in context extensions) ---

(define (kind-pred)       (ctx-ref 'eval/kind))
(define (param-pred)      (ctx-ref 'eval/param))
(define (body-pred)       (ctx-ref 'eval/body))
(define (binding-pred)    (ctx-ref 'eval/binding))
(define (binding-name-pred)      (ctx-ref 'eval/name))
(define (fn-pred)         (ctx-ref 'eval/fn))
(define (arg-pred)        (ctx-ref 'eval/arg))
(define (op-pred)         (ctx-ref 'eval/op))
(define (left-pred)       (ctx-ref 'eval/left))
(define (right-pred)      (ctx-ref 'eval/right))
(define (cond-pred)       (ctx-ref 'eval/cond))
(define (then-pred)       (ctx-ref 'eval/then))
(define (else-pred)       (ctx-ref 'eval/else))
(define (let-binding-pred)(ctx-ref 'eval/let-binding))
(define (let-val-pred)    (ctx-ref 'eval/let-val))
(define (let-body-pred)   (ctx-ref 'eval/let-body))

;; provenance
(define (reduced-from-pred) (ctx-ref 'eval/reduced-from))
(define (reduced-to-pred)   (ctx-ref 'eval/reduced-to))
(define (reduced-rule-pred) (ctx-ref 'eval/reduced-rule))

;; environments
(define (env-parent-pred)  (ctx-ref 'eval/env-parent))
(define (env-binding-pred) (ctx-ref 'eval/env-binding))
(define (env-value-pred)   (ctx-ref 'eval/env-value))

;; closures
(define (closure-param-pred) (ctx-ref 'eval/closure-param))
(define (closure-body-pred)  (ctx-ref 'eval/closure-body))
(define (closure-env-pred)   (ctx-ref 'eval/closure-env))

;; fuel
(define (fuel-limit-pred) (ctx-ref 'eval/fuel-limit))
(define (fuel-used-pred)  (ctx-ref 'eval/fuel-used))

;; eval runs
(define (run-root-pred)       (ctx-ref 'eval/run-root))
(define (run-status-pred)     (ctx-ref 'eval/run-status))
(define (run-result-pred)     (ctx-ref 'eval/run-result))
(define (run-reason-pred)     (ctx-ref 'eval/run-reason))
(define (run-error-node-pred) (ctx-ref 'eval/run-error-node))


;; --- Setup ---

(define (setup-eval!)
  (for ([p '(kind param body binding name fn arg op left right
             cond then else let-binding let-val let-body
             reduced-from reduced-to reduced-rule
             env-parent env-binding env-value
             closure-param closure-body closure-env
             fuel-limit fuel-used
             run-root run-status run-result run-reason run-error-node)])
    (ctx-set! (string->symbol (format "eval/~a" p)) (named! (symbol->string p))))
  (ctx-set! 'eval/primitives (make-hash)))


;; --- Primitive registry ---

(define (register-primitive! name-str proc)
  (hash-set! (ctx-ref 'eval/primitives) name-str proc))


;; --- Node constructors ---

(define (lit! val)
  (define e (entity!))
  (claim! e (kind-pred) (value! "literal"))
  (claim! e (value! "value") (value! val))
  e)

(define (var! binding-id)
  (define e (entity!))
  (claim! e (kind-pred) (value! "var"))
  (claim! e (binding-pred) binding-id)
  e)

(define (make-binding! name-str)
  (define b (entity!))
  (claim! b (kind-pred) (value! "binding"))
  (claim! b (binding-name-pred) (value! name-str))
  b)

(define (lam! param-name body-expr)
  (define b (make-binding! param-name))
  (define e (entity!))
  (claim! e (kind-pred) (value! "lambda"))
  (claim! e (param-pred) b)
  (claim! e (body-pred) body-expr)
  (values e b))

(define (app! fn-expr arg-expr)
  (define e (entity!))
  (claim! e (kind-pred) (value! "apply"))
  (claim! e (fn-pred) fn-expr)
  (claim! e (arg-pred) arg-expr)
  e)

(define (binop! op-name left-expr right-expr)
  (define e (entity!))
  (claim! e (kind-pred) (value! "binop"))
  (claim! e (op-pred) (value! op-name))
  (claim! e (left-pred) left-expr)
  (claim! e (right-pred) right-expr)
  e)

(define (let! name val-expr body-fn)
  ;; body-fn receives the binding entity so vars can reference it
  (define b (make-binding! name))
  (define body-expr (body-fn b))
  (define e (entity!))
  (claim! e (kind-pred) (value! "let"))
  (claim! e (let-binding-pred) b)
  (claim! e (let-val-pred) val-expr)
  (claim! e (let-body-pred) body-expr)
  e)

(define (if! cond-expr then-expr else-expr)
  (define e (entity!))
  (claim! e (kind-pred) (value! "if"))
  (claim! e (cond-pred) cond-expr)
  (claim! e (then-pred) then-expr)
  (claim! e (else-pred) else-expr)
  e)

(define (letrec! name val-fn body-fn)
  (define b (make-binding! name))
  (define val-expr (val-fn b))
  (define body-expr (body-fn b))
  (define e (entity!))
  (claim! e (kind-pred) (value! "letrec"))
  (claim! e (let-binding-pred) b)
  (claim! e (let-val-pred) val-expr)
  (claim! e (let-body-pred) body-expr)
  e)


;; --- Environments (graph nodes) ---

(define (empty-env)
  (define e (entity!))
  (claim! e (kind-pred) (value! "env"))
  e)

(define (extend-env parent binding-id val-id)
  (define e (entity!))
  (claim! e (kind-pred) (value! "env"))
  (claim! e (env-parent-pred) parent)
  (claim! e (env-binding-pred) binding-id)
  (claim! e (env-value-pred) val-id)
  e)

(define (env-lookup env-id binding-id)
  ;; Walk the environment chain looking for binding-id
  (define b-claims (current-claims-where #:l env-id #:p (env-binding-pred)))
  (cond
    [(and (not (null? b-claims))
          (equal? (list-ref (first b-claims) 3) binding-id))
     ;; Found it — return the value
     (define v-claims (current-claims-where #:l env-id #:p (env-value-pred)))
     (if (null? v-claims) #f (list-ref (first v-claims) 3))]
    [else
     ;; Check parent
     (define p-claims (current-claims-where #:l env-id #:p (env-parent-pred)))
     (if (null? p-claims)
         #f
         (env-lookup (list-ref (first p-claims) 3) binding-id))]))


;; --- Closures (graph nodes) ---

(define (make-closure! param-id body-id env-id)
  (define c (entity!))
  (claim! c (kind-pred) (value! "closure"))
  (claim! c (closure-param-pred) param-id)
  (claim! c (closure-body-pred) body-id)
  (claim! c (closure-env-pred) env-id)
  c)


;; --- Provenance ---

(define (record-reduction! from-id to-id rule-name)
  (define r (entity!))
  (claim! r (kind-pred) (value! "reduction"))
  (claim! r (reduced-from-pred) from-id)
  (claim! r (reduced-to-pred) to-id)
  (claim! r (reduced-rule-pred) (value! rule-name))
  r)


;; --- Node inspection helpers ---

(define (node-kind id)
  (define cs (current-claims-where #:l id #:p (kind-pred)))
  (and (not (null? cs))
       (resolve-value (list-ref (first cs) 3))))

(define (node-value id)
  (define cs (current-claims-where #:l id #:p (value! "value")))
  (and (not (null? cs))
       (resolve-value (list-ref (first cs) 3))))

(define (node-ref id pred)
  (define cs (current-claims-where #:l id #:p pred))
  (and (not (null? cs))
       (list-ref (first cs) 3)))


;; --- Fuel exhaustion ---

(struct exn:fuel exn:fail (node-id) #:transparent)


;; --- The evaluator ---

(define (graph-eval expr-id env-id #:fuel [fuel 10000] #:fuel-used [fuel-used-box #f])
  (define initial-fuel fuel)
  (define fuel-box (box fuel))

  (define (consume-fuel! expr-id)
    (when (<= (unbox fuel-box) 0)
      (when fuel-used-box (set-box! fuel-used-box initial-fuel))
      (define incomplete (entity!))
      (claim! incomplete (kind-pred) (value! "incomplete"))
      (claim! incomplete (fuel-limit-pred) (value! initial-fuel))
      (claim! incomplete (fuel-used-pred) (value! initial-fuel))
      (record-reduction! expr-id incomplete "fuel-exhausted")
      (raise (exn:fuel
              (format "fuel exhausted evaluating ~a" expr-id)
              (current-continuation-marks)
              incomplete)))
    (set-box! fuel-box (sub1 (unbox fuel-box))))

  (define (go expr-id env-id)
    (consume-fuel! expr-id)
    (define kind (node-kind expr-id))
    (case kind
      [("literal") expr-id]

      [("var")
       (define binding-id (node-ref expr-id (binding-pred)))
       (define val (env-lookup env-id binding-id))
       (unless val
         (define b-name-cs (current-claims-where #:l binding-id #:p (binding-name-pred)))
         (define name (if (null? b-name-cs) "?" (resolve-value (list-ref (first b-name-cs) 3))))
         (error 'graph-eval "unbound variable: ~a" name))
       (record-reduction! expr-id val "var-lookup")
       val]

      [("lambda")
       (define param-id (node-ref expr-id (param-pred)))
       (define body-id (node-ref expr-id (body-pred)))
       (define closure (make-closure! param-id body-id env-id))
       (record-reduction! expr-id closure "lambda→closure")
       closure]

      [("apply")
       (define fn-id (node-ref expr-id (fn-pred)))
       (define arg-id (node-ref expr-id (arg-pred)))
       (define fn-val (go fn-id env-id))
       (define arg-val (go arg-id env-id))
       (define fn-kind (node-kind fn-val))
       (unless (equal? fn-kind "closure")
         (error 'graph-eval "cannot apply non-closure: ~a" fn-kind))
       (define c-param (node-ref fn-val (closure-param-pred)))
       (define c-body (node-ref fn-val (closure-body-pred)))
       (define c-env (node-ref fn-val (closure-env-pred)))
       (define new-env (extend-env c-env c-param arg-val))
       (define result (go c-body new-env))
       (record-reduction! expr-id result "beta")
       result]

      [("binop")
       (define op-name (resolve-value (node-ref expr-id (op-pred))))
       (define left-id (node-ref expr-id (left-pred)))
       (define right-id (node-ref expr-id (right-pred)))
       (define left-val (go left-id env-id))
       (define right-val (go right-id env-id))
       (define l-lit (node-value left-val))
       (define r-lit (node-value right-val))
       (unless (and l-lit r-lit)
         (error 'graph-eval "binop operands must be literals, got ~a ~a" l-lit r-lit))
       (define prims (ctx-ref 'eval/primitives))
       (define proc (hash-ref prims op-name
                              (lambda () (error 'graph-eval "unknown primitive: ~a" op-name))))
       (define result-val (proc l-lit r-lit))
       (define result-node (lit! result-val))
       (record-reduction! expr-id result-node op-name)
       result-node]

      [("let")
       (define binding-id (node-ref expr-id (let-binding-pred)))
       (define val-id (node-ref expr-id (let-val-pred)))
       (define body-id (node-ref expr-id (let-body-pred)))
       (define val (go val-id env-id))
       (define new-env (extend-env env-id binding-id val))
       (define result (go body-id new-env))
       (record-reduction! expr-id result "let")
       result]

      [("letrec")
       (define binding-id (node-ref expr-id (let-binding-pred)))
       (define val-id (node-ref expr-id (let-val-pred)))
       (define body-id (node-ref expr-id (let-body-pred)))
       (define placeholder (lit! 'undefined))
       (define rec-env (extend-env env-id binding-id placeholder))
       (define val-result (go val-id rec-env))
       ;; Patch: newest env-value claim wins in env-lookup
       (claim! rec-env (env-value-pred) val-result)
       (define result (go body-id rec-env))
       (record-reduction! expr-id result "letrec")
       result]

      [("if")
       (define cond-id (node-ref expr-id (cond-pred)))
       (define then-id (node-ref expr-id (then-pred)))
       (define else-id (node-ref expr-id (else-pred)))
       (define cond-val (go cond-id env-id))
       (define cond-lit (node-value cond-val))
       (define branch (if cond-lit then-id else-id))
       (define result (go branch env-id))
       (record-reduction! expr-id result (if cond-lit "if-then" "if-else"))
       result]

      [else
       (error 'graph-eval "unknown node kind: ~a (entity ~a)" kind expr-id)]))

  (define result (go expr-id env-id))
  (when fuel-used-box
    (set-box! fuel-used-box (- initial-fuel (unbox fuel-box))))
  result)



#lang racket

(require rackunit
         cnf/private/kernel
         cnf/private/datalog
         (only-in cnf/private/eval setup-eval! op-pred
                                  graph-eval empty-env extend-env
                                  node-value kind-pred
                                  node-kind node-ref
                                  run-root-pred run-status-pred
                                  run-result-pred run-reason-pred
                                  run-error-node-pred
                                  fuel-limit-pred fuel-used-pred
                                  exn:fuel exn:fuel-node-id
                                  var! app! lit!)
         cnf/private/graph
         cnf/private/lang)

(define (fresh!)
  (reset-store!)
  (setup-eval!)
  (setup-graph!)
  (setup-lang!))

;; 1. Single function parse/render round-trip
(fresh!)
(let ()
  (define source "(defn double [x y]\n  (* x y))")
  (define fns (parse-program! source))
  (check-equal? (length fns) 1)
  (check-equal? (render-fn (first fns)) source)
  (displayln "PASS 1 — single function parse/render round-trip"))

;; 2. Cross-function call round-trip
(fresh!)
(let ()
  (define fn1 "(defn compute-pay [hours rate]\n  (* hours rate))")
  (define fn2 "(defn total-cost [hours rate]\n  (+ (compute-pay hours rate) 100))")
  (define source (string-join (list fn1 fn2) "\n\n"))
  (define fns (parse-program! source))
  (check-equal? (length fns) 2)
  (check-equal? (render-program fns) source)
  (displayln "PASS 2 — cross-function call parse/render round-trip"))

;; 3. Number literals preserved
(fresh!)
(let ()
  (define source "(defn add-ten [x y]\n  (+ x 10))")
  (define fns (parse-program! source))
  (check-equal? (render-fn (first fns)) source)
  (displayln "PASS 3 — number literals preserved in round-trip"))

;; 4. Nested expressions
(fresh!)
(let ()
  (define source "(defn nested [a b]\n  (* (+ a b) (- a b)))")
  (define fns (parse-program! source))
  (check-equal? (render-fn (first fns)) source)
  (displayln "PASS 4 — nested expressions round-trip"))

;; 5. Rename function — call site updates automatically
(fresh!)
(let ()
  (define fn1 "(defn compute-pay [hours rate]\n  (* hours rate))")
  (define fn2 "(defn total-cost [hours rate]\n  (+ (compute-pay hours rate) 100))")
  (define source (string-join (list fn1 fn2) "\n\n"))
  (define fns (parse-program! source))
  (rename! (first fns) "calculate-pay")
  (define rendered (render-program fns))
  (check-true (string-contains? rendered "calculate-pay"))
  (check-false (string-contains? rendered "compute-pay"))
  (check-true (string-contains? (render-fn (second fns)) "calculate-pay"))
  (displayln "PASS 5 — rename propagates to call sites"))

;; 6. Old name preserved after rename
(fresh!)
(let ()
  (define fns (parse-program! "(defn my-fn [a b]\n  (+ a b))"))
  (define fn-id (first fns))
  (rename! fn-id "new-name")
  (check-equal? (render-ref fn-id) "new-name")
  (define all-name-claims (claims-where #:l fn-id #:p (name-pred)))
  (check-equal? (length all-name-claims) 2)
  (define name-vals
    (map (lambda (c) (resolve-value (list-ref c 3))) all-name-claims))
  (check-not-false (member "my-fn" name-vals))
  (check-not-false (member "new-name" name-vals))
  (displayln "PASS 6 — old name preserved as history"))

;; 7. fn-depends-on derived by Datalog
(fresh!)
(let ()
  (define fn1 "(defn helper [a b]\n  (+ a b))")
  (define fn2 "(defn caller [x y]\n  (* (helper x y) 2))")
  (define source (string-join (list fn1 fn2) "\n\n"))
  (define fns (parse-program! source))
  (define helper-fn (first fns))
  (define caller-fn (second fns))
  (define deps (query (fn-depends-on (? who) (? on))))
  (check-true
   (ormap (lambda (s)
            (and (equal? (hash-ref s 'who) caller-fn)
                 (equal? (hash-ref s 'on) helper-fn)))
          deps))
  (displayln "PASS 7 — fn-depends-on derived by Datalog"))

;; 8. Change body operator via supersession
(fresh!)
(let ()
  (define fns (parse-program! "(defn calc [a b]\n  (* a b))"))
  (define fn-id (first fns))
  (define body-id (get-body fn-id))
  (change-operand! body-id (op-pred) (value! "*") (value! "+"))
  (define rendered (render-fn fn-id))
  (check-true (string-contains? rendered "(+ a b)"))
  (check-false (string-contains? rendered "(* a b)"))
  (define all-op-claims (claims-where #:l body-id #:p (op-pred)))
  (check-equal? (length all-op-claims) 2)
  (displayln "PASS 8 — operator changed via supersession, old preserved"))

;; 9. add-function! adds to existing graph
(fresh!)
(let ()
  (define fns (parse-program! "(defn helper [a b]\n  (+ a b))"))
  (materialize!)
  (define helper-id (first fns))
  (define fn2 (add-function! "(defn caller [x y]\n  (* (helper x y) 2))"))
  (check-equal? (render-ref fn2) "caller")
  (define deps (query (fn-depends-on fn2 (? on))))
  (check-true (ormap (lambda (s) (equal? (hash-ref s 'on) helper-id)) deps))
  (displayln "PASS 9 — add-function! adds to existing graph with matview update"))

;; 10. remove-function! invalidates all function claims
(fresh!)
(let ()
  (define fns (parse-program! "(defn foo [a b]\n  (+ a b))\n\n(defn bar [x y]\n  (* x y))"))
  (materialize!)
  (define foo-id (first fns))
  (remove-function! "foo")
  (define name-claims (current-claims-where #:l foo-id #:p (name-pred)))
  (check-equal? (length name-claims) 0)
  (define body-claims (current-claims-where #:l foo-id #:p (body-pred)))
  (check-equal? (length body-claims) 0)
  (define param-claims (current-claims-where #:l foo-id #:p (has-param-pred)))
  (check-equal? (length param-claims) 0)
  (displayln "PASS 10 — remove-function! invalidates all function claims"))

;; 11. remove-function! retracts fn-depends-on derived tuples
(fresh!)
(let ()
  (define source "(defn helper [a b]\n  (+ a b))\n\n(defn caller [x y]\n  (helper x y))")
  (define fns (parse-program! source))
  (materialize!)
  (define helper-id (first fns))
  (define caller-id (second fns))
  (define deps-before (query (fn-depends-on caller-id (? on))))
  (check-true (> (length deps-before) 0))
  (remove-function! "caller")
  (define deps-after (query (fn-depends-on caller-id (? on))))
  (check-equal? (length deps-after) 0)
  (displayln "PASS 11 — remove-function! retracts fn-depends-on derived tuples"))

;; 12. modify-function! preserves entity identity
(fresh!)
(let ()
  (define source "(defn helper [a b]\n  (+ a b))\n\n(defn caller [x y]\n  (helper x y))")
  (define fns (parse-program! source))
  (materialize!)
  (define helper-id (first fns))
  (define caller-id (second fns))
  (modify-function! "helper" "(defn helper [a b]\n  (* a b))")
  (check-equal? (render-ref helper-id) "helper")
  (define rendered (render-fn helper-id))
  (check-true (string-contains? rendered "(* a b)"))
  (define deps (query (fn-depends-on caller-id (? on))))
  (check-true (ormap (lambda (s) (equal? (hash-ref s 'on) helper-id)) deps))
  (displayln "PASS 12 — modify-function! preserves entity identity, caller still depends"))

;; 13. modify-function! updates fn-depends-on when calls change
(fresh!)
(let ()
  (define source (string-append
    "(defn a [x y]\n  (+ x y))\n\n"
    "(defn b [x y]\n  (* x y))\n\n"
    "(defn c [x y]\n  (a x y))"))
  (define fns (parse-program! source))
  (materialize!)
  (define a-id (first fns))
  (define b-id (second fns))
  (define c-id (third fns))
  (define deps-before (query (fn-depends-on c-id (? on))))
  (check-true (ormap (lambda (s) (equal? (hash-ref s 'on) a-id)) deps-before))
  (modify-function! "c" "(defn c [x y]\n  (b x y))")
  (define deps-after (query (fn-depends-on c-id (? on))))
  (check-false (ormap (lambda (s) (equal? (hash-ref s 'on) a-id)) deps-after))
  (check-true (ormap (lambda (s) (equal? (hash-ref s 'on) b-id)) deps-after))
  (displayln "PASS 13 — modify-function! updates fn-depends-on when calls change"))

;; 14. modify-function! can rename simultaneously
(fresh!)
(let ()
  (define fns (parse-program! "(defn old-name [a b]\n  (+ a b))"))
  (materialize!)
  (define fn-id (first fns))
  (modify-function! "old-name" "(defn new-name [a b]\n  (* a b))")
  (check-equal? (render-ref fn-id) "new-name")
  (define rendered (render-fn fn-id))
  (check-true (string-contains? rendered "new-name"))
  (check-true (string-contains? rendered "(* a b)"))
  (displayln "PASS 14 — modify-function! can rename simultaneously"))

;; 15. add-function! with calls to existing functions
(fresh!)
(let ()
  (define source "(defn base [a b]\n  (+ a b))")
  (define fns (parse-program! source))
  (materialize!)
  (define base-id (first fns))
  (define new-fn (add-function! "(defn wrapper [x y]\n  (+ (base x y) 1))"))
  (define deps (query (fn-depends-on new-fn (? on))))
  (check-true (ormap (lambda (s) (equal? (hash-ref s 'on) base-id)) deps))
  (define rendered (render-fn new-fn))
  (check-true (string-contains? rendered "(base x y)"))
  (displayln "PASS 15 — add-function! resolves calls to existing functions"))

;; 16. Parsed function body evaluable via graph-eval
(fresh!)
(let ()
  (define fns (parse-program! "(defn multiply [x y]\n  (* x y))"))
  (define fn-id (first fns))
  (define params (get-ordered-params fn-id))
  (define body-id (get-body fn-id))
  (define env (extend-env
               (extend-env (empty-env)
                           (first params) (lit! 3))
               (second params) (lit! 4)))
  (define result (graph-eval body-id env))
  (check-equal? (node-value result) 12)
  (displayln "PASS 16 — parsed function body evaluable via graph-eval"))

;; 17. Multi-function: parse, link, evaluate across function boundary
(fresh!)
(let ()
  (define source
    "(defn helper [a b]\n  (+ a b))\n\n(defn caller [x y]\n  (+ (helper x y) 100))")
  (define fns (parse-program! source))
  (define helper-id (first fns))
  (define caller-id (second fns))
  (define ep (ctx-ref 'eval/param))
  (define eb (ctx-ref 'eval/body))
  (define (make-curried params body)
    (foldr (lambda (p inner)
             (define lam (entity!))
             (claim! lam (kind-pred) (value! "lambda"))
             (claim! lam ep p)
             (claim! lam eb inner)
             lam)
           body params))
  (define helper-lam
    (make-curried (get-ordered-params helper-id) (get-body helper-id)))
  (define caller-lam
    (make-curried (get-ordered-params caller-id) (get-body caller-id)))
  (define base-env (empty-env))
  (define env1 (extend-env base-env helper-id (lit! 'placeholder)))
  (define env2 (extend-env env1 caller-id (lit! 'placeholder)))
  (define helper-closure (graph-eval helper-lam env2))
  (define caller-closure (graph-eval caller-lam env2))
  (claim! env1 (ctx-ref 'eval/env-value) helper-closure)
  (claim! env2 (ctx-ref 'eval/env-value) caller-closure)
  (define call-expr (app! (app! (var! caller-id) (lit! 3)) (lit! 4)))
  (define result (graph-eval call-expr env2))
  (check-equal? (node-value result) 107)
  (displayln "PASS 17 — multi-function: parsed, linked, evaluated via graph-eval"))

;; 18. eval-function! — single function, success
(fresh!)
(let ()
  (define fns (parse-program! "(defn multiply [x y]\n  (* x y))"))
  (define fn-id (first fns))
  (define run-id (eval-function! fn-id '(3 4)))
  (check-equal? (resolve-value (node-ref run-id (run-status-pred))) "complete")
  (define result-node (node-ref run-id (run-result-pred)))
  (check-equal? (node-value result-node) 12)
  (check-true (> (resolve-value (node-ref run-id (fuel-used-pred))) 0))
  (check-equal? (resolve-value (node-ref run-id (fuel-limit-pred))) 10000)
  (check-equal? (node-ref run-id (run-root-pred)) fn-id)
  (displayln "PASS 18 — eval-function! single function success, run is queryable"))

;; 19. eval-function! — cross-function call
(fresh!)
(let ()
  (define source
    "(defn helper [a b]\n  (+ a b))\n\n(defn caller [x y]\n  (+ (helper x y) 100))")
  (define fns (parse-program! source))
  (define caller-id (second fns))
  (define run-id (eval-function! caller-id '(3 4)))
  (check-equal? (resolve-value (node-ref run-id (run-status-pred))) "complete")
  (define result-node (node-ref run-id (run-result-pred)))
  (check-equal? (node-value result-node) 107)
  (displayln "PASS 19 — eval-function! cross-function call, caller(3,4) = 107"))

;; 20. eval-function! — fuel exhaustion becomes queryable claim
(fresh!)
(let ()
  (define source
    "(defn self [x y]\n  (self x y))")
  (define fns (parse-program! source))
  (define fn-id (first fns))
  (define run-id (eval-function! fn-id '(1 2) #:fuel 50))
  (check-equal? (resolve-value (node-ref run-id (run-status-pred))) "incomplete")
  (check-equal? (resolve-value (node-ref run-id (run-reason-pred))) "fuel-exhausted")
  (check-not-false (node-ref run-id (run-error-node-pred)))
  (check-equal? (resolve-value (node-ref run-id (fuel-used-pred))) 50)
  (displayln "PASS 20 — eval-function! fuel exhaustion is queryable graph data"))

;; 21. eval-function! — error becomes queryable claim
(fresh!)
(let ()
  (define fns (parse-program! "(defn broken [x y]\n  (+ x y))"))
  (define fn-id (first fns))
  ;; Too many args: 2-arg fn applied to 3 values tries to apply a literal
  (define run-id (eval-function! fn-id '(1 2 3)))
  (check-equal? (resolve-value (node-ref run-id (run-status-pred))) "error")
  (check-not-false (node-ref run-id (run-reason-pred)))
  (displayln "PASS 21 — eval-function! error is queryable graph data"))

;; 22. eval-function! after rename — still evaluates correctly
(fresh!)
(let ()
  (define source
    "(defn compute [a b]\n  (* a b))\n\n(defn wrapper [x y]\n  (+ (compute x y) 10))")
  (define fns (parse-program! source))
  (define compute-id (first fns))
  (define wrapper-id (second fns))
  (rename! compute-id "calculate")
  (define run-id (eval-function! wrapper-id '(5 6)))
  (check-equal? (resolve-value (node-ref run-id (run-status-pred))) "complete")
  (check-equal? (node-value (node-ref run-id (run-result-pred))) 40)
  (displayln "PASS 22 — eval-function! works after rename"))

;; 23. eval-function! — multiple runs are independent queryable entities
(fresh!)
(let ()
  (define fns (parse-program! "(defn add [x y]\n  (+ x y))"))
  (define fn-id (first fns))
  (define run1 (eval-function! fn-id '(1 2)))
  (define run2 (eval-function! fn-id '(10 20)))
  (check-not-equal? run1 run2)
  (check-equal? (node-value (node-ref run1 (run-result-pred))) 3)
  (check-equal? (node-value (node-ref run2 (run-result-pred))) 30)
  (check-equal? (node-kind run1) "eval-run")
  (check-equal? (node-kind run2) "eval-run")
  (displayln "PASS 23 — multiple eval runs are independent queryable entities"))

(displayln "")
(displayln "All lang tests passed.")

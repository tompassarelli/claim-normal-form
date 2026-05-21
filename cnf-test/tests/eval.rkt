#lang racket

(require rackunit
         cnf/private/kernel
         cnf/private/datalog
         cnf/private/eval)

;; ══════════════════════════════════════════════════════════════════
;; Graph evaluator tests.
;;
;; Victory condition: construct and run a program that never existed
;; as a source file. The graph IS the program.
;; ══════════════════════════════════════════════════════════════════


;; --- Test 1: literal evaluates to itself ---

(reset-store!)
(reset-rules!)
(setup-eval!)

(let* ([five (lit! 5)]
       [env (empty-env)]
       [result (graph-eval five env)])
  (check-equal? (node-value result) 5)
  (displayln "PASS 1 — literal: 5 => 5"))


;; --- Test 2: binop 2 + 3 = 5 ---

(reset-store!)
(reset-rules!)
(setup-eval!)
(register-primitive! "+" +)

(let* ([expr (binop! "+" (lit! 2) (lit! 3))]
       [env (empty-env)]
       [result (graph-eval expr env)])
  (check-equal? (node-value result) 5)
  (displayln "PASS 2 — binop: 2 + 3 = 5"))


;; --- Test 3: nested binop (1 + 2) * 4 = 12 ---

(reset-store!)
(reset-rules!)
(setup-eval!)
(register-primitive! "+" +)
(register-primitive! "*" *)

(let* ([inner (binop! "+" (lit! 1) (lit! 2))]
       [outer (binop! "*" inner (lit! 4))]
       [env (empty-env)]
       [result (graph-eval outer env)])
  (check-equal? (node-value result) 12)
  (displayln "PASS 3 — nested: (1 + 2) * 4 = 12"))


;; --- Test 4: lambda + apply: ((λ x x) 42) = 42 (identity) ---

(reset-store!)
(reset-rules!)
(setup-eval!)

(let* ([env (empty-env)])
  (define-values (id-fn x-binding) (lam! "x" (var! 'placeholder)))
  ;; Need to build body that references x-binding.
  ;; Rebuild properly:
  (void))

;; Cleaner approach: build bottom-up
(reset-store!)
(reset-rules!)
(setup-eval!)

(let* ([x-bind (entity!)]
       [_ (begin (claim! x-bind (kind-pred) (value! "binding"))
                 (claim! x-bind (binding-name-pred) (value! "x")))]
       [body (var! x-bind)]
       [lam-node (entity!)]
       [_ (begin (claim! lam-node (kind-pred) (value! "lambda"))
                 (claim! lam-node (param-pred) x-bind)
                 (claim! lam-node (body-pred) body))]
       [app-node (app! lam-node (lit! 42))]
       [env (empty-env)]
       [result (graph-eval app-node env)])
  (check-equal? (node-value result) 42)
  (displayln "PASS 4 — identity: ((λ x x) 42) = 42"))


;; --- Test 5: ((λ x (+ x 1)) 5) = 6 — THE victory condition ---

(reset-store!)
(reset-rules!)
(setup-eval!)
(register-primitive! "+" +)

(let* ([x-bind (entity!)]
       [_ (begin (claim! x-bind (kind-pred) (value! "binding"))
                 (claim! x-bind (binding-name-pred) (value! "x")))]
       [body (binop! "+" (var! x-bind) (lit! 1))]
       [lam-node (entity!)]
       [_ (begin (claim! lam-node (kind-pred) (value! "lambda"))
                 (claim! lam-node (param-pred) x-bind)
                 (claim! lam-node (body-pred) body))]
       [app-node (app! lam-node (lit! 5))]
       [env (empty-env)]
       [result (graph-eval app-node env)])
  (check-equal? (node-value result) 6)
  (displayln "PASS 5 — ((λ x (+ x 1)) 5) = 6  *** THE PROOF ***"))


;; --- Test 6: let x = 10 in x + 20 = 30 ---

(reset-store!)
(reset-rules!)
(setup-eval!)
(register-primitive! "+" +)

(let* ([expr (let! "x" (lit! 10)
               (lambda (x-bind) (binop! "+" (var! x-bind) (lit! 20))))]
       [env (empty-env)]
       [result (graph-eval expr env)])
  (check-equal? (node-value result) 30)
  (displayln "PASS 6 — let x = 10 in x + 20 = 30"))


;; --- Test 7: if true 1 2 = 1 ---

(reset-store!)
(reset-rules!)
(setup-eval!)

(let* ([expr (if! (lit! #t) (lit! 1) (lit! 2))]
       [env (empty-env)]
       [result (graph-eval expr env)])
  (check-equal? (node-value result) 1)
  (displayln "PASS 7 — if true 1 2 = 1"))


;; --- Test 8: if false 1 2 = 2 ---

(reset-store!)
(reset-rules!)
(setup-eval!)

(let* ([expr (if! (lit! #f) (lit! 1) (lit! 2))]
       [env (empty-env)]
       [result (graph-eval expr env)])
  (check-equal? (node-value result) 2)
  (displayln "PASS 8 — if false 1 2 = 2"))


;; --- Test 9: nested lambda — ((λ x (λ y (+ x y))) 3 4) = 7 ---

(reset-store!)
(reset-rules!)
(setup-eval!)
(register-primitive! "+" +)

(let* ([x-bind (entity!)]
       [_ (begin (claim! x-bind (kind-pred) (value! "binding"))
                 (claim! x-bind (binding-name-pred) (value! "x")))]
       [y-bind (entity!)]
       [_ (begin (claim! y-bind (kind-pred) (value! "binding"))
                 (claim! y-bind (binding-name-pred) (value! "y")))]
       [inner-body (binop! "+" (var! x-bind) (var! y-bind))]
       [inner-lam (entity!)]
       [_ (begin (claim! inner-lam (kind-pred) (value! "lambda"))
                 (claim! inner-lam (param-pred) y-bind)
                 (claim! inner-lam (body-pred) inner-body))]
       [outer-lam (entity!)]
       [_ (begin (claim! outer-lam (kind-pred) (value! "lambda"))
                 (claim! outer-lam (param-pred) x-bind)
                 (claim! outer-lam (body-pred) inner-lam))]
       ;; ((λ x (λ y (+ x y))) 3) => closure, then apply to 4
       [app1 (app! outer-lam (lit! 3))]
       [app2 (app! app1 (lit! 4))]
       [env (empty-env)]
       [result (graph-eval app2 env)])
  (check-equal? (node-value result) 7)
  (displayln "PASS 9 — curried add: ((λ x (λ y (+ x y))) 3 4) = 7"))


;; --- Test 10: provenance — reductions are queryable ---

(reset-store!)
(reset-rules!)
(setup-eval!)
(register-primitive! "+" +)

(let* ([expr (binop! "+" (lit! 2) (lit! 3))]
       [env (empty-env)]
       [result (graph-eval expr env)])
  (check-equal? (node-value result) 5)
  ;; Query: what reduced to produce the result?
  (define reductions (current-claims-where #:p (reduced-to-pred) #:r result))
  (check-true (not (null? reductions)) "should have a reduction record")
  (define red-entity (list-ref (first reductions) 2))
  ;; The reduction should point back to the original expr
  (define from-claims (current-claims-where #:l red-entity #:p (reduced-from-pred)))
  (check-equal? (list-ref (first from-claims) 3) expr)
  ;; The reduction should name the rule
  (define rule-claims (current-claims-where #:l red-entity #:p (reduced-rule-pred)))
  (check-equal? (resolve-value (list-ref (first rule-claims) 3)) "+")
  (displayln "PASS 10 — provenance: reduction records are queryable claims"))


;; --- Test 11: the full proof — no source file ever existed ---

(reset-store!)
(reset-rules!)
(setup-eval!)
(register-primitive! "+" +)
(register-primitive! "*" *)
(register-primitive! "-" -)

;; Build: let double = (λ x (+ x x)) in double(double(3))
;; = double(6) = 12
(let* ([x-bind (entity!)]
       [_ (begin (claim! x-bind (kind-pred) (value! "binding"))
                 (claim! x-bind (binding-name-pred) (value! "x")))]
       [double-body (binop! "+" (var! x-bind) (var! x-bind))]
       [double-lam (entity!)]
       [_ (begin (claim! double-lam (kind-pred) (value! "lambda"))
                 (claim! double-lam (param-pred) x-bind)
                 (claim! double-lam (body-pred) double-body))]
       [expr (let! "double" double-lam
               (lambda (d-bind)
                 (app! (var! d-bind) (app! (var! d-bind) (lit! 3)))))]
       [env (empty-env)]
       [result (graph-eval expr env)])
  (check-equal? (node-value result) 12)
  ;; Count all reduction records in the graph
  (define all-reds (current-claims-where #:p (reduced-from-pred)))
  (check-true (> (length all-reds) 3) "should have multiple reduction steps")
  (displayln "PASS 11 — let double = (λ x (+ x x)) in double(double(3)) = 12"))


;; --- Test 12: letrec — factorial(5) = 120 ---

(reset-store!)
(reset-rules!)
(setup-eval!)
(register-primitive! "+" +)
(register-primitive! "*" *)
(register-primitive! "-" -)
(register-primitive! "=" =)

(let* ([expr
        (letrec! "factorial"
          (lambda (fact-bind)
            (define n-bind (entity!))
            (claim! n-bind (kind-pred) (value! "binding"))
            (claim! n-bind (binding-name-pred) (value! "n"))
            (define body
              (if! (binop! "=" (var! n-bind) (lit! 0))
                   (lit! 1)
                   (binop! "*" (var! n-bind)
                           (app! (var! fact-bind)
                                 (binop! "-" (var! n-bind) (lit! 1))))))
            (define lam (entity!))
            (claim! lam (kind-pred) (value! "lambda"))
            (claim! lam (param-pred) n-bind)
            (claim! lam (body-pred) body)
            lam)
          (lambda (fact-bind)
            (app! (var! fact-bind) (lit! 5))))]
       [env (empty-env)]
       [result (graph-eval expr env)])
  (check-equal? (node-value result) 120)
  (displayln "PASS 12 — letrec: factorial(5) = 120"))


;; --- Test 13: letrec — countdown(10) = 0 ---

(reset-store!)
(reset-rules!)
(setup-eval!)
(register-primitive! "-" -)
(register-primitive! "=" =)

(let* ([expr
        (letrec! "countdown"
          (lambda (cd-bind)
            (define n-bind (entity!))
            (claim! n-bind (kind-pred) (value! "binding"))
            (claim! n-bind (binding-name-pred) (value! "n"))
            (define body
              (if! (binop! "=" (var! n-bind) (lit! 0))
                   (var! n-bind)
                   (app! (var! cd-bind)
                         (binop! "-" (var! n-bind) (lit! 1)))))
            (define lam (entity!))
            (claim! lam (kind-pred) (value! "lambda"))
            (claim! lam (param-pred) n-bind)
            (claim! lam (body-pred) body)
            lam)
          (lambda (cd-bind)
            (app! (var! cd-bind) (lit! 10))))]
       [env (empty-env)]
       [result (graph-eval expr env)])
  (check-equal? (node-value result) 0)
  (displayln "PASS 13 — letrec: countdown(10) = 0"))


;; --- Test 14: fuel exhaustion — infinite loop is bounded ---

(reset-store!)
(reset-rules!)
(setup-eval!)

(let* ([expr
        (letrec! "loop"
          (lambda (loop-bind)
            (define x-bind (entity!))
            (claim! x-bind (kind-pred) (value! "binding"))
            (claim! x-bind (binding-name-pred) (value! "x"))
            (define body (app! (var! loop-bind) (var! x-bind)))
            (define lam (entity!))
            (claim! lam (kind-pred) (value! "lambda"))
            (claim! lam (param-pred) x-bind)
            (claim! lam (body-pred) body)
            lam)
          (lambda (loop-bind)
            (app! (var! loop-bind) (lit! 1))))]
       [env (empty-env)])
  (check-exn exn:fuel?
    (lambda () (graph-eval expr env #:fuel 50)))
  (displayln "PASS 14 — infinite loop exhausts fuel without hanging"))


;; --- Test 15: fuel-exhaustion claims are queryable ---

(reset-store!)
(reset-rules!)
(setup-eval!)

(let* ([expr
        (letrec! "loop"
          (lambda (loop-bind)
            (define x-bind (entity!))
            (claim! x-bind (kind-pred) (value! "binding"))
            (claim! x-bind (binding-name-pred) (value! "x"))
            (define body (app! (var! loop-bind) (var! x-bind)))
            (define lam (entity!))
            (claim! lam (kind-pred) (value! "lambda"))
            (claim! lam (param-pred) x-bind)
            (claim! lam (body-pred) body)
            lam)
          (lambda (loop-bind)
            (app! (var! loop-bind) (lit! 1))))]
       [env (empty-env)]
       [incomplete-id
        (with-handlers ([exn:fuel? (lambda (e) (exn:fuel-node-id e))])
          (graph-eval expr env #:fuel 50)
          #f)])
  (check-not-false incomplete-id)
  ;; The incomplete node exists in the graph
  (check-equal? (node-kind incomplete-id) "incomplete")
  ;; A reduction record links to it with rule "fuel-exhausted"
  (define reds (current-claims-where #:p (reduced-to-pred) #:r incomplete-id))
  (check-true (not (null? reds)))
  (define red-entity (list-ref (first reds) 2))
  (define rule-claims (current-claims-where #:l red-entity #:p (reduced-rule-pred)))
  (check-equal? (resolve-value (list-ref (first rule-claims) 3)) "fuel-exhausted")
  ;; Fuel budget is recorded on the incomplete node
  (define limit-cs (current-claims-where #:l incomplete-id #:p (fuel-limit-pred)))
  (check-equal? (resolve-value (list-ref (first limit-cs) 3)) 50)
  (define used-cs (current-claims-where #:l incomplete-id #:p (fuel-used-pred)))
  (check-equal? (resolve-value (list-ref (first used-cs) 3)) 50)
  (displayln "PASS 15 — fuel-exhaustion is a queryable claim with budget details"))


(displayln "")
(displayln "All eval tests passed.")
(displayln "The graph is the program. No source file was involved.")

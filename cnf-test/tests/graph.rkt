#lang racket

(require rackunit
         cnf/private/kernel
         cnf/private/datalog
         cnf/private/eval
         cnf/private/graph)

;; 1. Semantic rename — rendered output changes, object references don't
(reset-store!)
(reset-rules!)
(setup-eval!)
(setup-graph!)

(let* ([fn-1 (entity!)]
       [calls-pred (named! "calls")]
       [covers-pred (named! "covers")]
       [describes-pred (named! "describes")]
       [_ (give-name! fn-1 "calculate-pay")]
       [call-1 (entity!)]
       [test-1 (entity!)]
       [doc-1 (entity!)]
       [c-call (claim! call-1 calls-pred fn-1)]
       [c-test (claim! test-1 covers-pred fn-1)]
       [c-doc (claim! doc-1 describes-pred fn-1)])
  (check-equal? (render-ref fn-1) "calculate-pay")
  (rename! fn-1 "compute-pay")
  (check-equal? (render-ref fn-1) "compute-pay")
  (define call-claims (current-claims-where #:l call-1 #:p calls-pred))
  (check-equal? (list-ref (first call-claims) 3) fn-1)
  (define test-claims (current-claims-where #:l test-1 #:p covers-pred))
  (check-equal? (list-ref (first test-claims) 3) fn-1)
  (define doc-claims (current-claims-where #:l doc-1 #:p describes-pred))
  (check-equal? (list-ref (first doc-claims) 3) fn-1)
  (displayln "PASS 1 — semantic rename changes render, not references"))

;; 2. Old name still queryable after rename
(reset-store!)
(reset-rules!)
(setup-eval!)
(setup-graph!)

(let* ([fn-1 (entity!)]
       [_ (give-name! fn-1 "calculate-pay")])
  (rename! fn-1 "compute-pay")
  (check-equal? (current-name fn-1) "compute-pay")
  (define all-name-claims (claims-where #:l fn-1 #:p (name-pred)))
  (check-equal? (length all-name-claims) 2)
  (define name-vals
    (map (λ (c) (resolve-value (list-ref c 3))) all-name-claims))
  (check-not-false (member "calculate-pay" name-vals))
  (check-not-false (member "compute-pay" name-vals))
  (displayln "PASS 2 — old name still queryable after rename"))

;; 3. Structural dependency derived from graph
(reset-store!)
(reset-rules!)
(setup-eval!)
(setup-graph!)
(register-primitive! "+" +)
(register-primitive! "*" *)

(let* ([inner (binop! "+" (lit! 1) (lit! 2))]
       [outer (binop! "*" inner (lit! 4))])
  (define deps (query (expr-depends-on (? x) (? dep))))
  (check-true
   (ormap (λ (s) (and (equal? (hash-ref s 'x) outer)
                       (equal? (hash-ref s 'dep) inner)))
          deps))
  (displayln "PASS 3 — structural dependency derived from graph"))

;; 4. Transitive affectedness query
(reset-store!)
(reset-rules!)
(setup-eval!)
(setup-graph!)
(register-primitive! "+" +)
(register-primitive! "*" *)

(let* ([inner (binop! "+" (lit! 1) (lit! 2))]
       [outer (binop! "*" inner (lit! 4))]
       [independent (binop! "+" (lit! 10) (lit! 20))])
  (define aff (affected-by inner))
  (check-not-false (member inner aff))
  (check-not-false (member outer aff))
  (check-false (member independent aff))
  (displayln "PASS 4 — transitive affectedness, independent node excluded"))

;; 5. Evaluation + provenance on graph expressions
(reset-store!)
(reset-rules!)
(setup-eval!)
(setup-graph!)
(register-primitive! "+" +)
(register-primitive! "*" *)

(let* ([inner (binop! "+" (lit! 1) (lit! 2))]
       [outer (binop! "*" inner (lit! 4))]
       [env (empty-env)]
       [result (graph-eval outer env)])
  (check-equal? (node-value result) 12)
  ;; Check provenance exists
  (define reds (current-claims-where #:p (reduced-from-pred)))
  (check-true (>= (length reds) 2))
  (displayln "PASS 5 — evaluation with provenance on graph expressions"))

;; 6. Reductions are queryable — which rule produced the result?
(reset-store!)
(reset-rules!)
(setup-eval!)
(setup-graph!)
(register-primitive! "+" +)

(let* ([expr (binop! "+" (lit! 2) (lit! 3))]
       [env (empty-env)]
       [result (graph-eval expr env)])
  (check-equal? (node-value result) 5)
  (define reds (current-claims-where #:p (reduced-to-pred) #:r result))
  (check-true (not (null? reds)))
  (define red-entity (list-ref (first reds) 2))
  (define rule-claims (current-claims-where #:l red-entity #:p (reduced-rule-pred)))
  (check-equal? (resolve-value (list-ref (first rule-claims) 3)) "+")
  (displayln "PASS 6 — reductions are queryable claims"))

(displayln "")
(displayln "All graph tests passed.")

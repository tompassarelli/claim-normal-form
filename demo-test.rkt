#lang racket

(require rackunit
         "cnf.rkt"
         "datalog.rkt"
         "eval.rkt"
         "graph.rkt")

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
  ;; Rename
  (rename! fn-1 "compute-pay")
  (check-equal? (render-ref fn-1) "compute-pay")
  ;; References still point to the same identity
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
  ;; Old name claim still exists in the raw store
  (define all-name-claims (claims-where #:l fn-1 #:p (name-pred)))
  (check-equal? (length all-name-claims) 2)
  (define name-vals
    (map (λ (c) (resolve-value (list-ref c 3))) all-name-claims))
  (check-not-false (member "calculate-pay" name-vals))
  (check-not-false (member "compute-pay" name-vals))
  (displayln "PASS 2 — old name still queryable after rename"))

;; 3. Structural dependency derived from graph, not declared
(reset-store!)
(reset-rules!)
(setup-eval!)
(setup-graph!)

(let* ([add-op (named! "add")]
       [mul-op (named! "multiply")]
       [one (value! 1)]
       [two (value! 2)]
       [four (value! 4)]
       [expr-1 (expr! add-op one two)]
       [expr-2 (expr! mul-op expr-1 four)])
  ;; No manual depends-on claims — derived from expression structure
  (define deps (query (expr-depends-on (? x) (? dep))))
  (check-true
   (ormap (λ (s) (and (equal? (hash-ref s 'x) expr-2)
                       (equal? (hash-ref s 'dep) expr-1)))
          deps))
  (displayln "PASS 3 — structural dependency derived from graph"))

;; 4. Transitive affectedness query
(reset-store!)
(reset-rules!)
(setup-eval!)
(setup-graph!)

(let* ([add-op (named! "add")]
       [mul-op (named! "multiply")]
       [one (value! 1)]
       [two (value! 2)]
       [four (value! 4)]
       [ten (value! 10)]
       [twenty (value! 20)]
       [expr-1 (expr! add-op one two)]
       [expr-2 (expr! mul-op expr-1 four)]
       [expr-3 (expr! add-op ten twenty)])
  (define aff (affected-by expr-1))
  (check-not-false (member expr-1 aff))
  (check-not-false (member expr-2 aff))
  (check-false (member expr-3 aff))
  (displayln "PASS 4 — transitive affectedness, independent node excluded"))

;; 5. Incremental recompute updates affected downstream results
(reset-store!)
(reset-rules!)
(setup-eval!)
(setup-graph!)

(let* ([add-op (named! "add")]
       [mul-op (named! "multiply")]
       [one (value! 1)]
       [two (value! 2)]
       [four (value! 4)]
       [expr-1 (expr! add-op one two)]
       [expr-2 (expr! mul-op expr-1 four)]
       [env (entity!)])
  (register-primitive! add-op +)
  (register-primitive! mul-op *)
  (define evs (run! env))
  (check-equal? (eval-result (first evs)) 3)
  (check-equal? (eval-result (second evs)) 12)
  ;; Change expr-1 right operand: 2 -> 5
  (define five (value! 5))
  (change-operand! expr-1 (right-pred) two five)
  (define-values (affected-ids new-evs) (recompute-affected! env expr-1))
  (check-equal? (length new-evs) 2)
  (check-equal? (eval-result (first new-evs)) 6)
  (check-equal? (eval-result (second new-evs)) 24)
  (displayln "PASS 5 — incremental recompute updates downstream"))

;; 6. Unaffected node not recomputed
(reset-store!)
(reset-rules!)
(setup-eval!)
(setup-graph!)

(let* ([add-op (named! "add")]
       [mul-op (named! "multiply")]
       [one (value! 1)]
       [two (value! 2)]
       [four (value! 4)]
       [ten (value! 10)]
       [twenty (value! 20)]
       [expr-1 (expr! add-op one two)]
       [expr-2 (expr! mul-op expr-1 four)]
       [expr-3 (expr! add-op ten twenty)]
       [env (entity!)])
  (register-primitive! add-op +)
  (register-primitive! mul-op *)
  (define evs (run! env))
  (check-equal? (length evs) 3)
  ;; Capture expr-3's eval event before recompute
  (define expr-3-ev-before
    (current-claims-where #:p (evaluated-pred) #:r expr-3))
  ;; Change expr-1 right: 2 -> 5
  (change-operand! expr-1 (right-pred) two (value! 5))
  (define-values (affected-ids new-evs) (recompute-affected! env expr-1))
  ;; Only expr-1 and expr-2 recomputed
  (check-equal? (length new-evs) 2)
  (check-false (member expr-3 affected-ids))
  ;; expr-3's eval event unchanged
  (define expr-3-ev-after
    (current-claims-where #:p (evaluated-pred) #:r expr-3))
  (check-equal? expr-3-ev-before expr-3-ev-after)
  (displayln "PASS 6 — unaffected node not recomputed"))

;; 7. Old eval events preserved as provenance
(reset-store!)
(reset-rules!)
(setup-eval!)
(setup-graph!)

(let* ([add-op (named! "add")]
       [one (value! 1)]
       [two (value! 2)]
       [expr-1 (expr! add-op one two)]
       [env (entity!)])
  (register-primitive! add-op +)
  (define evs (run! env))
  (define old-ev (first evs))
  (check-equal? (eval-result old-ev) 3)
  ;; Change and recompute
  (change-operand! expr-1 (right-pred) two (value! 5))
  (define-values (affected-ids new-evs) (recompute-affected! env expr-1))
  (define new-ev (first new-evs))
  (check-equal? (eval-result new-ev) 6)
  ;; Old eval event's result still queryable via raw claims-where
  (define old-result-claims (claims-where #:l old-ev #:p (result-pred)))
  (check-false (null? old-result-claims))
  (check-equal? (resolve-value (list-ref (first old-result-claims) 3)) 3)
  ;; But old event is NOT current
  (define old-current (current-claims-where #:l old-ev #:p (evaluated-pred)))
  (check-true (null? old-current))
  (displayln "PASS 7 — old eval events preserved as provenance"))

;; 8. Affected-only: unevaluated independent expr stays unevaluated after recompute
(reset-store!)
(reset-rules!)
(setup-eval!)
(setup-graph!)

(let* ([add-op (named! "add")]
       [mul-op (named! "multiply")]
       [one (value! 1)]
       [two (value! 2)]
       [four (value! 4)]
       [expr-1 (expr! add-op one two)]
       [expr-2 (expr! mul-op expr-1 four)]
       [env (entity!)])
  (register-primitive! add-op +)
  (register-primitive! mul-op *)
  ;; Evaluate expr-1 and expr-2
  (define evs (run! env))
  (check-equal? (length evs) 2)
  ;; Now add an independent expression that is ready but NOT yet evaluated
  (define ten (value! 10))
  (define twenty (value! 20))
  (define expr-3 (expr! add-op ten twenty))
  ;; Change expr-1 and recompute affected only
  (change-operand! expr-1 (right-pred) two (value! 5))
  (define-values (affected-ids new-evs) (recompute-affected! env expr-1))
  ;; expr-1 and expr-2 recomputed
  (check-equal? (length new-evs) 2)
  ;; expr-3 must still be unevaluated — not touched by affected-only recompute
  (check-false (member expr-3 affected-ids))
  (define expr-3-ev (current-claims-where #:p (evaluated-pred) #:r expr-3))
  (check-true (null? expr-3-ev))
  (displayln "PASS 8 — unevaluated independent expr stays unevaluated"))

(displayln "")
(displayln "All demo tests passed.")

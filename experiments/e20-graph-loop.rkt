#lang racket

(require cnf/private/kernel
         cnf/private/datalog
         (only-in cnf/private/eval
                  setup-eval! graph-eval empty-env extend-env
                  node-value node-kind node-ref
                  kind-pred run-root-pred run-status-pred
                  run-result-pred run-reason-pred run-error-node-pred
                  fuel-limit-pred fuel-used-pred
                  exn:fuel exn:fuel-node-id)
         cnf/private/graph
         cnf/private/lang)

;; ══════════════════════════════════════════════════════════════════
;; E20: Graph-Native Agent Loop
;;
;; The question: does the closed loop give an agent leverage
;; it doesn't have through files?
;;
;; One program, 10 steps. Each step shows what the graph agent does
;; and what a text agent would need to do instead.
;; ══════════════════════════════════════════════════════════════════

(define (fresh!)
  (reset-store!)
  (setup-eval!)
  (setup-graph!)
  (setup-lang!)
  (materialize!))

(define program-source
  (string-append
   "(defn base-rate [hours rate]\n  (* hours rate))\n\n"
   "(defn overtime [hours rate]\n  (* (base-rate hours rate) 2))\n\n"
   "(defn total-pay [base extra]\n  (+ base extra))\n\n"
   "(defn tax-amount [income pct]\n  (/ (* income pct) 100))\n\n"
   "(defn after-tax [income pct]\n  (- income (tax-amount income pct)))"))

(define (separator)
  (displayln (make-string 64 #\─)))

(define (step n title)
  (newline)
  (separator)
  (printf "STEP ~a: ~a\n" n title)
  (separator))

;; ──────────────────────────────────────────────────────────────
;; Run it
;; ──────────────────────────────────────────────────────────────

(fresh!)

;; STEP 1: Parse
(step 1 "Parse program into the graph")
(define fns (parse-program! program-source))
(materialize!)
(printf "  Parsed ~a functions:\n" (length fns))
(for ([f (in-list fns)])
  (printf "    ~a: ~a\n" f (render-ref f)))
(printf "  Objects: ~a, Claims: ~a\n"
        (length (all-objects)) (length (claims-where)))
(displayln "")
(displayln "  GRAPH: parse_program → 5 entity IDs, graph built")
(displayln "  TEXT:  read source file into context window")
(displayln "  DELTA: same effort, different representation")

;; STEP 2: Query dependencies
(step 2 "Query cross-function dependencies")
(define deps (query (fn-depends-on (? caller) (? callee))))
(printf "  fn-depends-on results (~a):\n" (length deps))
(for ([d (in-list deps)])
  (printf "    ~a → ~a\n"
          (render-ref (hash-ref d 'caller))
          (render-ref (hash-ref d 'callee))))
(displayln "")
(displayln "  GRAPH: query fn-depends-on → instant, correct, transitive")
(displayln "  TEXT:  grep for function names in other functions")
(displayln "  DELTA: graph is structural; grep finds string matches, not calls")

;; STEP 3: Evaluate base-rate
(step 3 "Evaluate base-rate(40, 25)")
(define base-rate-id (first fns))
(define run1 (eval-function! base-rate-id '(40 25)))
(define run1-status (resolve-value (node-ref run1 (run-status-pred))))
(define run1-result (node-value (node-ref run1 (run-result-pred))))
(define run1-fuel (resolve-value (node-ref run1 (fuel-used-pred))))
(printf "  Run: ~a\n" run1)
(printf "  Status: ~a\n" run1-status)
(printf "  Result: ~a  (expected: 1000)\n" run1-result)
(printf "  Fuel: ~a used\n" run1-fuel)
(displayln "")
(displayln "  GRAPH: evaluate → run entity with result, fuel, provenance")
(displayln "  TEXT:  mental math or write a test script")
(displayln "  DELTA: graph records the run as queryable data")

;; STEP 4: Evaluate after-tax (cross-function)
(step 4 "Evaluate after-tax(1500, 20) — crosses function boundaries")
(define after-tax-id (fifth fns))
(define run2 (eval-function! after-tax-id '(1500 20)))
(define run2-status (resolve-value (node-ref run2 (run-status-pred))))
(define run2-result (node-value (node-ref run2 (run-result-pred))))
(define run2-fuel (resolve-value (node-ref run2 (fuel-used-pred))))
(printf "  Run: ~a\n" run2)
(printf "  Status: ~a\n" run2-status)
(printf "  Result: ~a  (expected: 1200)\n" run2-result)
(printf "  Fuel: ~a used\n" run2-fuel)
(printf "  Trace: after-tax calls tax-amount, which uses builtins * and /\n")
(displayln "")
(displayln "  GRAPH: evaluate → result + provenance across function boundary")
(displayln "  TEXT:  same mental math, but no record of the evaluation")

;; STEP 5: Rename base-rate → hourly-rate
(step 5 "Rename base-rate → hourly-rate")
(void (rename! base-rate-id "hourly-rate"))
(printf "  Entity ~a is now: ~a\n" base-rate-id (render-ref base-rate-id))
(define overtime-id (second fns))
(define overtime-rendered (render-fn overtime-id))
(printf "  overtime now renders as:\n    ~a\n"
        (string-replace overtime-rendered "\n" "\n    "))
(define overtime-has-hourly?
  (string-contains? overtime-rendered "hourly-rate"))
(define overtime-has-base?
  (string-contains? overtime-rendered "base-rate"))
(printf "  Call site updated: ~a  (old name gone: ~a)\n"
        overtime-has-hourly? (not overtime-has-base?))
(displayln "")
(displayln "  GRAPH: rename → 1 operation, all call sites update automatically")
(displayln "  TEXT:  find-and-replace 'base-rate' → 'hourly-rate'")
(displayln "  DELTA: graph rename is semantic (entity-level);")
(displayln "         text rename is textual (risks false positives in strings/comments)")

;; STEP 6: Evaluate overtime after rename
(step 6 "Evaluate overtime(10, 25) — verify rename didn't break anything")
(define run3 (eval-function! overtime-id '(10 25)))
(define run3-status (resolve-value (node-ref run3 (run-status-pred))))
(define run3-result (node-value (node-ref run3 (run-result-pred))))
(printf "  Status: ~a\n" run3-status)
(printf "  Result: ~a  (expected: 500 = hourly-rate(10,25) * 2 = 250 * 2)\n"
        run3-result)
(displayln "")
(displayln "  GRAPH: evaluate → proves rename preserved semantics")
(displayln "  TEXT:  re-run tests (if they exist)")
(displayln "  DELTA: graph agent verified in one tool call; text agent needs test infrastructure")

;; STEP 7: Add a new function
(step 7 "Add discounted-pay that calls after-tax")
(define new-fn
  (add-function! "(defn discounted-pay [income discount]\n  (- (after-tax income 20) discount))"))
(materialize!)
(printf "  New function: ~a (~a)\n" (render-ref new-fn) new-fn)
(define new-deps (query (fn-depends-on new-fn (? on))))
(printf "  Dependencies: ~a\n"
        (string-join (map (lambda (s) (render-ref (hash-ref s 'on))) new-deps) ", "))
(displayln "")
(displayln "  GRAPH: add_function → entity created, deps auto-derived")
(displayln "  TEXT:  append to file, re-grep for dependencies")
(displayln "  DELTA: graph incrementally updates matview; text re-analyzes from scratch")

;; STEP 8: Evaluate the new function
(step 8 "Evaluate discounted-pay(1500, 100)")
(define run4 (eval-function! new-fn '(1500 100)))
(define run4-status (resolve-value (node-ref run4 (run-status-pred))))
(define run4-result (node-value (node-ref run4 (run-result-pred))))
(printf "  Status: ~a\n" run4-status)
(printf "  Result: ~a  (expected: 1100 = after-tax(1500,20) - 100 = 1200 - 100)\n"
        run4-result)
(displayln "")
(displayln "  GRAPH: evaluate new function → works, crosses 3 function boundaries")
(displayln "  TEXT:  manual trace through 3 levels of calls")

;; STEP 9: Introduce a bug — division by zero
(step 9 "Break it: modify tax-amount to divide by zero")
(define tax-amount-id (fourth fns))
(void (modify-function! "tax-amount" "(defn tax-amount [income pct]\n  (/ (* income pct) 0))"))
(materialize!)
(printf "  tax-amount now: ~a\n"
        (string-replace (render-fn tax-amount-id) "\n" "\n    "))
(define run5 (eval-function! new-fn '(1500 100)))
(define run5-status (resolve-value (node-ref run5 (run-status-pred))))
(define run5-reason (resolve-value (node-ref run5 (run-reason-pred))))
(printf "  Evaluate discounted-pay(1500, 100):\n")
(printf "    Status: ~a\n" run5-status)
(printf "    Reason: ~a\n" run5-reason)
(printf "    Run entity: ~a (queryable)\n" run5)
(displayln "")
(displayln "  GRAPH: evaluate → error recorded as graph data")
(displayln "         run-status = error, run-reason = division by zero")
(displayln "         agent can query: which runs failed? what was the error?")
(displayln "  TEXT:  run program, read stack trace, parse error message")
(displayln "  DELTA: graph error is structured and queryable;")
(displayln "         text error is an opaque string in stderr")

;; STEP 10: Fix and verify
(step 10 "Fix the bug, re-evaluate")
(void (modify-function! "tax-amount" "(defn tax-amount [income pct]\n  (/ (* income pct) 100))"))
(materialize!)
(printf "  tax-amount fixed: ~a\n"
        (string-replace (render-fn tax-amount-id) "\n" "\n    "))
(define run6 (eval-function! new-fn '(1500 100)))
(define run6-status (resolve-value (node-ref run6 (run-status-pred))))
(define run6-result (node-value (node-ref run6 (run-result-pred))))
(printf "  Evaluate discounted-pay(1500, 100):\n")
(printf "    Status: ~a\n" run6-status)
(printf "    Result: ~a  (expected: 1100)\n" run6-result)
(displayln "")
(displayln "  GRAPH: modify + evaluate → fixed, result correct")
(displayln "  TEXT:  edit file + re-run test")
(displayln "  DELTA: same effort for the fix; graph retains error history")

;; Summary
(newline)
(separator)
(displayln "SUMMARY")
(separator)
(newline)

;; Count eval runs
(define all-runs
  (current-claims-where #:p (run-status-pred)))
(printf "Total eval runs in graph: ~a\n" (length all-runs))
(for ([c (in-list all-runs)])
  (define run-id (list-ref c 2))
  (define status (resolve-value (list-ref c 3)))
  (define root (node-ref run-id (run-root-pred)))
  (define root-name (if root (render-ref root) "?"))
  (define result-node (node-ref run-id (run-result-pred)))
  (define result-val (and result-node (node-value result-node)))
  (printf "  ~a: ~a(~a) → ~a~a\n"
          run-id root-name status
          (if result-val (format "~a" result-val) "—")
          (let ([reason (resolve-value (node-ref run-id (run-reason-pred)))])
            (if reason (format " [~a]" reason) ""))))

(newline)
(displayln "The graph retained every evaluation as queryable data.")
(displayln "Success, failure, provenance, fuel — all facts in the same graph")
(displayln "as the program itself.")
(newline)
(displayln "What the graph agent has that the text agent doesn't:")
(displayln "  1. Structural dependency queries (not grep)")
(displayln "  2. Semantic rename (not find-and-replace)")
(displayln "  3. Evaluation as graph data (not opaque output)")
(displayln "  4. Error diagnosis as structured claims (not stderr)")
(displayln "  5. Incremental mutation with automatic matview updates")
(displayln "  6. Full execution history queryable after the fact")

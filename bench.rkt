#lang racket

(require "cnf.rkt" "datalog.rkt" "eval.rkt" "graph.rkt")

;; Benchmark: indexed affected-only recompute
;;
;; Setup:
;;   - 1 chain of 5 dependent expressions (affected)
;;   - 100 independent expressions (unaffected)
;;   - Change one input, recompute only affected chain
;;   - Prove unaffected nodes untouched
;;   - Time affected-only vs full recompute

(define N 100)

(define (timed msg thunk)
  (collect-garbage)
  (collect-garbage)
  (define start (current-inexact-milliseconds))
  (define result (thunk))
  (define elapsed (- (current-inexact-milliseconds) start))
  (printf "  ~a: ~a ms\n" msg (~r elapsed #:precision 1))
  result)

(reset-store!)
(reset-rules!)
(setup-eval!)
(setup-graph!)

(define add-op (named! "add"))
(define mul-op (named! "multiply"))
(register-primitive! add-op +)
(register-primitive! mul-op *)

;; --- Build the affected chain ---

(define one (value! 1))
(define two (value! 2))
(define v10 (value! 10))
(define v100 (value! 100))
(define v3 (value! 3))

(define e1 (expr! add-op one two))
(define e2 (expr! add-op e1 v10))
(define e3 (expr! mul-op e2 two))
(define e4 (expr! add-op e3 v100))
(define e5 (expr! mul-op e4 v3))

;; --- Build N independent expressions ---

(printf "\nBuilding graph...\n")
(define independent-exprs
  (for/list ([i (in-range N)])
    (expr! add-op (value! i) (value! (+ i 1)))))

(printf "  ~a independent + 5-deep chain = ~a total expressions\n"
        N (+ N 5))
(printf "  total claims: ~a\n" (length (claims-where)))
(printf "  total objects: ~a\n" (length (all-objects)))

;; --- Initial evaluation ---

(define env (entity!))

(printf "\nInitial evaluation...\n")
(define all-evs
  (timed (format "evaluate all ~a expressions" (+ N 5))
    (λ () (run! env))))

(printf "  eval events: ~a\n" (length all-evs))

(define (expr-result-val expr-id)
  (define cs (current-claims-where #:p (evaluated-pred) #:r expr-id))
  (and (not (null? cs))
       (eval-result (list-ref (first cs) 2))))

(printf "  chain: e1=~a e2=~a e3=~a e4=~a e5=~a\n"
        (expr-result-val e1) (expr-result-val e2) (expr-result-val e3)
        (expr-result-val e4) (expr-result-val e5))

;; --- Affected-only recompute ---

(printf "\nChange: e1 right operand 2 -> 7\n")
(define seven (value! 7))
(void (change-operand! e1 (right-pred) two seven))

(printf "\nAffected-only recompute...\n")
(define affected-result
  (timed (format "recompute affected only (5 of ~a)" (+ N 5))
    (λ ()
      (define-values (ids evs) (recompute-affected! env e1))
      (list ids evs))))

(define affected-ids (first affected-result))
(define new-evs (second affected-result))

(printf "  affected: ~a expressions\n" (length affected-ids))
(printf "  new eval events: ~a\n" (length new-evs))
(printf "  chain: e1=~a e2=~a e3=~a e4=~a e5=~a\n"
        (expr-result-val e1) (expr-result-val e2) (expr-result-val e3)
        (expr-result-val e4) (expr-result-val e5))

;; --- Verify unaffected nodes ---

(define unaffected-still-evaluated
  (for/sum ([expr-id (in-list independent-exprs)])
    (if (not (null? (current-claims-where #:p (evaluated-pred) #:r expr-id)))
        1 0)))

(printf "\n  unaffected still evaluated: ~a / ~a\n"
        unaffected-still-evaluated N)

(define spot-ok
  (for/and ([expr-id (in-list (take independent-exprs 10))]
            [i (in-range 10)])
    (equal? (expr-result-val expr-id) (+ i (+ i 1)))))
(printf "  spot-check first 10: ~a\n" (if spot-ok "correct" "WRONG"))

;; --- Full run! for comparison ---

(printf "\nComparison: invalidate chain again, run WITHOUT #:only...\n")
(void (change-operand! e1 (right-pred) seven (value! 9)))
(for ([eid (in-list (affected-by e1))])
  (invalidate-eval-events! eid))

(define full-evs
  (timed "full run! (no filter)"
    (λ () (run! env))))

(printf "  eval events: ~a (only affected, since others still have current events)\n"
        (length full-evs))

(printf "\nDone.\n")

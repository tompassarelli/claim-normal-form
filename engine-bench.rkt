#lang racket

(require "cnf.rkt" "datalog.rkt" "eval.rkt" "graph.rkt" "lang.rkt")

;; Engine benchmark: CNF graph operations vs text-based equivalents.
;;
;; Generates programs at different scales and measures:
;; 1. Parse (text -> claims)
;; 2. Dependency query (Datalog)
;; 3. Rename + render one function (the agent use case)
;; 4. Render all functions
;; 5. Text baseline: string-replace across all source strings

(define (generate-source n)
  (define ops '("+" "-" "*"))
  (define (pick-op i) (list-ref ops (modulo i (length ops))))
  (string-join
   (for/list ([i (in-range n)])
     (define name (format "f~a" i))
     (if (= i 0)
         (format "(defn ~a [a b]\n  (~a a b))" name (pick-op i))
         (let ([callee (format "f~a" (modulo (sub1 i) i))]
               [op (pick-op i)])
           (format "(defn ~a [a b]\n  (~a (~a a b) b))" name op callee))))
   "\n\n"))

(define (time-ms thunk)
  (define t0 (current-inexact-milliseconds))
  (define result (thunk))
  (define t1 (current-inexact-milliseconds))
  (values result (- t1 t0)))

(define (run-benchmark n)
  (printf "\n--- N = ~a functions ---\n" n)
  (define source (generate-source n))

  ;; Setup
  (reset-store!)
  (setup-eval!)
  (setup-graph!)
  (setup-lang!)

  ;; 1. Parse
  (define-values (fns parse-ms) (time-ms (lambda () (parse-program! source))))
  (define total-objects (length (all-objects)))
  (define total-claims (length (claims-where)))
  (printf "  Parse:           ~a ms  (~a objects, ~a claims)\n"
          (~r parse-ms #:precision 1) total-objects total-claims)

  ;; 2. Dependency query
  (define-values (deps dep-ms)
    (time-ms (lambda () (query (fn-depends-on (? caller) (? callee))))))
  (printf "  Dependency query: ~a ms  (~a deps found)\n"
          (~r dep-ms #:precision 1) (length deps))

  ;; 3. Rename + render one (agent scenario: change name, check one call site)
  (define-values (_r1 rename-one-ms)
    (time-ms (lambda ()
      (rename! (first fns) "renamed-f0")
      (render-fn (last fns)))))
  (printf "  Rename+render 1: ~a ms\n" (~r rename-one-ms #:precision 1))

  ;; 4. Render all
  (define-values (_r2 render-all-ms)
    (time-ms (lambda () (render-program fns))))
  (printf "  Render all:       ~a ms\n" (~r render-all-ms #:precision 1))

  ;; 5. Text baseline: string-replace across all source strings
  (define rendered-sources (map render-fn fns))
  (define-values (_r3 text-ms)
    (time-ms (lambda ()
      (for/list ([s (in-list rendered-sources)])
        (string-replace s "renamed-f0" "rerenamed-f0")))))
  (printf "  Text replace all: ~a ms\n" (~r text-ms #:precision 1))

  ;; 6. Text baseline: regex search for dependencies (grep equivalent)
  (define-values (_r4 grep-ms)
    (time-ms (lambda ()
      (for/list ([s (in-list rendered-sources)])
        (regexp-match* #rx"\\(f[0-9]+ " s)))))
  (printf "  Text grep deps:   ~a ms\n" (~r grep-ms #:precision 1))

  (printf "  ---\n")
  (printf "  Rename+render-1 / text-replace-all = ~ax\n"
          (if (> text-ms 0)
              (~r (/ rename-one-ms text-ms) #:precision 2)
              "N/A"))
  (printf "  Dep query / text-grep = ~ax\n"
          (if (> grep-ms 0)
              (~r (/ dep-ms grep-ms) #:precision 2)
              "N/A")))

(displayln "")
(displayln "================================================================")
(displayln "    CNF Engine Benchmark")
(displayln "================================================================")
(displayln "")
(displayln "Comparing CNF graph operations against text-based equivalents.")
(displayln "CNF advantages grow with scale (rename is O(1), deps are indexed).")
(displayln "CNF uses semi-naive evaluation (delta restriction per iteration).")

(for ([n '(10 50 100 200)])
  (run-benchmark n))

(displayln "")
(displayln "================================================================")
(displayln "  Notes")
(displayln "================================================================")
(displayln "")
(displayln "- 'Rename+render 1' is the agent scenario: rename a function,")
(displayln "  verify one call site. CNF rename is O(1), rendering is O(fn).")
(displayln "- 'Text replace all' must scan every source string — O(N).")
(displayln "- Datalog dep query uses semi-naive fixpoint. Materialized")
(displayln "  views would make it competitive with grep at scale.")
(displayln "- The index-aware engine avoids full EDB copy and uses claim")
(displayln "  indexes during joins (idx-by-l, idx-by-lp, idx-by-pr).")

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
  (printf "  Parse:            ~a ms  (~a objects, ~a claims)\n"
          (~r parse-ms #:precision 1) total-objects total-claims)

  ;; 2. Dependency query (no materialization — full fixpoint)
  (define-values (deps dep-ms)
    (time-ms (lambda () (query (fn-depends-on (? caller) (? callee))))))
  (printf "  Dep query (cold): ~a ms  (~a deps found)\n"
          (~r dep-ms #:precision 1) (length deps))

  ;; 3. Materialize, then query again (cache hit)
  (define-values (_m1 mat-ms) (time-ms materialize!))
  (define-values (deps2 dep2-ms)
    (time-ms (lambda () (query (fn-depends-on (? caller) (? callee))))))
  (printf "  Materialize:      ~a ms\n" (~r mat-ms #:precision 1))
  (printf "  Dep query (hit):  ~a ms  (~a deps)\n"
          (~r dep2-ms #:precision 1) (length deps2))

  ;; 4. Rename (invalidates), then query (recompute + cache), then query (hit)
  (define-values (_r0 rename-ms)
    (time-ms (lambda () (rename! (first fns) "renamed-f0"))))
  (define-values (deps3 dep3-ms)
    (time-ms (lambda () (query (fn-depends-on (? caller) (? callee))))))
  (define-values (deps4 dep4-ms)
    (time-ms (lambda () (query (fn-depends-on (? caller) (? callee))))))
  (printf "  Rename:           ~a ms\n" (~r rename-ms #:precision 1))
  (printf "  Dep after rename: ~a ms  (recompute)\n" (~r dep3-ms #:precision 1))
  (printf "  Dep again:        ~a ms  (cache hit)\n" (~r dep4-ms #:precision 1))

  ;; 5. Materialized parse: materialize first, then parse (incremental)
  (reset-store!)
  (setup-eval!)
  (setup-graph!)
  (setup-lang!)
  (materialize!)
  (define-values (fns2 parse2-ms) (time-ms (lambda () (parse-program! source))))
  (define-values (deps5 dep5-ms)
    (time-ms (lambda () (query (fn-depends-on (? caller) (? callee))))))
  (printf "  Parse (incr):     ~a ms  (views maintained during parse)\n"
          (~r parse2-ms #:precision 1))
  (printf "  Dep query (incr): ~a ms  (~a deps)\n"
          (~r dep5-ms #:precision 1) (length deps5))

  ;; 6. Render
  (define-values (_r2 render-all-ms)
    (time-ms (lambda () (render-program fns2))))
  (printf "  Render all:       ~a ms\n" (~r render-all-ms #:precision 1))

  ;; 7. Text baselines
  (define rendered-sources (map render-fn fns2))
  (define-values (_r3 text-ms)
    (time-ms (lambda ()
      (for/list ([s (in-list rendered-sources)])
        (string-replace s "f0" "renamed-f0")))))
  (define-values (_r4 grep-ms)
    (time-ms (lambda ()
      (for/list ([s (in-list rendered-sources)])
        (regexp-match* #rx"\\(f[0-9]+ " s)))))
  (printf "  Text replace all: ~a ms\n" (~r text-ms #:precision 1))
  (printf "  Text grep deps:   ~a ms\n" (~r grep-ms #:precision 1))

  (printf "  ---\n")
  (printf "  Dep query speedup (cold vs cache hit): ~ax\n"
          (if (> dep2-ms 0)
              (~r (/ dep-ms dep2-ms) #:precision 1)
              "∞"))
  (printf "  Dep query (incr) vs text grep: ~ax\n"
          (if (> grep-ms 0)
              (~r (/ dep5-ms grep-ms) #:precision 2)
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
(displayln "- 'Dep query (hit)' reads from materialized views — O(1).")
(displayln "- 'Parse (incr)' maintains views live during parsing via")
(displayln "  delta propagation. Query after parse is a cache hit.")
(displayln "- Supersession (rename) invalidates views. Next query recomputes.")
(displayln "- The index-aware engine uses claim hash indexes during joins.")
(displayln "- CNF rename is O(1). Rendering is O(fn-size).")

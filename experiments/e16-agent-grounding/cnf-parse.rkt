#lang racket

(require "../../cnf.rkt" "../../datalog.rkt" "../../eval.rkt"
         "../../graph.rkt" "../../python-lang.rkt")

;; Parse the E16 codebase into the CNF claim graph and demonstrate
;; structural queries that the agent would use during tasks.

(printf "=== E16 CNF Baseline ===\n\n")

(reset-store!)
(setup-eval!)
(setup-graph!)
(setup-python-lang!)

;; Parse all modules
(define modules '("pricing.py" "validation.py" "processing.py" "reporting.py"))
(define all-fns '())

(for ([mod (in-list modules)])
  (define path (build-path "codebase" mod))
  (define source (file->string path))
  (define t0 (current-inexact-milliseconds))
  (define fns (parse-python-program! source))
  (define t1 (current-inexact-milliseconds))
  (printf "  ~a: ~a forms in ~a ms\n" mod (length fns) (~r (- t1 t0) #:precision '(= 1)))
  (set! all-fns (append all-fns fns)))

(printf "\nTotal: ~a forms, ~a objects, ~a claims\n"
        (length all-fns) (length (all-objects)) (length (current-claims-where)))

;; Materialize + custom rules
(define-rule (py-trans-dep (? f) (? g))
  (py-fn-depends-on (? f) (? g)))
(define-rule (py-trans-dep (? f) (? g))
  (py-fn-depends-on (? f) (? m))
  (py-trans-dep (? m) (? g)))

(materialize!)

(define deps (query (py-fn-depends-on (? caller) (? callee))))
(define tdeps (query (py-trans-dep (? f) (? g))))
(printf "\nDirect dependencies: ~a edges\n" (length deps))
(printf "Transitive dependencies: ~a pairs\n" (length tdeps))

;; Task 01 preview: callers of subtotal
(printf "\n--- Task 01: subtotal callers ---\n")
(define subtotal-callers
  (for/list ([d (in-list deps)]
             #:when (equal? (render-ref (hash-ref d 'callee)) "subtotal"))
    (render-ref (hash-ref d 'caller))))
(printf "  Direct: ~a\n" (sort subtotal-callers string<?))

;; Task 02 preview: round_cents impact
(printf "\n--- Task 02: round_cents transitive impact ---\n")
(define rc-affected
  (sort
   (for/list ([d (in-list tdeps)]
              #:when (equal? (render-ref (hash-ref d 'g)) "round_cents"))
     (render-ref (hash-ref d 'f)))
   string<?))
(printf "  Transitively affected (~a): ~a\n" (length rc-affected) rc-affected)

;; Task 04 preview: dead code
(printf "\n--- Task 04: functions with no callers ---\n")
(define all-fn-names
  (for/list ([fn (in-list all-fns)]
             #:when (let ([fk (current-claims-where #:l fn #:p (py-form-kind-pred))])
                      (and (not (null? fk))
                           (equal? (resolve-value (list-ref (first fk) 3)) "function"))))
    (render-ref fn)))
(define called
  (remove-duplicates
   (for/list ([d (in-list deps)]) (render-ref (hash-ref d 'callee)))))
(define uncalled (sort (remove* called all-fn-names) string<?))
(printf "  Uncalled (~a): ~a\n" (length uncalled) uncalled)

;; Task 08 preview: full_report dependency tree
(printf "\n--- Task 08: full_report dependency tree ---\n")
(define fr-deps
  (sort
   (for/list ([d (in-list tdeps)]
              #:when (equal? (render-ref (hash-ref d 'f)) "full_report"))
     (render-ref (hash-ref d 'g)))
   string<?))
(printf "  Full tree (~a): ~a\n" (length fr-deps) fr-deps)

(printf "\n=== CNF baseline ready ===\n")

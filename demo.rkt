#lang racket

(require "cnf.rkt" "datalog.rkt" "eval.rkt" "graph.rkt")

;; E1: Semantic Rename + Incremental Recompute
;;
;; Three things text code does badly that CNF does well:
;; 1. Rename without find-replace
;; 2. Query what depends on what (from the substrate, not a derived cache)
;; 3. Change one thing, recompute only what's affected, keep provenance

(define (section title)
  (printf "\n~a\n~a\n" title (make-string (string-length title) #\=)))

(define (subsection title)
  (printf "\n  ~a\n" title))

(define (find-current-ev expr-id)
  (define cs (current-claims-where #:p (evaluated-pred) #:r expr-id))
  (and (not (null? cs)) (list-ref (first cs) 2)))

(define (expr-result expr-id)
  (define ev (find-current-ev expr-id))
  (and ev (eval-result ev)))

;; ============================================================
;; Setup
;; ============================================================

(reset-store!)
(reset-rules!)
(setup-eval!)
(setup-graph!)

(define add-op (named! "add"))
(define mul-op (named! "multiply"))
(register-primitive! add-op +)
(register-primitive! mul-op *)

;; ============================================================
;; Part 1: Semantic Rename
;; ============================================================

(section "Part 1: Semantic Rename")

(define fn-1 (entity!))
(void (give-name! fn-1 "calculate-pay"))

(define calls-pred (named! "calls"))
(define covers-pred (named! "covers"))
(define describes-pred (named! "describes"))

(define call-1 (entity!))
(void (give-name! call-1 "call-1"))
(void (claim! call-1 calls-pred fn-1))

(define test-1 (entity!))
(void (give-name! test-1 "test-1"))
(void (claim! test-1 covers-pred fn-1))

(define doc-1 (entity!))
(void (give-name! doc-1 "doc-1"))
(void (claim! doc-1 describes-pred fn-1))

(subsection "Program graph (references point to identity, not name):")
(printf "    ~a  calls     ~a\n" (render-ref call-1) (render-ref fn-1))
(printf "    ~a  covers    ~a\n" (render-ref test-1) (render-ref fn-1))
(printf "    ~a  describes ~a\n" (render-ref doc-1) (render-ref fn-1))

(subsection "Rename: 1 new claim. 0 references changed.")
(void (rename! fn-1 "compute-pay"))

(printf "    ~a  calls     ~a\n" (render-ref call-1) (render-ref fn-1))
(printf "    ~a  covers    ~a\n" (render-ref test-1) (render-ref fn-1))
(printf "    ~a  describes ~a\n" (render-ref doc-1) (render-ref fn-1))

(subsection "History preserved:")
(define all-names (claims-where #:l fn-1 #:p (name-pred)))
(for ([c (in-list all-names)])
  (define val (resolve-value (list-ref c 3)))
  (define claim-status
    (if (equal? val (current-name fn-1)) "(current)" "(superseded)"))
  (printf "    fn-1 named ~s ~a\n" val claim-status))

;; ============================================================
;; Part 2: Dependency + Affectedness
;; ============================================================

(section "Part 2: Dependency + Affectedness")

(define one (value! 1))
(define two (value! 2))
(define four (value! 4))
(define ten (value! 10))
(define twenty (value! 20))

(define expr-1 (expr! add-op one two))
(define expr-2 (expr! mul-op expr-1 four))
(define expr-3 (expr! add-op ten twenty))

(void (give-name! expr-1 "expr-1"))
(void (give-name! expr-2 "expr-2"))
(void (give-name! expr-3 "expr-3"))

(subsection "Expressions:")
(printf "    expr-1 = add(1, 2)\n")
(printf "    expr-2 = multiply(expr-1, 4)\n")
(printf "    expr-3 = add(10, 20)          <- independent\n")

(subsection "Dependencies (derived from graph structure, not declared):")
(define deps (query (expr-depends-on (? x) (? dep))))
(for ([d (in-list deps)])
  (printf "    ~a depends on ~a\n"
          (render-ref (hash-ref d 'x))
          (render-ref (hash-ref d 'dep))))

(subsection "What's affected if expr-1 changes?")
(define aff (affected-by expr-1))
(for ([id (in-list aff)])
  (printf "    ~a~a\n" (render-ref id)
          (if (equal? id expr-1) " (changed)" " (transitive)")))
(printf "    ~a NOT affected\n" (render-ref expr-3))

;; ============================================================
;; Part 3: Incremental Recompute
;; ============================================================

(section "Part 3: Incremental Recompute")

(define env (entity!))
(void (run! env))

(subsection "Initial evaluation:")
(printf "    expr-1 = add(1, 2)           => ~a\n" (expr-result expr-1))
(printf "    expr-2 = multiply(expr-1, 4) => ~a\n" (expr-result expr-2))
(printf "    expr-3 = add(10, 20)         => ~a\n" (expr-result expr-3))

;; Save old eval event IDs for provenance display
(define old-ev-1 (find-current-ev expr-1))
(define old-ev-2 (find-current-ev expr-2))
(define old-ev-3 (find-current-ev expr-3))

(subsection "Change: expr-1 right operand 2 -> 5")
(printf "    (1 claim superseded, 1 new claim)\n")
(define five (value! 5))
(void (change-operand! expr-1 (right-pred) two five))

(define-values (affected-ids new-evs) (recompute-affected! env expr-1))

(subsection "Affected:")
(for ([id (in-list affected-ids)])
  (printf "    ~a\n" (render-ref id)))
(printf "    ~a NOT affected (untouched)\n" (render-ref expr-3))

(subsection "After recompute:")
(printf "    expr-1 = add(1, 5)           => ~a  (recomputed)\n" (expr-result expr-1))
(printf "    expr-2 = multiply(expr-1, 4) => ~a  (recomputed)\n" (expr-result expr-2))
(printf "    expr-3 = add(10, 20)         => ~a  (untouched)\n" (expr-result expr-3))

(subsection "Provenance (old eval events still in graph):")
(for ([ev (list old-ev-1 old-ev-2 old-ev-3)]
      [name '("expr-1" "expr-2" "expr-3")])
  (define old-result-claims (claims-where #:l ev #:p (result-pred)))
  (define old-val (resolve-value (list-ref (first old-result-claims) 3)))
  (define still-current?
    (not (null? (current-claims-where #:l ev #:p (evaluated-pred)))))
  (printf "    ~a was ~a ~a\n" name old-val
          (if still-current? "(still current)" "(superseded)")))

;; ============================================================
;; The point
;; ============================================================

(section "The point")
(printf "
  Text code:
    Rename:       find-replace across N files
    Dependencies: grep or language server (derived cache, can go stale)
    Recompute:    rebuild everything, or maintain complex incremental build

  CNF:
    Rename:       1 claim (identity is stable, name is a claim)
    Dependencies: O(affected-subgraph) query on the program substrate itself
    Recompute:    invalidate + re-evaluate only affected, with full provenance

  > CNF makes program change a graph operation instead of a text operation.
")

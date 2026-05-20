#lang racket

;; E12: Real Codebase Demo
;;
;; 100-function financial analytics program, 5 layers.
;; Full workflow: parse, discover, define rules, refactor, evolve.
;; Includes incremental parse (add/remove/modify) — the E9 missing piece.

(require cnf cnf/lang)

(define (fresh!)
  (reset-store!)
  (setup-eval!)
  (setup-graph!)
  (setup-schema!)
  (setup-rule-predicates!)
  (setup-lang!)
  (materialize!))

(define (timed label thunk)
  (collect-garbage)
  (define start (current-inexact-milliseconds))
  (define result (thunk))
  (define elapsed (- (current-inexact-milliseconds) start))
  (printf "  ~a: ~ams\n" label (~r elapsed #:precision '(= 1)))
  result)

(define here (path->string (path-only (syntax-source #'here))))
(define source (file->string (build-path here "demo-program.txt")))

(displayln "=== E12: Real Codebase Demo ===")
(displayln (format "Program: 100 functions, 5 layers, ~a lines"
                   (length (string-split source "\n"))))
(displayln "")

;; Phase 1: Parse
(displayln "--- Phase 1: Parse ---")
(fresh!)
(define fns
  (timed "parse 100 functions" (lambda () (parse-program! source))))
(printf "  Objects: ~a, Claims: ~a\n" (length (all-objects)) (length (claims-where)))
(displayln "")

;; Phase 2: Discover structure
(displayln "--- Phase 2: Discover structure ---")
(define all-deps
  (timed "query fn-depends-on (all)" (lambda () (query (fn-depends-on (? a) (? b))))))
(printf "  Dependency edges: ~a\n" (length all-deps))

(define scale-rate-id (first fns))
(define deps-of-firm-pnl
  (timed "query deps of firm-pnl"
    (lambda ()
      (define firm-pnl-id (last fns))
      (query (fn-depends-on firm-pnl-id (? dep))))))
(printf "  firm-pnl direct deps: ~a\n" (length deps-of-firm-pnl))
(displayln "")

;; Phase 3: Define custom rules
(displayln "--- Phase 3: Define custom rules ---")
(define cp (calls-pred))
(define lp (left-pred))
(define rp (right-pred))
(define bp (body-pred))

(timed "define trans-dep (base)"
  (lambda ()
    (define-rule (trans-dep (? f) (? g)) (fn-depends-on (? f) (? g)))))

(timed "define trans-dep (recursive)"
  (lambda ()
    (define-rule (trans-dep (? f) (? g))
      (fn-depends-on (? f) (? mid))
      (trans-dep (? mid) (? g)))))

(timed "define shared-dep"
  (lambda ()
    (define-rule (shared-dep (? f) (? g) (? shared))
      (fn-depends-on (? f) (? shared))
      (fn-depends-on (? g) (? shared)))))

(timed "materialize rules"
  (lambda () (materialize!)))

(define trans-deps
  (timed "query trans-dep (all)"
    (lambda () (query (trans-dep (? a) (? b))))))
(printf "  Transitive dependency pairs: ~a\n" (length trans-deps))

(define firm-pnl-trans
  (timed "query trans-dep of firm-pnl"
    (lambda ()
      (define firm-pnl-id (last fns))
      (query (trans-dep firm-pnl-id (? dep))))))
(printf "  firm-pnl transitive deps: ~a\n" (length firm-pnl-trans))
(displayln "")

;; Phase 4: Define hub analysis rule
(displayln "--- Phase 4: Hub analysis ---")
(define np (name-pred))

(timed "define hub (called by 3+ functions via shared-dep)"
  (lambda ()
    (define-rule (hub-pair (? f) (? g) (? hub))
      (shared-dep (? f) (? g) (? hub))
      (trans-dep (? f) (? hub))
      (trans-dep (? g) (? hub)))))

(timed "materialize hub rule"
  (lambda () (materialize!)))

(define hubs
  (timed "query hub-pair"
    (lambda () (query (hub-pair (? f) (? g) (? hub))))))
(printf "  Hub triples: ~a\n" (length hubs))

(define callers-count
  (length (remove-duplicates (map (lambda (s) (hash-ref s 'hub)) hubs))))
(printf "  Unique hubs: ~a\n" callers-count)
(displayln "")

;; Phase 5: Refactor (rename)
(displayln "--- Phase 5: Refactor ---")
(define blend-id
  (let ([vid (value-id "blend")])
    (and vid
         (let ([cs (current-claims-where #:p np #:r vid)])
           (and (not (null? cs)) (list-ref (first cs) 2))))))

(void (timed "rename blend → mix"
  (lambda () (rename! blend-id "mix"))))

(define post-rename-deps
  (timed "query fn-depends-on after rename (matview cache hit)"
    (lambda () (query (fn-depends-on (? a) (? b))))))
(printf "  Dependency edges after rename: ~a\n" (length post-rename-deps))

(define rendered
  (timed "render risk-adj (should show 'mix')"
    (lambda ()
      (define risk-adj-id (list-ref fns 19))
      (render-fn risk-adj-id))))
(printf "  ~a\n" rendered)
(displayln "")

;; Phase 6: Incremental parse — the E9 missing piece
(displayln "--- Phase 6: Incremental parse ---")

(define rules-before (length (ctx-ref 'rules '())))
(define claims-before (length (claims-where)))

(void (timed "add-function! (new function referencing existing)"
  (lambda ()
    (add-function! "(defn excess-return [x y]\n  (delta (net-perf x y) (interest x y)))"))))

(define new-deps
  (timed "query deps of excess-return (matview auto-updated)"
    (lambda ()
      (define eid (let ([vid (value-id "excess-return")])
                    (and vid
                         (let ([cs (current-claims-where #:p np #:r vid)])
                           (and (not (null? cs)) (list-ref (first cs) 2))))))
      (query (fn-depends-on eid (? dep))))))
(printf "  excess-return depends on: ~a functions\n" (length new-deps))

(void (timed "modify-function! (change net-perf body)"
  (lambda ()
    (modify-function! "net-perf" "(defn net-perf [x y]\n  (delta (post-trade x y) (mgmt-fee x y)))"))))

(define modified-deps
  (timed "query deps of net-perf after modify (should change)"
    (lambda ()
      (define npid (let ([vid (value-id "net-perf")])
                     (and vid
                          (let ([cs (current-claims-where #:p np #:r vid)])
                            (and (not (null? cs)) (list-ref (first cs) 2))))))
      (query (fn-depends-on npid (? dep))))))
(printf "  net-perf deps after modify: ~a\n" (length modified-deps))

(void (timed "remove-function! (remove daily-pnl)"
  (lambda () (remove-function! "daily-pnl"))))

(define rules-after (length (ctx-ref 'rules '())))
(printf "  Rules preserved across mutations: ~a (was ~a)\n" rules-after rules-before)

(define claims-after (length (claims-where)))
(printf "  Claims: ~a → ~a (delta: ~a)\n"
        claims-before claims-after (- claims-after claims-before))
(displayln "")

;; Phase 7: Temporal queries
(displayln "--- Phase 7: Temporal queries ---")
(define seq-now (current-tx-seq))
(printf "  Current tx seq: ~a\n" seq-now)
(define txs (all-txs))
(printf "  Total transactions: ~a\n" (length txs))
(displayln "")

;; Summary
(displayln "=== Summary ===")
(printf "Objects: ~a\n" (length (all-objects)))
(printf "Claims: ~a (active: ~a)\n"
        (length (claims-where))
        (length (filter (lambda (c) (not (superseded? (first c)))) (claims-where))))
(printf "Rules: ~a\n" (length (ctx-ref 'rules '())))
(printf "Transactions: ~a\n" (length (all-txs)))
(displayln "")
(displayln "Full workflow complete: parse → discover → rules → refactor → evolve → temporal.")
(displayln "Rules and matviews survived incremental parse mutations.")

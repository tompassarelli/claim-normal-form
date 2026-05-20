#lang racket

(require cnf cnf/beagle)

;; E13: Beagle bridge demo — real beagle syntax, real CNF claim graph.
;;
;; Demonstrates: parse beagle source → query structural dependencies →
;; define custom Datalog rules → rename (claim-level, O(1)) → incremental
;; edit → render back to beagle source.

(define beagle-source "
(defrecord Trade [(symbol : String) (qty : Int) (price : Float)])

(defrecord Portfolio [(name : String) (trades : (Vec Trade))])

(defn trade-value [(t : Trade)] : Float
  (* (trade-qty t) (trade-price t)))

(defn portfolio-total [(p : Portfolio)] : Float
  (reduce + 0.0 (mapv trade-value (portfolio-trades p))))

(defn trade-pnl [(t : Trade) (mark : Float)] : Float
  (- (* (trade-qty t) mark) (trade-value t)))

(defn portfolio-pnl [(p : Portfolio) (marks : (Map String Float))] : Float
  (reduce + 0.0
    (mapv (fn [t] (trade-pnl t (get marks (trade-symbol t) 0.0)))
          (portfolio-trades p))))

(defn high-value-trades [(p : Portfolio) (threshold : Float)] : (Vec Trade)
  (filterv (fn [t] (>= (trade-value t) threshold))
           (portfolio-trades p)))

(defn portfolio-summary [(p : Portfolio) (marks : (Map String Float))] : String
  (let [total (portfolio-total p)
        pnl (portfolio-pnl p marks)
        big-trades (high-value-trades p 10000.0)]
    (str (portfolio-name p)
         \": total=\" (str total)
         \" pnl=\" (str pnl)
         \" big-trades=\" (str (count big-trades)))))

(defn risk-report [(portfolios : (Vec Portfolio)) (marks : (Map String Float))] : (Vec String)
  (mapv (fn [p] (portfolio-summary p marks)) portfolios))
")

(define (time-ms thunk)
  (define t0 (current-inexact-milliseconds))
  (define result (thunk))
  (define t1 (current-inexact-milliseconds))
  (values result (- t1 t0)))

(define (show-dep-pair d k1 k2 [prefix "    "] [arrow "->"])
  (define a (hash-ref d k1))
  (define b (hash-ref d k2))
  (printf "~a~a ~a ~a\n" prefix (render-ref a) arrow (render-ref b)))

(printf "=== E13: Beagle Bridge Demo ===\n\n")

;; --- Phase 1: Parse ---
(reset-store!)
(setup-eval!)
(setup-graph!)
(setup-beagle-lang!)

(define-values (fns parse-ms) (time-ms (lambda () (parse-beagle-program! beagle-source))))
(printf "Phase 1 — Parse\n")
(printf "  Parsed ~a forms in ~a ms\n" (length fns) (~r parse-ms #:precision 1))
(printf "  Objects: ~a\n" (length (all-objects)))
(printf "  Claims: ~a\n" (length (claims-where)))
(printf "  Forms:\n")
(for ([fn fns])
  (define fk (current-claims-where #:l fn #:p (form-kind-pred)))
  (define kind (if (null? fk) "?" (resolve-value (list-ref (first fk) 3))))
  (printf "    ~a (~a)\n" (render-ref fn) kind))

;; --- Phase 2: Query dependencies ---
(printf "\nPhase 2 — Dependency discovery\n")
(define-values (deps dep-ms)
  (time-ms (lambda () (query (fn-depends-on (? caller) (? callee))))))
(printf "  fn-depends-on: ~a edges in ~a ms\n" (length deps) (~r dep-ms #:precision 1))
(for ([d deps]) (show-dep-pair d 'caller 'callee))

;; --- Phase 3: Custom rules + materialize ---
(printf "\nPhase 3 — Custom rules + materialize\n")

(define-rule (trans-dep (? f) (? g))
  (fn-depends-on (? f) (? g)))
(define-rule (trans-dep (? f) (? g))
  (fn-depends-on (? f) (? m))
  (trans-dep (? m) (? g)))

(define-values (_ mat-ms) (time-ms materialize!))
(printf "  Materialize: ~a ms\n" (~r mat-ms #:precision 1))

(define-values (_2 dep2-ms)
  (time-ms (lambda () (query (fn-depends-on (? caller) (? callee))))))
(printf "  fn-depends-on (cache): ~a ms (~a edges)\n"
        (~r dep2-ms #:precision 1) (length (query (fn-depends-on (? caller) (? callee)))))

(define-values (tdeps td-ms)
  (time-ms (lambda () (query (trans-dep (? f) (? g))))))
(printf "  trans-dep: ~a pairs in ~a ms\n" (length tdeps) (~r td-ms #:precision 1))
(for ([d tdeps]) (show-dep-pair d 'f 'g "    " "=>"))

;; --- Phase 4: Rename ---
(printf "\nPhase 4 — Rename\n")
(define trade-value-fn (first (filter
  (lambda (fn) (equal? (render-ref fn) "trade-value"))
  fns)))
(define-values (_3 rename-ms) (time-ms (lambda () (rename! trade-value-fn "compute-trade-value"))))
(printf "  Renamed trade-value -> compute-trade-value in ~a ms\n" (~r rename-ms #:precision 2))

(printf "  Callers auto-updated:\n")
(for ([fn fns])
  (define body-id (get-body fn))
  (when body-id
    (define rendered (render-beagle-expr body-id))
    (when (regexp-match? #rx"compute-trade-value" rendered)
      (printf "    ~a uses compute-trade-value\n" (render-ref fn)))))

;; --- Phase 5: Render ---
(printf "\nPhase 5 — Render (full program)\n")
(define-values (rendered render-ms) (time-ms (lambda () (render-beagle-program fns))))
(printf "  Rendered ~a forms in ~a ms\n" (length fns) (~r render-ms #:precision 1))
(printf "\n~a\n" rendered)

;; --- Phase 6: Incremental edit ---
(printf "\nPhase 6 — Incremental edit\n")

(define-values (new-fn add-ms)
  (time-ms (lambda ()
    (add-beagle-function! "
(defn weighted-pnl [(p : Portfolio) (marks : (Map String Float)) (weight : Float)] : Float
  (* (portfolio-pnl p marks) weight))"))))
(printf "  add-function! in ~a ms\n" (~r add-ms #:precision 1))

(define-values (_4 mod-ms)
  (time-ms (lambda ()
    (modify-beagle-function! "compute-trade-value" "
(defn net-trade-value [(t : Trade)] : Float
  (- (* (trade-qty t) (trade-price t)) 0.01))"))))
(printf "  modify-function! (+ rename) in ~a ms\n" (~r mod-ms #:precision 1))

;; Re-query dependencies
(define-values (deps3 dep3-ms)
  (time-ms (lambda () (query (fn-depends-on (? caller) (? callee))))))
(printf "  fn-depends-on after mutations: ~a edges in ~a ms\n"
        (length deps3) (~r dep3-ms #:precision 1))
(for ([d deps3]) (show-dep-pair d 'caller 'callee))

;; Final render
(printf "\n  Final program:\n")
(define all-fns (append fns (list new-fn)))
(for ([fn all-fns])
  (printf "\n~a\n" (render-beagle-fn fn)))

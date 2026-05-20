#lang racket

(require rackunit
         "cnf.rkt"
         "datalog.rkt"
         "eval.rkt"
         "graph.rkt"
         "lang.rkt")

(define (fresh!)
  (reset-store!)
  (setup-eval!)
  (setup-graph!)
  (setup-lang!))

;; 1. Single function parse/render round-trip
(fresh!)
(let ()
  (define source "(defn double [x y]\n  (* x y))")
  (define fns (parse-program! source))
  (check-equal? (length fns) 1)
  (check-equal? (render-fn (first fns)) source)
  (displayln "PASS 1 — single function parse/render round-trip"))

;; 2. Cross-function call round-trip
(fresh!)
(let ()
  (define fn1 "(defn compute-pay [hours rate]\n  (* hours rate))")
  (define fn2 "(defn total-cost [hours rate]\n  (+ (compute-pay hours rate) 100))")
  (define source (string-join (list fn1 fn2) "\n\n"))
  (define fns (parse-program! source))
  (check-equal? (length fns) 2)
  (check-equal? (render-program fns) source)
  (displayln "PASS 2 — cross-function call parse/render round-trip"))

;; 3. Number literals preserved
(fresh!)
(let ()
  (define source "(defn add-ten [x y]\n  (+ x 10))")
  (define fns (parse-program! source))
  (check-equal? (render-fn (first fns)) source)
  (displayln "PASS 3 — number literals preserved in round-trip"))

;; 4. Nested expressions
(fresh!)
(let ()
  (define source "(defn nested [a b]\n  (* (+ a b) (- a b)))")
  (define fns (parse-program! source))
  (check-equal? (render-fn (first fns)) source)
  (displayln "PASS 4 — nested expressions round-trip"))

;; 5. Rename function — call site updates automatically
(fresh!)
(let ()
  (define fn1 "(defn compute-pay [hours rate]\n  (* hours rate))")
  (define fn2 "(defn total-cost [hours rate]\n  (+ (compute-pay hours rate) 100))")
  (define source (string-join (list fn1 fn2) "\n\n"))
  (define fns (parse-program! source))
  (rename! (first fns) "calculate-pay")
  (define rendered (render-program fns))
  (check-true (string-contains? rendered "calculate-pay"))
  (check-false (string-contains? rendered "compute-pay"))
  (check-true (string-contains? (render-fn (second fns)) "calculate-pay"))
  (displayln "PASS 5 — rename propagates to call sites"))

;; 6. Old name preserved after rename
(fresh!)
(let ()
  (define fns (parse-program! "(defn my-fn [a b]\n  (+ a b))"))
  (define fn-id (first fns))
  (rename! fn-id "new-name")
  (check-equal? (render-ref fn-id) "new-name")
  (define all-name-claims (claims-where #:l fn-id #:p (name-pred)))
  (check-equal? (length all-name-claims) 2)
  (define name-vals
    (map (lambda (c) (resolve-value (list-ref c 3))) all-name-claims))
  (check-not-false (member "my-fn" name-vals))
  (check-not-false (member "new-name" name-vals))
  (displayln "PASS 6 — old name preserved as history"))

;; 7. fn-depends-on derived by Datalog
(fresh!)
(let ()
  (define fn1 "(defn helper [a b]\n  (+ a b))")
  (define fn2 "(defn caller [x y]\n  (* (helper x y) 2))")
  (define source (string-join (list fn1 fn2) "\n\n"))
  (define fns (parse-program! source))
  (define helper-fn (first fns))
  (define caller-fn (second fns))
  (define deps (query (fn-depends-on (? who) (? on))))
  (check-true
   (ormap (lambda (s)
            (and (equal? (hash-ref s 'who) caller-fn)
                 (equal? (hash-ref s 'on) helper-fn)))
          deps))
  (displayln "PASS 7 — fn-depends-on derived by Datalog"))

;; 8. Change body operator via supersession
(fresh!)
(let ()
  (define fns (parse-program! "(defn calc [a b]\n  (* a b))"))
  (define fn-id (first fns))
  (define body-id (get-body fn-id))
  (define builtins (ctx-ref 'builtins))
  (define mul-op (hash-ref builtins '*))
  (define add-op (hash-ref builtins '+))
  (change-operand! body-id (op-pred) mul-op add-op)
  (define rendered (render-fn fn-id))
  (check-true (string-contains? rendered "(+ a b)"))
  (check-false (string-contains? rendered "(* a b)"))
  (define all-op-claims (claims-where #:l body-id #:p (op-pred)))
  (check-equal? (length all-op-claims) 2)
  (displayln "PASS 8 — operator changed via supersession, old preserved"))

(displayln "")
(displayln "All lang tests passed.")

#lang racket

(require rackunit
         cnf/private/kernel
         cnf/private/datalog
         cnf/private/eval
         cnf/private/graph
         cnf/private/schema
         cnf/private/lang)

;; --- MVCC Tests ---
;; Tests for snapshot isolation: readers see consistent state,
;; writers don't block readers, snapshots are independent.

(define (fresh!)
  (reset-store!)
  (setup-eval!)
  (setup-graph!)
  (setup-schema!)
  (setup-rule-predicates!)
  (setup-lang!)
  (materialize!))

;; 1. snapshot-ctx creates independent copy
(fresh!)
(let ()
  (define fns (parse-program! "(defn foo [a b]\n  (+ a b))"))
  (define snap (snapshot-ctx))
  (define claims-before (length (claims-where)))
  (parse-program! "(defn bar [x y]\n  (* x y))")
  (define claims-after (length (claims-where)))
  (check-true (> claims-after claims-before))
  (parameterize ([current-ctx snap])
    (check-equal? (length (claims-where)) claims-before))
  (displayln "PASS 1 — snapshot is independent of live state"))

;; 2. snapshot preserves matview queries
(fresh!)
(let ()
  (define fns (parse-program!
    "(defn helper [a b]\n  (+ a b))\n\n(defn caller [x y]\n  (helper x y))"))
  (define snap (snapshot-ctx))
  (define live-deps (query (fn-depends-on (? a) (? b))))
  (parameterize ([current-ctx snap])
    (define snap-deps (query (fn-depends-on (? a) (? b))))
    (check-equal? (length snap-deps) (length live-deps)))
  (displayln "PASS 2 — snapshot preserves matview queries"))

;; 3. writes on live ctx don't affect snapshot queries
(fresh!)
(let ()
  (define fns (parse-program!
    "(defn base [a b]\n  (+ a b))"))
  (define snap (snapshot-ctx))
  (add-function! "(defn caller [x y]\n  (base x y))")
  (define live-deps (query (fn-depends-on (? a) (? b))))
  (check-equal? (length live-deps) 1)
  (parameterize ([current-ctx snap])
    (define snap-deps (query (fn-depends-on (? a) (? b))))
    (check-equal? (length snap-deps) 0))
  (displayln "PASS 3 — writes don't affect snapshot queries"))

;; 4. snapshot preserves transaction data
(fresh!)
(let ()
  (ctx-set! 'current-agent "agent-A")
  (define fns (parse-program! "(defn foo [a b]\n  (+ a b))"))
  (define snap (snapshot-ctx))
  (define live-seq (current-tx-seq))
  (ctx-set! 'current-agent "agent-B")
  (parse-program! "(defn bar [x y]\n  (* x y))")
  (check-true (> (current-tx-seq) live-seq))
  (parameterize ([current-ctx snap])
    (check-equal? (current-tx-seq) live-seq))
  (displayln "PASS 4 — snapshot preserves transaction data"))

;; 5. multiple snapshots are independent
(fresh!)
(let ()
  (parse-program! "(defn a [x y]\n  (+ x y))")
  (define snap1 (snapshot-ctx))
  (parse-program! "(defn b [x y]\n  (* x y))")
  (define snap2 (snapshot-ctx))
  (parse-program! "(defn c [x y]\n  (- x y))")
  (define live-claims (length (claims-where)))
  (parameterize ([current-ctx snap1])
    (define s1-claims (length (claims-where)))
    (check-true (< s1-claims live-claims)))
  (parameterize ([current-ctx snap2])
    (define s2-claims (length (claims-where)))
    (parameterize ([current-ctx snap1])
      (check-true (< (length (claims-where)) s2-claims))))
  (displayln "PASS 5 — multiple snapshots are independent"))

;; 6. concurrent reads on snapshot (thread safety)
(fresh!)
(let ()
  (define fns (parse-program!
    (string-append
      "(defn f1 [a b]\n  (+ a b))\n\n"
      "(defn f2 [a b]\n  (* a b))\n\n"
      "(defn f3 [x y]\n  (f1 x y))\n\n"
      "(defn f4 [x y]\n  (f2 x y))")))
  (define snap (snapshot-ctx))
  (define results (make-channel))
  (for ([i (in-range 10)])
    (thread
     (lambda ()
       (parameterize ([current-ctx snap])
         (define deps (query (fn-depends-on (? a) (? b))))
         (channel-put results (length deps))))))
  (define counts
    (for/list ([i (in-range 10)])
      (channel-get results)))
  (check-true (apply = counts))
  (displayln "PASS 6 — concurrent reads on snapshot produce consistent results"))

(displayln "")
(displayln "All MVCC tests passed.")

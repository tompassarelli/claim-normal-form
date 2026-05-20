#lang racket

(require rackunit
         cnf/private/kernel
         cnf/private/datalog
         cnf/private/schema)

;; 1. Implicit tx on every claim
(reset-store!)
(let* ([a (entity!)]
       [p (entity!)]
       [b (entity!)]
       [c (claim! a p b)])
  (check-not-false (claim-tx c))
  (check-equal? (length (tx-claims (claim-tx c))) 1)
  (displayln "PASS 1 — implicit tx on every claim"))

;; 2. Explicit transaction groups claims
(reset-store!)
(let* ([a (entity!)]
       [p (entity!)]
       [b (entity!)]
       [c (entity!)])
  (define tx (begin-tx!))
  (define c1 (claim! a p b))
  (define c2 (claim! a p c))
  (commit-tx!)
  (check-equal? (claim-tx c1) (claim-tx c2))
  (check-equal? (length (tx-claims tx)) 2)
  (displayln "PASS 2 — explicit tx groups claims"))

;; 3. Rollback undoes all claims
(reset-store!)
(let* ([a (entity!)]
       [p (entity!)]
       [b (entity!)]
       [claims-before (length (claims-where))])
  (begin-tx!)
  (claim! a p b)
  (claim! a p a)
  (rollback-tx!)
  (check-equal? (length (claims-where)) claims-before)
  (displayln "PASS 3 — rollback undoes all claims"))

;; 4. Rollback on exception via call-with-transaction
(reset-store!)
(let* ([a (entity!)]
       [p (entity!)]
       [b (entity!)]
       [claims-before (length (claims-where))])
  (check-exn exn:fail?
    (lambda ()
      (call-with-transaction
       (lambda ()
         (claim! a p b)
         (error "boom")))))
  (check-equal? (length (claims-where)) claims-before)
  (displayln "PASS 4 — rollback on exception"))

;; 5. Tx sequence ordering
(reset-store!)
(let* ([a (entity!)]
       [p (entity!)]
       [b (entity!)]
       [c1 (claim! a p b)]
       [c2 (claim! a p a)])
  (define tx1 (claim-tx c1))
  (define tx2 (claim-tx c2))
  (check-true (< (tx-seq tx1) (tx-seq tx2)))
  (displayln "PASS 5 — tx sequence ordering"))

;; 6. claims-since filters by tx seq
(reset-store!)
(let* ([a (entity!)]
       [p (entity!)]
       [b (entity!)]
       [c1 (claim! a p b)]
       [seq-after-c1 (current-tx-seq)]
       [c2 (claim! a p a)])
  (define since (claims-since seq-after-c1))
  (check-not-false (member c2 since))
  (check-false (member c1 since))
  (displayln "PASS 6 — claims-since filters by tx seq"))

;; 7. all-txs returns sorted list
(reset-store!)
(let* ([a (entity!)]
       [p (entity!)]
       [b (entity!)])
  (claim! a p b)
  (claim! a p a)
  (define txs (all-txs))
  (check-true (>= (length txs) 2))
  (define seqs (map tx-seq txs))
  (check-equal? seqs (sort seqs <))
  (displayln "PASS 7 — all-txs returns sorted list"))

;; 8. Serialization round-trip preserves tx data
(reset-store!)
(let* ([a (entity!)]
       [p (entity!)]
       [b (entity!)]
       [c (claim! a p b)]
       [tx (claim-tx c)]
       [seq (tx-seq tx)]
       [data (export-store)])
  (check-equal? (hash-ref data 'version) 2)
  (current-ctx (make-blank-ctx))
  (import-store! data)
  (check-equal? (claim-tx c) tx)
  (check-equal? (tx-seq tx) seq)
  (displayln "PASS 8 — serialization round-trip preserves tx data"))

;; 9. V1 import creates synthetic tx
(reset-store!)
(let* ([a (entity!)]
       [p (entity!)]
       [b (entity!)]
       [c (claim! a p b)]
       [data (export-store)]
       [v1-data (hash-remove (hash-remove (hash-remove
                  (hash-set data 'version 1)
                  'tx-counter) 'claim-txs) 'tx-meta)])
  (current-ctx (make-blank-ctx))
  (import-store! v1-data)
  (check-not-false (claim-tx c))
  (check-equal? (current-tx-seq) 1)
  (displayln "PASS 9 — v1 import creates synthetic tx"))

;; 10. Hook suppression during tx — matview updates on commit
(reset-store!)
(setup-schema!)
(define-predicates edge)
(define aa (named! "aa"))
(define bb (named! "bb"))
(define cc (named! "cc"))
(claim! aa edge bb)
(define-rule (link (? x) (? y)) (current-triple (? x) edge (? y)))
(materialize!)
(define before-tx (length (query (link (? x) (? y)))))
(begin-tx!)
(claim! bb edge cc)
(define during-tx (length (query (link (? x) (? y)))))
(check-equal? during-tx before-tx) ;; hooks suppressed — matview unchanged
(commit-tx!)
(define after-commit (length (query (link (? x) (? y)))))
(check-equal? after-commit (+ before-tx 1)) ;; hooks fired on commit
(displayln "PASS 10 — matview updates on commit, not during tx")

;; 11. Temporal query: claims-visible-as-of
(reset-store!)
(setup-schema!)
(define-predicates color)
(define apple (named! "apple"))
(claim! apple color (value! "green"))
(define seq1 (current-tx-seq))
(update! apple color "red")
(define seq2 (current-tx-seq))
(define as-of-1 (claims-visible-as-of seq1 #:l apple #:p color))
(define as-of-2 (claims-visible-as-of seq2 #:l apple #:p color))
(check-equal? (length as-of-1) 1)
(check-equal? (length as-of-2) 1)
(define val-1 (resolve-value (list-ref (first as-of-1) 3)))
(define val-2 (resolve-value (list-ref (first as-of-2) 3)))
(check-equal? val-1 "green")
(check-equal? val-2 "red")
(displayln "PASS 11 — temporal query: claims-visible-as-of")

;; 12. Nested tx rejected
(reset-store!)
(begin-tx!)
(check-exn exn:fail?
  (lambda () (begin-tx!)))
(commit-tx!)
(displayln "PASS 12 — nested tx rejected")

;; 13. current-tx-seq advances monotonically
(reset-store!)
(let* ([a (entity!)]
       [p (entity!)]
       [b (entity!)]
       [s0 (current-tx-seq)])
  (claim! a p b)
  (define s1 (current-tx-seq))
  (claim! a p a)
  (define s2 (current-tx-seq))
  (check-true (< s0 s1))
  (check-true (< s1 s2))
  (displayln "PASS 13 — current-tx-seq advances monotonically"))

;; 14. Agent identity on transactions
(reset-store!)
(let* ([a (entity!)]
       [p (entity!)]
       [b (entity!)]
       [c1 (claim! a p b)])
  (check-false (tx-agent (claim-tx c1)))
  (ctx-set! 'current-agent "agent-A")
  (define c2 (claim! a p a))
  (check-equal? (tx-agent (claim-tx c2)) "agent-A")
  (ctx-set! 'current-agent #f)
  (displayln "PASS 14 — agent identity on implicit txs"))

;; 15. Agent identity on explicit transactions
(reset-store!)
(let* ([a (entity!)]
       [p (entity!)]
       [b (entity!)])
  (define tx (begin-tx! #:agent "agent-B"))
  (claim! a p b)
  (commit-tx!)
  (check-equal? (tx-agent tx) "agent-B")
  (displayln "PASS 15 — agent identity on explicit txs"))

;; 16. Agent identity survives serialization round-trip
(reset-store!)
(ctx-set! 'current-agent "agent-C")
(let* ([a (entity!)]
       [p (entity!)]
       [b (entity!)]
       [c (claim! a p b)]
       [tx (claim-tx c)]
       [data (export-store)])
  (ctx-set! 'current-agent #f)
  (current-ctx (make-blank-ctx))
  (import-store! data)
  (check-equal? (tx-agent tx) "agent-C")
  (displayln "PASS 16 — agent identity survives serialization"))

(displayln "")
(displayln "All tx tests passed.")

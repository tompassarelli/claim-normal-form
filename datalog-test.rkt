#lang racket

(require rackunit
         "cnf.rkt"
         "datalog.rkt")

;; 1. Basic triple query
(reset-store!)
(reset-rules!)

(let* ([a (entity!)]
       [p (entity!)]
       [b (entity!)]
       [c (claim! a p b)]
       [results (query (triple (? l) (? pred) (? r)))])
  (check-true (>= (length results) 2))
  (check-true
    (ormap (λ (s) (and (equal? (hash-ref s 'l) a)
                       (equal? (hash-ref s 'pred) p)
                       (equal? (hash-ref s 'r) b)))
           results))
  (displayln "PASS 1 — basic triple query"))

;; 2. Query with constants
(reset-store!)
(reset-rules!)

(let* ([a (entity!)]
       [p (entity!)]
       [b (entity!)]
       [c (claim! a p b)]
       [results (query (triple a (? pred) (? r)))])
  (check-equal? (length results) 1)
  (check-equal? (hash-ref (first results) 'pred) p)
  (check-equal? (hash-ref (first results) 'r) b)
  (displayln "PASS 2 — query with constants"))

;; 3. Literals resolve to interned value IDs — no value/2 join needed
(reset-store!)
(reset-rules!)

(let* ([tom (named! "tom")]
       [results (query (triple tom (? p) "tom"))])
  (check-equal? (length results) 1)
  (displayln "PASS 3 — literals resolve automatically"))

;; 4. Join — find named objects using literals directly
(reset-store!)
(reset-rules!)

(let* ([tom (named! "tom")]
       [results (query (triple (? obj) (? sym) "tom")
                       (triple (? sym) (? sym) "symbol"))])
  (check-true
    (ormap (λ (s) (equal? (hash-ref s 'obj) tom))
           results))
  (displayln "PASS 4 — join with literal resolution"))

;; 5. Rule definition and query
(reset-store!)
(reset-rules!)

(define-rule (named-thing (? obj) (? name-val))
  (triple (? obj) (? sym) (? name-val))
  (triple (? sym) (? sym) "symbol"))

(let* ([tom (named! "tom")]
       [alice (named! "alice")]
       [results (query (named-thing (? who) (? what)))])
  (check-true (>= (length results) 3))
  (define names (map (λ (s) (resolve-value (hash-ref s 'what))) results))
  (check-not-false (member "tom" names))
  (check-not-false (member "alice" names))
  (check-not-false (member "symbol" names))
  (displayln "PASS 5 — rule definition and query"))

;; 6. Transitive closure (recursive rules)
(reset-store!)
(reset-rules!)

(define edge-pred (named! "edge"))
(define a-node (named! "a"))
(define b-node (named! "b"))
(define c-node (named! "c"))
(define d-node (named! "d"))

(void (claim! a-node edge-pred b-node))
(void (claim! b-node edge-pred c-node))
(void (claim! c-node edge-pred d-node))

(define-rule (path (? x) (? y))
  (triple (? x) edge-pred (? y)))

(define-rule (path (? x) (? z))
  (triple (? x) edge-pred (? y))
  (path (? y) (? z)))

(let ([results (query (path (? from) (? to)))])
  (check-equal? (length results) 6)
  (check-true
    (ormap (λ (s) (and (equal? (hash-ref s 'from) a-node)
                       (equal? (hash-ref s 'to) d-node)))
           results))
  (displayln "PASS 6 — transitive closure"))

;; 7. Claim IDs via claim/4
(reset-store!)
(reset-rules!)

(let* ([a (entity!)]
       [p (entity!)]
       [b (entity!)]
       [c (claim! a p b)]
       [results (query (claim (? cid) a p b))])
  (check-equal? (length results) 1)
  (check-equal? (hash-ref (first results) 'cid) c)
  (displayln "PASS 7 — claim IDs via claim/4"))

;; 8. Meta-claims (claims about claims)
(reset-store!)
(reset-rules!)

(let* ([a (entity!)]
       [p (entity!)]
       [b (entity!)]
       [c1 (claim! a p b)]
       [meta-p (named! "source")]
       [human (named! "human")]
       [c2 (claim! c1 meta-p human)]
       [results (query (claim (? mc) (? base) meta-p human)
                       (claim (? base) (? l) (? pred) (? r)))])
  (check-true (>= (length results) 1))
  (let ([r (findf (λ (s) (equal? (hash-ref s 'base) c1)) results)])
    (check-not-false r)
    (check-equal? (hash-ref r 'l) a)
    (check-equal? (hash-ref r 'pred) p)
    (check-equal? (hash-ref r 'r) b))
  (displayln "PASS 8 — meta-claims (claims about claims)"))

;; 9. Literal in rule body resolves correctly
(reset-store!)
(reset-rules!)

(define-rule (has-symbol (? obj))
  (triple (? obj) (? sym) (? val))
  (triple (? sym) (? sym) "symbol"))

(let* ([tom (named! "tom")]
       [lonely (entity!)]
       [results (query (has-symbol (? x)))])
  (check-true (ormap (λ (s) (equal? (hash-ref s 'x) tom)) results))
  (check-false (ormap (λ (s) (equal? (hash-ref s 'x) lonely)) results))
  (displayln "PASS 9 — literal resolution in rule bodies"))

(displayln "")
(displayln "All Datalog tests passed.")

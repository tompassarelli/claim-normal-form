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

;; 10. Diamond graph — no duplicate tuples in transitive closure
(reset-store!)
(reset-rules!)

(let ()
  (define ep (named! "edge"))
  (define n1 (named! "n1"))
  (define n2 (named! "n2"))
  (define n3 (named! "n3"))
  (define n4 (named! "n4"))
  ;; Diamond: n1->n2, n1->n3, n2->n4, n3->n4
  (void (claim! n1 ep n2))
  (void (claim! n1 ep n3))
  (void (claim! n2 ep n4))
  (void (claim! n3 ep n4))

  (define-rule (reach (? x) (? y))
    (triple (? x) ep (? y)))
  (define-rule (reach (? x) (? z))
    (triple (? x) ep (? y))
    (reach (? y) (? z)))

  (define results (query (reach (? from) (? to))))
  ;; n1->n2, n1->n3, n1->n4, n2->n4, n3->n4 = 5 paths
  ;; n1->n4 must appear exactly once despite two diamond paths
  (define n1-to-n4
    (filter (λ (s) (and (equal? (hash-ref s 'from) n1)
                        (equal? (hash-ref s 'to) n4)))
            results))
  (check-equal? (length n1-to-n4) 1)
  (check-equal? (length results) 5)
  (displayln "PASS 10 — diamond graph, no duplicate tuples"))

;; 11. Multiple IDB body atoms — join across two derived relations
(reset-store!)
(reset-rules!)

(let ()
  (define ep (named! "edge"))
  (define tp (named! "type"))
  (define a (named! "a"))
  (define b (named! "b"))
  (define c (named! "c"))
  (void (claim! a ep b))
  (void (claim! b ep c))
  (void (claim! a tp (value! "source")))
  (void (claim! c tp (value! "sink")))

  (define-rule (reach2 (? x) (? y))
    (triple (? x) ep (? y)))
  (define-rule (reach2 (? x) (? z))
    (triple (? x) ep (? y))
    (reach2 (? y) (? z)))

  (define-rule (typed (? x) (? t))
    (triple (? x) tp (? tv))
    (value (? tv) (? t)))

  ;; Rule with two IDB body atoms
  (define-rule (source-to-sink (? s) (? t))
    (typed (? s) "source")
    (reach2 (? s) (? t))
    (typed (? t) "sink"))

  (define results (query (source-to-sink (? src) (? dst))))
  (check-equal? (length results) 1)
  (check-equal? (hash-ref (first results) 'src) a)
  (check-equal? (hash-ref (first results) 'dst) c)
  (displayln "PASS 11 — multiple IDB body atoms join correctly"))

;; 12. EDB-only rules terminate without IDB iteration
(reset-store!)
(reset-rules!)

(let ()
  (define p (named! "color"))
  (define x (named! "sky"))
  (claim! x p (value! "blue"))

  (define-rule (colored (? obj) (? color))
    (triple (? obj) p (? cv))
    (value (? cv) (? color)))

  (define results (query (colored (? what) (? col))))
  (check-equal? (length results) 1)
  (check-equal? (hash-ref (first results) 'col) "blue")
  (displayln "PASS 12 — EDB-only rule fires without IDB iteration"))

;; 13. Homoiconic rules — define-rule!/claims creates entity with proper claims
(reset-store!)
(reset-rules!)
(setup-rule-predicates!)

(let ()
  (define ep (named! "edge"))
  (define a (named! "a"))
  (define b (named! "b"))
  (void (claim! a ep b))

  (define rule-ent
    (define-rule!/claims
      (atom 'connected (list (var 'x) (var 'y)))
      (list (atom 'triple (list (var 'x) ep (var 'y))))))

  (check-true (object-exists? rule-ent))
  (check-not-false (member rule-ent (list-rule-entities)))

  (define head-claims (current-claims-where #:l rule-ent #:p (rule-head-rel-pred)))
  (check-equal? (length head-claims) 1)
  (check-equal? (resolve-value (list-ref (first head-claims) 3)) "connected")

  (define src-claims (current-claims-where #:l rule-ent #:p (rule-source-pred)))
  (check-equal? (length src-claims) 1)

  (define results (query (connected (? x) (? y))))
  (check-equal? (length results) 1)
  (check-equal? (hash-ref (first results) 'x) a)
  (check-equal? (hash-ref (first results) 'y) b)
  (displayln "PASS 13 — homoiconic rule: define, query, inspect as claims"))

;; 14. Homoiconic rules — supersede-rule! replaces rule and updates derived facts
(reset-store!)
(reset-rules!)
(setup-rule-predicates!)
(define sup-pred (named! "supersedes"))
(set-supersedes-pred! sup-pred)

(let ()
  (define ep (named! "edge"))
  (define a (named! "a"))
  (define b (named! "b"))
  (define c (named! "c"))
  (void (claim! a ep b))
  (void (claim! b ep c))

  (define old-rule-ent
    (define-rule!/claims
      (atom 'linked (list (var 'x) (var 'y)))
      (list (atom 'triple (list (var 'x) ep (var 'y))))))

  (define r1 (query (linked (? x) (? y))))
  (check-equal? (length r1) 2)

  (define new-rule-ent
    (supersede-rule! old-rule-ent
      (atom 'linked (list (var 'x) (var 'z)))
      (list (atom 'triple (list (var 'x) ep (var 'y)))
            (atom 'triple (list (var 'y) ep (var 'z))))))

  (check-false (member old-rule-ent (list-rule-entities)))
  (check-not-false (member new-rule-ent (list-rule-entities)))

  (define old-head-claims (claims-where #:l old-rule-ent #:p (rule-head-rel-pred)))
  (check-true
    (andmap (lambda (c) (superseded? (first c))) old-head-claims))

  (define r2 (query (linked (? x) (? z))))
  (check-equal? (length r2) 1)
  (check-equal? (hash-ref (first r2) 'x) a)
  (check-equal? (hash-ref (first r2) 'z) c)
  (displayln "PASS 14 — homoiconic rule: supersede updates derived facts"))

;; 15. Incremental rule addition — define rule without full fixpoint recompute
(reset-store!)
(reset-rules!)
(setup-rule-predicates!)

(let ()
  (define ep (named! "edge"))
  (define a (named! "a"))
  (define b (named! "b"))
  (define c (named! "c"))
  (void (claim! a ep b))
  (void (claim! b ep c))

  ;; Materialize base rules
  (define-rule (direct (? x) (? y))
    (triple (? x) ep (? y)))
  (materialize!)

  ;; Verify base rule works
  (define r0 (query (direct (? x) (? y))))
  (check-equal? (length r0) 2)

  ;; Add a new rule incrementally (matview should stay valid)
  (define rule-ent
    (define-rule!/claims
      (atom 'two-hop (list (var 'x) (var 'z)))
      (list (atom 'direct (list (var 'x) (var 'y)))
            (atom 'direct (list (var 'y) (var 'z))))))

  ;; Matview should still be valid (incremental, not invalidated)
  (check-true (ctx-ref 'matview-valid? #f))

  ;; Query the new rule — should work without full recompute
  (define r1 (query (two-hop (? x) (? z))))
  (check-equal? (length r1) 1)
  (check-equal? (hash-ref (first r1) 'x) a)
  (check-equal? (hash-ref (first r1) 'z) c)

  ;; Base rule still works
  (define r2 (query (direct (? x) (? y))))
  (check-equal? (length r2) 2)

  (displayln "PASS 15 — incremental rule addition without full recompute"))

(displayln "")
(displayln "All Datalog tests passed.")

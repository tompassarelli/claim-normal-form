#lang racket

(require rackunit
         "cnf.rkt")

;; 1. Entities get unique opaque IDs
(reset-store!)
(let ([a (entity!)]
      [b (entity!)]
      [c (entity!)])
  (check-not-equal? a b)
  (check-not-equal? b c)
  (check-not-equal? a c)
  (check-pred string? a)
  (displayln "PASS 1 — entities get unique opaque IDs"))

;; 2. Claims have l/p/r structure pointing to objects
(reset-store!)
(let* ([x (entity!)]
       [p (entity!)]
       [y (entity!)]
       [c (claim! x p y)]
       [found (claims-about x)])
  (check-equal? (length found) 1)
  (let ([row (first found)])
    (check-equal? (second row) p)
    (check-equal? (third row) y))
  (displayln "PASS 2 — claims have l/p/r structure"))

;; 3. Predicates are ordinary objects
(reset-store!)
(let ([p (entity!)])
  (check-not-false (member p (all-objects)))
  (let ([a (entity!)] [b (entity!)])
    (claim! a p b)
    (check-not-false (member p (all-objects))))
  (displayln "PASS 3 — predicates are ordinary objects"))

;; 4. Values ground through interned value objects
(reset-store!)
(let ([v (value! "hello")])
  (check-equal? (resolve-value v) "hello")
  (check-not-false (member v (all-objects)))
  (let ([o (entity!)])
    (check-false (resolve-value o)))
  (displayln "PASS 4 — values ground through value objects"))

;; 5. Claims are objects (can appear in l/p/r of other claims)
(reset-store!)
(let* ([a (entity!)]
       [p (entity!)]
       [b (entity!)]
       [c1 (claim! a p b)]
       [meta-p (entity!)]
       [tag (entity!)]
       [c2 (claim! c1 meta-p tag)])
  (check-not-false (member c1 (all-objects)))
  (check-not-false (member c2 (all-objects)))
  (let ([about-c1 (claims-about c1)])
    (check-equal? (length about-c1) 1)
    (check-equal? (third (first about-c1)) tag))
  (displayln "PASS 5 — claims are objects"))

;; 6. Symbols are claims, not IDs
(reset-store!)
(let* ([tom (named! "tom")]
       [sym-claims (claims-about tom)])
  (check-true (>= (length sym-claims) 1))
  (check-pred string? tom)
  (check-false (equal? tom "tom"))
  (check-equal? (resolve-symbol "tom") tom)
  (displayln "PASS 6 — symbols are claims, not IDs"))

;; 7. Rename is cheap (one claim, references don't change)
(reset-store!)
(let* ([alice-id (named! "alice")]
       [p (entity!)]
       [b (entity!)]
       [c (claim! alice-id p b)])
  (named! "bob")
  (claim! alice-id (symbol-predicate-id) (value! "alicia"))
  (check-equal? (resolve-symbol "alicia") alice-id)
  (let ([found (claims-about alice-id)])
    (check-true (>= (length found) 2)))
  (displayln "PASS 7 — rename is cheap"))

;; 8. claim-v! is sugar over value! + claim!
(reset-store!)
(let* ([a (entity!)]
       [p (entity!)]
       [objs-before (length (all-objects))])
  (define-values (cid vid) (claim-v! a p "42"))
  (let ([objs-after (length (all-objects))])
    (check-equal? (- objs-after objs-before) 2)
    (check-equal? (resolve-value vid) "42")
    (let ([row (first (claims-where #:l a #:p p #:r vid))])
      (check-equal? (first row) cid)))
  (displayln "PASS 8 — claim-v! is sugar over value! + claim!"))

;; 9. Value interning — same literal returns same ID
(reset-store!)
(let* ([v1 (value! "hello")]
       [v2 (value! "hello")]
       [v3 (value! "world")])
  (check-equal? v1 v2)
  (check-not-equal? v1 v3)
  (check-equal? (resolve-value v1) "hello")
  (check-equal? (resolve-value v3) "world")
  (displayln "PASS 9 — value interning"))

;; 10. Value #f is a valid literal — not confused with "no grounding"
(reset-store!)
(let* ([vf1 (value! #f)]
       [vf2 (value! #f)]
       [vt (value! #t)])
  (check-equal? vf1 vf2)
  (check-not-equal? vf1 vt)
  (check-equal? (resolve-value vf1) #f)
  (check-equal? (resolve-value vt) #t)
  (check-true (value-object? vf1))
  (check-true (value-object? vt))
  (check-false (value-object? (entity!)))
  (displayln "PASS 10 — #f is a valid value literal"))

(displayln "")
(displayln "All tests passed.")

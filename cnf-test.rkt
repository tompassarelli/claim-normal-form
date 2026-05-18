#lang racket

(require rackunit
         "cnf.rkt")

;; Reset before each group to keep tests independent.

;; 1. Objects get unique opaque IDs
(reset-store!)
(let ([a (object!)]
      [b (object!)]
      [c (object!)])
  (check-not-equal? a b)
  (check-not-equal? b c)
  (check-not-equal? a c)
  (check-pred string? a)
  (displayln "PASS 1 — objects get unique opaque IDs"))

;; 2. Claims have l/p/r structure pointing to objects
(reset-store!)
(let* ([x (object!)]
       [p (object!)]
       [y (object!)]
       [c (claim! x p y)]
       [found (claims-about x)])
  (check-equal? (length found) 1)
  (let ([row (first found)])
    (check-equal? (second row) p)
    (check-equal? (third row) y))
  (displayln "PASS 2 — claims have l/p/r structure"))

;; 3. Predicates are ordinary objects
(reset-store!)
(let ([p (object!)])
  (check-not-false (member p (all-objects)))
  ;; use it as predicate
  (let ([a (object!)] [b (object!)])
    (claim! a p b)
    ;; p still in objects, no special bucket
    (check-not-false (member p (all-objects))))
  (displayln "PASS 3 — predicates are ordinary objects"))

;; 4. Values ground through objects
(reset-store!)
(let ([v (value! "hello")])
  (check-equal? (resolve-value v) "hello")
  (check-not-false (member v (all-objects)))
  ;; bare object has no value
  (let ([o (object!)])
    (check-false (resolve-value o)))
  (displayln "PASS 4 — values ground through objects"))

;; 5. Claims are objects (can appear in l/p/r of other claims)
(reset-store!)
(let* ([a (object!)]
       [p (object!)]
       [b (object!)]
       [c1 (claim! a p b)]
       ;; c1 is an object — use it in another claim
       [meta-p (object!)]
       [tag (object!)]
       [c2 (claim! c1 meta-p tag)])
  (check-not-false (member c1 (all-objects)))
  (check-not-false (member c2 (all-objects)))
  ;; can query claims about the claim-object
  (let ([about-c1 (claims-about c1)])
    (check-equal? (length about-c1) 1)
    (check-equal? (third (first about-c1)) tag))
  (displayln "PASS 5 — claims are objects"))

;; 6. Symbols are claims, not IDs
(reset-store!)
(let* ([tom (named! "tom")]
       [sym-claims (claims-about tom)])
  ;; named! creates a claim linking tom -> symbol -> value("tom")
  (check-true (>= (length sym-claims) 1))
  ;; the symbol is stored as a claim, not baked into the ID
  (check-pred string? tom)
  (check-false (equal? tom "tom"))
  ;; resolve round-trips
  (check-equal? (resolve-symbol "tom") tom)
  (displayln "PASS 6 — symbols are claims, not IDs"))

;; 7. Rename is cheap (one claim, references don't change)
(reset-store!)
(let* ([alice-id (named! "alice")]
       [p (object!)]
       [b (object!)]
       [c (claim! alice-id p b)])
  ;; rename: attach a new symbol claim
  (named! "bob")  ; different object — we want to rename alice-id
  ;; Actually: rename means new symbol claim on same object.
  ;; Remove old symbol claim and add new one.
  ;; In this minimal store we just add another symbol claim.
  (claim! alice-id (symbol-predicate-id) (value! "alicia"))
  ;; alice-id hasn't changed
  (check-equal? (resolve-symbol "alicia") alice-id)
  ;; existing claim still points at alice-id, untouched
  (let ([found (claims-about alice-id)])
    (check-true (>= (length found) 2))) ; symbol + the p->b claim + rename
  (displayln "PASS 7 — rename is cheap"))

;; 8. claim-v! is sugar over value! + claim!
(reset-store!)
(let* ([a (object!)]
       [p (object!)]
       [objs-before (length (all-objects))])
  (define-values (cid vid) (claim-v! a p "42"))
  (let ([objs-after (length (all-objects))])
    ;; should have added exactly 2 objects: the value and the claim
    (check-equal? (- objs-after objs-before) 2)
    (check-equal? (resolve-value vid) "42")
    ;; the claim links a -> p -> vid
    (let ([row (first (claims-where #:l a #:p p #:r vid))])
      (check-equal? (first row) cid)))
  (displayln "PASS 8 — claim-v! is sugar over value! + claim!"))

(displayln "")
(displayln "All tests passed.")

#lang racket

(require rackunit
         cnf/private/kernel
         cnf/private/datalog
         cnf/private/eval)

;; 1. Add: 2 + 3 = 5
(reset-store!)
(reset-rules!)
(setup-eval!)

(let* ([add-op (named! "add")]
       [two (value! 2)]
       [three (value! 3)]
       [e (expr! add-op two three)]
       [env (entity!)])
  (register-primitive! add-op +)
  (define evs (run! env))
  (check-equal? (length evs) 1)
  (check-equal? (eval-result (first evs)) 5)
  (displayln "PASS 1 — add: 2 + 3 = 5"))

;; 2. Multiply: 2 * 3 = 6
(reset-store!)
(reset-rules!)
(setup-eval!)

(let* ([mul-op (named! "multiply")]
       [two (value! 2)]
       [three (value! 3)]
       [e (expr! mul-op two three)]
       [env (entity!)])
  (register-primitive! mul-op *)
  (define evs (run! env))
  (check-equal? (length evs) 1)
  (check-equal? (eval-result (first evs)) 6)
  (displayln "PASS 2 — multiply: 2 * 3 = 6"))

;; 3. Nested: (1 + 2) * 4 = 12
(reset-store!)
(reset-rules!)
(setup-eval!)

(let* ([add-op (named! "add")]
       [mul-op (named! "multiply")]
       [one (value! 1)]
       [two (value! 2)]
       [four (value! 4)]
       [inner (expr! add-op one two)]
       [outer (expr! mul-op inner four)]
       [env (entity!)])
  (register-primitive! add-op +)
  (register-primitive! mul-op *)
  (define evs (run! env))
  (check-equal? (length evs) 2)
  (check-equal? (eval-result (first evs)) 3)
  (check-equal? (eval-result (second evs)) 12)
  (displayln "PASS 3 — nested: (1 + 2) * 4 = 12"))

;; 4. No double evaluation
(reset-store!)
(reset-rules!)
(setup-eval!)

(let* ([add-op (named! "add")]
       [two (value! 2)]
       [three (value! 3)]
       [e (expr! add-op two three)]
       [env (entity!)])
  (register-primitive! add-op +)
  (define evs (run! env))
  (check-equal? (length evs) 1)
  (define evs2 (run! env))
  (check-equal? (length evs2) 0)
  (displayln "PASS 4 — no double evaluation"))

;; 5. Eval events are queryable claims
(reset-store!)
(reset-rules!)
(setup-eval!)

(let* ([add-op (named! "add")]
       [two (value! 2)]
       [three (value! 3)]
       [e (expr! add-op two three)]
       [env (entity!)])
  (register-primitive! add-op +)
  (define evs (run! env))
  (define ev (first evs))
  (define ev-claims (claims-about ev))
  (check-equal? (length ev-claims) 3)
  (define results (query (triple ev (evaluated-pred) (? expr))))
  (check-equal? (length results) 1)
  (check-equal? (hash-ref (first results) 'expr) e)
  (displayln "PASS 5 — eval events are queryable claims"))

;; 6. Result values are interned
(reset-store!)
(reset-rules!)
(setup-eval!)

(let* ([add-op (named! "add")]
       [v2 (value! 2)]
       [v3 (value! 3)]
       [e1 (expr! add-op v2 v3)]
       [v1 (value! 1)]
       [v4 (value! 4)]
       [e2 (expr! add-op v1 v4)]
       [env (entity!)])
  (register-primitive! add-op +)
  (define evs (run! env))
  (check-equal? (length evs) 2)
  (check-true (andmap (λ (r) (equal? r 5)) (map eval-result evs)))
  (define r1-claims (claims-where #:l (first evs) #:p (result-pred)))
  (define r2-claims (claims-where #:l (second evs) #:p (result-pred)))
  (define r1-val (list-ref (first r1-claims) 3))
  (define r2-val (list-ref (first r2-claims) 3))
  (check-equal? r1-val r2-val)
  (check-equal? (resolve-value r1-val) 5)
  (displayln "PASS 6 — result values are interned"))

(displayln "")
(displayln "All eval tests passed.")

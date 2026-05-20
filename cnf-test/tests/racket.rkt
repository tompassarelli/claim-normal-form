#lang racket

(require rackunit
         cnf/private/kernel
         cnf/private/datalog
         cnf/private/graph
         cnf/private/racket)

(define (fresh!)
  (reset-store!)
  (setup-graph!)
  (setup-racket-lang!))

(define (get-rkt-params fn-id)
  (define param-claims (current-claims-where #:l fn-id #:p (rkt-has-param-pred)))
  (define params
    (for/list ([c (in-list param-claims)])
      (define pid (list-ref c 3))
      (define pos-claims (current-claims-where #:l pid #:p (rkt-position-pred)))
      (define pos (if (null? pos-claims) 999
                      (resolve-value (list-ref (first pos-claims) 3))))
      (cons pos pid)))
  (map cdr (sort params < #:key car)))

(define (get-rkt-body fn-id)
  (define cs (current-claims-where #:l fn-id #:p (rkt-body-pred)))
  (and (not (null? cs))
       (list-ref (first cs) 3)))

;; 1. Parse function definition
(fresh!)
(let ()
  (define fns (parse-racket-program! "(define (add x y) (+ x y))"))
  (check-equal? (length fns) 1)
  (check-equal? (render-ref (first fns)) "add")
  (define params (get-rkt-params (first fns)))
  (check-equal? (length params) 2)
  (check-equal? (render-ref (first params)) "x")
  (check-equal? (render-ref (second params)) "y")
  (displayln "PASS 1 — parse function definition"))

;; 2. Parse constant definition
(fresh!)
(let ()
  (define fns (parse-racket-program! "(define pi 3.14159)"))
  (check-equal? (length fns) 1)
  (check-equal? (render-ref (first fns)) "pi")
  (define kind-cs (current-claims-where #:l (first fns) #:p (rkt-form-kind-pred)))
  (check-equal? (resolve-value (list-ref (first kind-cs) 3)) "constant")
  (displayln "PASS 2 — parse constant definition"))

;; 3. Parse struct definition
(fresh!)
(let ()
  (define fns (parse-racket-program! "(struct point (x y z))"))
  (check-equal? (length fns) 1)
  (check-equal? (render-ref (first fns)) "point")
  (define kind-cs (current-claims-where #:l (first fns) #:p (rkt-form-kind-pred)))
  (check-equal? (resolve-value (list-ref (first kind-cs) 3)) "struct")
  (define field-cs (current-claims-where #:l (first fns) #:p (rkt-has-field-pred)))
  (check-equal? (length field-cs) 3)
  (displayln "PASS 3 — parse struct definition"))

;; 4. rkt-fn-depends-on via Datalog
(fresh!)
(let ()
  (define fns (parse-racket-program! "
(define (helper x) (+ x 1))
(define (caller a) (helper a))
"))
  (define deps (query (rkt-fn-depends-on (? caller) (? callee))))
  (define found
    (findf (lambda (d)
             (and (equal? (render-ref (hash-ref d 'caller)) "caller")
                  (equal? (render-ref (hash-ref d 'callee)) "helper")))
           deps))
  (check-not-false found)
  (displayln "PASS 4 — rkt-fn-depends-on via Datalog"))

;; 5. Rename propagates to call sites
(fresh!)
(let ()
  (define fns (parse-racket-program! "
(define (old-name x) (+ x 1))
(define (user a) (old-name a))
"))
  (rename! (first fns) "new-name")
  (check-equal? (render-ref (first fns)) "new-name")
  (define rendered (render-racket-program fns))
  (check-true (string-contains? rendered "new-name"))
  (check-false (string-contains? rendered "old-name"))
  (displayln "PASS 5 — rename propagates"))

;; 6. Parse if/cond/when/unless
(fresh!)
(let ()
  (define fns (parse-racket-program! "
(define (classify x)
  (cond
    [(> x 0) \"positive\"]
    [(< x 0) \"negative\"]
    [else \"zero\"]))
"))
  (check-equal? (length fns) 1)
  (define body (get-rkt-body (first fns)))
  (check-not-false body)
  (displayln "PASS 6 — parse if/cond/when/unless"))

;; 7. Parse let/let* bindings
(fresh!)
(let ()
  (define fns (parse-racket-program! "
(define (compute x y)
  (let ([sum (+ x y)]
        [diff (- x y)])
    (* sum diff)))
"))
  (check-equal? (length fns) 1)
  (define body (get-rkt-body (first fns)))
  (check-not-false body)
  (displayln "PASS 7 — parse let/let* bindings"))

;; 8. Parse lambda expressions
(fresh!)
(let ()
  (define fns (parse-racket-program! "
(define (higher xs)
  (map (lambda (x) (+ x 1)) xs))
"))
  (check-equal? (length fns) 1)
  (define rendered (render-racket-fn (first fns)))
  (check-true (string-contains? rendered "lambda"))
  (displayln "PASS 8 — parse lambda expressions"))

;; 9. Incremental add-racket-function!
(fresh!)
(let ()
  (parse-racket-program! "(define (base x) (+ x 1))")
  (define new-fn (add-racket-function! "(define (caller a) (base a))"))
  (define deps (query (rkt-fn-depends-on (? caller) (? callee))))
  (define found
    (findf (lambda (d)
             (and (equal? (render-ref (hash-ref d 'caller)) "caller")
                  (equal? (render-ref (hash-ref d 'callee)) "base")))
           deps))
  (check-not-false found)
  (displayln "PASS 9 — incremental add-racket-function!"))

;; 10. Incremental remove-racket-function!
(fresh!)
(let ()
  (parse-racket-program! "
(define (target x) (+ x 1))
(define (other x) (* x 2))
")
  (remove-racket-function! "target")
  (check-false (resolve-symbol "target"))
  (check-not-false (resolve-symbol "other"))
  (displayln "PASS 10 — incremental remove-racket-function!"))

;; 11. modify-racket-function! preserves entity, updates params
(fresh!)
(let ()
  (define fns (parse-racket-program! "(define (helper x) (+ x 1))"))
  (define original-id (first fns))
  (modify-racket-function! "helper" "(define (helper x y) (* x y))")
  (define params (get-rkt-params original-id))
  (check-equal? (length params) 2)
  (check-equal? (render-ref (first params)) "x")
  (check-equal? (render-ref (second params)) "y")
  (displayln "PASS 11 — modify-racket-function! preserves entity, updates params"))

;; 12. modify-racket-function! with rename
(fresh!)
(let ()
  (define fns (parse-racket-program! "(define (old-fn x) (+ x 1))"))
  (modify-racket-function! "old-fn" "(define (new-fn x y) (* x y))")
  (check-equal? (render-ref (first fns)) "new-fn")
  (define params (get-rkt-params (first fns)))
  (check-equal? (length params) 2)
  (displayln "PASS 12 — modify-racket-function! with rename"))

;; 13. Render round-trip preserves structure
(fresh!)
(let ()
  (define fns (parse-racket-program! "(define (add x y) (+ x y))"))
  (define rendered (render-racket-fn (first fns)))
  (check-true (string-contains? rendered "define"))
  (check-true (string-contains? rendered "add"))
  (check-true (string-contains? rendered "x"))
  (check-true (string-contains? rendered "y"))
  (displayln "PASS 13 — render round-trip preserves structure"))

;; 14. Multiple top-level forms
(fresh!)
(let ()
  (define fns (parse-racket-program! "
(struct point (x y))
(define pi 3.14)
(define (distance p1 p2) (+ (point-x p1) (point-x p2)))
"))
  (check-equal? (length fns) 3)
  (define kinds
    (for/list ([f fns])
      (define ks (current-claims-where #:l f #:p (rkt-form-kind-pred)))
      (resolve-value (list-ref (first ks) 3))))
  (check-equal? kinds '("struct" "constant" "function"))
  (displayln "PASS 14 — multiple top-level forms"))

;; 15. Dependency chain a->b->c
(fresh!)
(let ()
  (parse-racket-program! "
(define (a x) (+ x 1))
(define (b x) (a x))
(define (c x) (b x))
")
  (define deps (query (rkt-fn-depends-on (? caller) (? callee))))
  (define b-a
    (findf (lambda (d)
             (and (equal? (render-ref (hash-ref d 'caller)) "b")
                  (equal? (render-ref (hash-ref d 'callee)) "a")))
           deps))
  (define c-b
    (findf (lambda (d)
             (and (equal? (render-ref (hash-ref d 'caller)) "c")
                  (equal? (render-ref (hash-ref d 'callee)) "b")))
           deps))
  (check-not-false b-a)
  (check-not-false c-b)
  (displayln "PASS 15 — dependency chain a->b->c"))

(displayln "")
(displayln "All racket bridge tests passed.")

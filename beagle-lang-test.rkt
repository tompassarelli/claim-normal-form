#lang racket

(require rackunit
         "cnf.rkt"
         "datalog.rkt"
         "eval.rkt"
         "graph.rkt"
         "schema.rkt"
         "beagle-lang.rkt")

(define (fresh!)
  (reset-store!)
  (setup-eval!)
  (setup-graph!)
  (setup-schema!)
  (setup-rule-predicates!)
  (setup-beagle-lang!)
  (materialize!))

;; 1. Parse defn with typed params and return type
(fresh!)
(let ()
  (define fns (parse-beagle-program! "(defn add [(x : Int) (y : Int)] : Int\n  (+ x y))"))
  (check-equal? (length fns) 1)
  (check-equal? (render-ref (first fns)) "add")
  (define params (get-ordered-params (first fns)))
  (check-equal? (length params) 2)
  (check-equal? (render-ref (first params)) "x")
  (check-equal? (render-ref (second params)) "y")
  (define ret-cs (current-claims-where #:l (first fns) #:p (return-type-pred)))
  (check-equal? (resolve-value (list-ref (first ret-cs) 3)) "Int")
  (displayln "PASS 1 — parse defn with types"))

;; 2. fn-depends-on via Datalog
(fresh!)
(let ()
  (define fns (parse-beagle-program! "
(defn helper [x y] (+ x y))
(defn caller [a b] (helper a b))
"))
  (define deps (query (fn-depends-on (? caller) (? callee))))
  (check-true (> (length deps) 0))
  (define caller-dep
    (findf (lambda (d)
             (and (equal? (render-ref (hash-ref d 'caller)) "caller")
                  (equal? (render-ref (hash-ref d 'callee)) "helper")))
           deps))
  (check-not-false caller-dep)
  (displayln "PASS 2 — fn-depends-on via Datalog"))

;; 3. Rename propagates through dependencies
(fresh!)
(let ()
  (define fns (parse-beagle-program! "
(defn old-name [x] (+ x 1))
(defn user [a] (old-name a))
"))
  (rename! (first fns) "new-name")
  (check-equal? (render-ref (first fns)) "new-name")
  (define rendered (render-beagle-program fns))
  (check-true (string-contains? rendered "new-name"))
  (check-false (string-contains? rendered "old-name"))
  (displayln "PASS 3 — rename propagates"))

;; 4. Parse defrecord with typed fields
(fresh!)
(let ()
  (define fns (parse-beagle-program! "(defrecord Point [(x : Float) (y : Float)])"))
  (check-equal? (length fns) 1)
  (check-equal? (render-ref (first fns)) "Point")
  (define field-cs (current-claims-where #:l (first fns) #:p (has-field-pred)))
  (check-equal? (length field-cs) 2)
  (displayln "PASS 4 — parse defrecord"))

;; 5. Parse def with type
(fresh!)
(let ()
  (define fns (parse-beagle-program! "(def PI : Float 3.14159)"))
  (check-equal? (length fns) 1)
  (check-equal? (render-ref (first fns)) "PI")
  (define type-cs (current-claims-where #:l (first fns) #:p (has-type-pred)))
  (check-false (null? type-cs))
  (check-equal? (resolve-value (list-ref (first type-cs) 3)) "Float")
  (displayln "PASS 5 — parse def with type"))

;; 6. Incremental add-function
(fresh!)
(let ()
  (define fns (parse-beagle-program! "(defn base [x] (+ x 1))"))
  (define new-fn (add-beagle-function! "(defn caller [a] (base a))"))
  (define deps (query (fn-depends-on (? caller) (? callee))))
  (define found
    (findf (lambda (d)
             (and (equal? (render-ref (hash-ref d 'caller)) "caller")
                  (equal? (render-ref (hash-ref d 'callee)) "base")))
           deps))
  (check-not-false found)
  (displayln "PASS 6 — incremental add-function"))

;; 7. Incremental remove-function
(fresh!)
(let ()
  (parse-beagle-program! "
(defn target [x] (+ x 1))
(defn other [x] (* x 2))
")
  (remove-beagle-function! "target")
  (check-false (resolve-symbol "target"))
  (check-not-false (resolve-symbol "other"))
  (displayln "PASS 7 — incremental remove-function"))

;; 8. Incremental modify-function
(fresh!)
(let ()
  (define fns (parse-beagle-program! "
(defn helper [x] (+ x 1))
(defn main-fn [a] (helper a))
"))
  (modify-beagle-function! "helper" "(defn helper [(x : Int)] : Int\n  (* x 2))")
  (define params (get-ordered-params (first fns)))
  (check-equal? (length params) 1)
  (define type-cs (current-claims-where #:l (first params) #:p (has-type-pred)))
  (check-false (null? type-cs))
  (check-equal? (resolve-value (list-ref (first type-cs) 3)) "Int")
  (displayln "PASS 8 — modify-function preserves entity, updates params"))

;; 9. Parse let/if expressions
(fresh!)
(let ()
  (define fns (parse-beagle-program! "
(defn calc [x y]
  (let [z (+ x y)]
    (if (> z 0)
      (* z 2)
      z)))
"))
  (check-equal? (length fns) 1)
  (define body (get-body (first fns)))
  (check-not-false body)
  (define kind-cs (current-claims-where #:l body #:p (expr-kind-pred)))
  (check-equal? (resolve-value (list-ref (first kind-cs) 3)) "let")
  (displayln "PASS 9 — parse let/if expressions"))

;; 10. Transitive dependencies
(fresh!)
(let ()
  (parse-beagle-program! "
(defn a [x] (+ x 1))
(defn b [x] (a x))
(defn c [x] (b x))
")
  (define deps (query (fn-depends-on (? caller) (? callee))))
  (define b-depends-a
    (findf (lambda (d)
             (and (equal? (render-ref (hash-ref d 'caller)) "b")
                  (equal? (render-ref (hash-ref d 'callee)) "a")))
           deps))
  (define c-depends-b
    (findf (lambda (d)
             (and (equal? (render-ref (hash-ref d 'caller)) "c")
                  (equal? (render-ref (hash-ref d 'callee)) "b")))
           deps))
  (check-not-false b-depends-a)
  (check-not-false c-depends-b)
  (displayln "PASS 10 — dependency chain a→b→c"))

;; 11. Render round-trips typed function
(fresh!)
(let ()
  (define fns (parse-beagle-program! "(defn add [(x : Int) (y : Int)] : Int\n  (+ x y))"))
  (define rendered (render-beagle-fn (first fns)))
  (check-true (string-contains? rendered "defn add"))
  (check-true (string-contains? rendered "(x : Int)"))
  (check-true (string-contains? rendered ": Int"))
  (check-true (string-contains? rendered "(+ x y)"))
  (displayln "PASS 11 — render preserves types and structure"))

;; 12. Multiple call args render correctly
(fresh!)
(let ()
  (define fns (parse-beagle-program! "
(defn target [a b c] (+ a b))
(defn caller [x y z] (target x y z))
"))
  (define rendered (render-beagle-fn (second fns)))
  (check-true (string-contains? rendered "(target x y z)"))
  (displayln "PASS 12 — multi-arg call renders correctly"))

;; 13. Parse fn (lambda) in expression position
(fresh!)
(let ()
  (define fns (parse-beagle-program! "(defn higher [xs] (map (fn [x] (+ x 1)) xs))"))
  (check-equal? (length fns) 1)
  (define body (get-body (first fns)))
  (check-not-false body)
  (displayln "PASS 13 — parse fn (lambda) in expression"))

;; 14. Mixed form types in one program
(fresh!)
(let ()
  (define fns (parse-beagle-program! "
(def MAX : Int 100)
(defrecord Config [(name : String) (value : Int)])
(defn validate [(c : Config)] : Bool
  (< (:value c) MAX))
"))
  (check-equal? (length fns) 3)
  (define kinds
    (for/list ([f fns])
      (define ks (current-claims-where #:l f #:p (form-kind-pred)))
      (resolve-value (list-ref (first ks) 3))))
  (check-equal? kinds '("def" "defrecord" "defn"))
  (displayln "PASS 14 — mixed form types"))

;; 15. Modify with rename
(fresh!)
(let ()
  (define fns (parse-beagle-program! "(defn old-fn [x] (+ x 1))"))
  (modify-beagle-function! "old-fn" "(defn new-fn [x y] (* x y))")
  (check-equal? (render-ref (first fns)) "new-fn")
  (define params (get-ordered-params (first fns)))
  (check-equal? (length params) 2)
  (displayln "PASS 15 — modify with rename"))

(displayln "")
(displayln "All beagle-lang tests passed.")

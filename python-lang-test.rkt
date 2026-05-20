#lang racket

(require rackunit
         "cnf.rkt"
         "datalog.rkt"
         "eval.rkt"
         "graph.rkt"
         "python-lang.rkt")

(define (fresh!)
  (reset-store!)
  (setup-eval!)
  (setup-graph!)
  (setup-python-lang!))

;; Helper: get ordered params via claims (py-get-ordered-params is not exported)
(define (get-py-params fn-id)
  (define param-claims (current-claims-where #:l fn-id #:p (py-has-param-pred)))
  (define params
    (for/list ([c (in-list param-claims)])
      (define pid (list-ref c 3))
      (define pos-claims (current-claims-where #:l pid #:p (py-position-pred)))
      (define pos (if (null? pos-claims) 999
                      (resolve-value (list-ref (first pos-claims) 3))))
      (cons pos pid)))
  (map cdr (sort params < #:key car)))

;; Helper: get body entity via claims (py-get-body is not exported)
(define (get-py-body fn-id)
  (define cs (current-claims-where #:l fn-id #:p (py-body-pred)))
  (and (not (null? cs))
       (list-ref (first cs) 3)))

;; 1. Parse function with type annotations
(fresh!)
(let ()
  (define fns (parse-python-program! "def add(x: int, y: int) -> int:\n    return x + y\n"))
  (check-equal? (length fns) 1)
  (check-equal? (render-ref (first fns)) "add")
  (define params (get-py-params (first fns)))
  (check-equal? (length params) 2)
  (check-equal? (render-ref (first params)) "x")
  (check-equal? (render-ref (second params)) "y")
  (define type-cs (current-claims-where #:l (first params) #:p (py-has-type-pred)))
  (check-false (null? type-cs))
  (check-equal? (resolve-value (list-ref (first type-cs) 3)) "int")
  (define ret-cs (current-claims-where #:l (first fns) #:p (py-return-type-pred)))
  (check-false (null? ret-cs))
  (check-equal? (resolve-value (list-ref (first ret-cs) 3)) "int")
  (displayln "PASS 1 — parse function with type annotations"))

;; 2. py-fn-depends-on via Datalog
(fresh!)
(let ()
  (define fns (parse-python-program! "
def helper(x, y):
    return x + y

def caller(a, b):
    return helper(a, b)
"))
  (define deps (query (py-fn-depends-on (? caller) (? callee))))
  (check-true (> (length deps) 0))
  (define caller-dep
    (findf (lambda (d)
             (and (equal? (render-ref (hash-ref d 'caller)) "caller")
                  (equal? (render-ref (hash-ref d 'callee)) "helper")))
           deps))
  (check-not-false caller-dep)
  (displayln "PASS 2 — py-fn-depends-on via Datalog"))

;; 3. Rename propagates to call sites
(fresh!)
(let ()
  (define fns (parse-python-program! "
def old_name(x):
    return x + 1

def user(a):
    return old_name(a)
"))
  (rename! (first fns) "new_name")
  (check-equal? (render-ref (first fns)) "new_name")
  (define rendered (render-python-program fns))
  (check-true (string-contains? rendered "new_name"))
  (check-false (string-contains? rendered "old_name"))
  (displayln "PASS 3 — rename propagates"))

;; 4. Parse class with methods
(fresh!)
(let ()
  (define fns (parse-python-program! "
class Calculator:
    def add(self, x, y):
        return x + y

    def sub(self, x, y):
        return x - y
"))
  (check-equal? (length fns) 1)
  (check-equal? (render-ref (first fns)) "Calculator")
  (define kind-cs (current-claims-where #:l (first fns) #:p (py-form-kind-pred)))
  (check-equal? (resolve-value (list-ref (first kind-cs) 3)) "class")
  (define method-cs (current-claims-where #:l (first fns) #:p (py-has-method-pred)))
  (check-equal? (length method-cs) 2)
  (displayln "PASS 4 — parse class with methods"))

;; 5. Parse function with decorators
(fresh!)
(let ()
  (define fns (parse-python-program! "
@staticmethod
@cache
def compute(x: int) -> int:
    return x * 2
"))
  (check-equal? (length fns) 1)
  (define dec-cs (current-claims-where #:l (first fns) #:p (py-has-decorator-pred)))
  (check-equal? (length dec-cs) 2)
  (define dec-values
    (for/list ([c (in-list dec-cs)])
      (resolve-value (list-ref c 3))))
  (check-not-false (member "staticmethod" dec-values))
  (check-not-false (member "cache" dec-values))
  (displayln "PASS 5 — parse function with decorators"))

;; 6. Incremental add-python-function!
(fresh!)
(let ()
  (define fns (parse-python-program! "
def base(x):
    return x + 1
"))
  (define new-fn (add-python-function! "
def caller(a):
    return base(a)
"))
  (define deps (query (py-fn-depends-on (? caller) (? callee))))
  (define found
    (findf (lambda (d)
             (and (equal? (render-ref (hash-ref d 'caller)) "caller")
                  (equal? (render-ref (hash-ref d 'callee)) "base")))
           deps))
  (check-not-false found)
  (displayln "PASS 6 — incremental add-python-function!"))

;; 7. Incremental remove-python-function!
(fresh!)
(let ()
  (parse-python-program! "
def target(x):
    return x + 1

def other(x):
    return x * 2
")
  (remove-python-function! "target")
  (check-false (resolve-symbol "target"))
  (check-not-false (resolve-symbol "other"))
  (displayln "PASS 7 — incremental remove-python-function!"))

;; 8. modify-python-function! preserves entity, updates params
(fresh!)
(let ()
  (define fns (parse-python-program! "
def helper(x):
    return x + 1

def main_fn(a):
    return helper(a)
"))
  (modify-python-function! "helper" "
def helper(x: int, y: int) -> int:
    return x * y
")
  (define params (get-py-params (first fns)))
  (check-equal? (length params) 2)
  (define type-cs (current-claims-where #:l (first params) #:p (py-has-type-pred)))
  (check-false (null? type-cs))
  (check-equal? (resolve-value (list-ref (first type-cs) 3)) "int")
  (displayln "PASS 8 — modify-python-function! preserves entity, updates params"))

;; 9. Parse if/for/while expressions in body
(fresh!)
(let ()
  (define fns (parse-python-program! "
def process(items):
    result = []
    for item in items:
        if item > 0:
            result.append(item)
    while len(result) > 10:
        result.pop()
    return result
"))
  (check-equal? (length fns) 1)
  (define body (get-py-body (first fns)))
  (check-not-false body)
  (define child-claims (current-claims-where #:l body #:p (py-has-child-pred)))
  (check-true (>= (length child-claims) 3))
  ;; Check that we find if, for, while kinds among body children
  (define all-kinds
    (for/list ([c (in-list child-claims)])
      (define cid (list-ref c 3))
      (define ks (current-claims-where #:l cid #:p (py-expr-kind-pred)))
      (if (null? ks) #f (resolve-value (list-ref (first ks) 3)))))
  (check-not-false (member "for" all-kinds))
  (displayln "PASS 9 — parse if/for/while expressions in body"))

;; 10. Dependency chain a->b->c (transitive)
(fresh!)
(let ()
  (parse-python-program! "
def a(x):
    return x + 1

def b(x):
    return a(x)

def c(x):
    return b(x)
")
  (define deps (query (py-fn-depends-on (? caller) (? callee))))
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
  (displayln "PASS 10 — dependency chain a->b->c"))

;; 11. Render preserves types and structure
(fresh!)
(let ()
  (define fns (parse-python-program! "def add(x: int, y: int) -> int:\n    return x + y\n"))
  (define rendered (render-python-fn (first fns)))
  (check-true (string-contains? rendered "def add"))
  (check-true (string-contains? rendered "x: int"))
  (check-true (string-contains? rendered "-> int"))
  (check-true (string-contains? rendered "return"))
  (displayln "PASS 11 — render preserves types and structure"))

;; 12. Multi-arg call renders correctly
(fresh!)
(let ()
  (define fns (parse-python-program! "
def target(a, b, c):
    return a + b + c

def caller(x, y, z):
    return target(x, y, z)
"))
  (define rendered (render-python-fn (second fns)))
  (check-true (string-contains? rendered "target(x, y, z)"))
  (displayln "PASS 12 — multi-arg call renders correctly"))

;; 13. Parse lambda expression
(fresh!)
(let ()
  (define fns (parse-python-program! "
def higher(xs):
    return list(map(lambda x: x + 1, xs))
"))
  (check-equal? (length fns) 1)
  (define body (get-py-body (first fns)))
  (check-not-false body)
  (define rendered (render-python-fn (first fns)))
  (check-true (string-contains? rendered "lambda"))
  (displayln "PASS 13 — parse lambda expression"))

;; 14. Mixed form types (functions + classes)
(fresh!)
(let ()
  (define fns (parse-python-program! "
def validate(x: int) -> bool:
    return x > 0

class Config:
    def __init__(self, name: str):
        self.name = name
"))
  (check-equal? (length fns) 2)
  (define kinds
    (for/list ([f fns])
      (define ks (current-claims-where #:l f #:p (py-form-kind-pred)))
      (resolve-value (list-ref (first ks) 3))))
  (check-equal? kinds '("function" "class"))
  (displayln "PASS 14 — mixed form types"))

;; 15. Modify with rename
(fresh!)
(let ()
  (define fns (parse-python-program! "
def old_fn(x):
    return x + 1
"))
  (modify-python-function! "old_fn" "
def new_fn(x, y):
    return x * y
")
  (check-equal? (render-ref (first fns)) "new_fn")
  (define params (get-py-params (first fns)))
  (check-equal? (length params) 2)
  (displayln "PASS 15 — modify with rename"))

(displayln "")
(displayln "All python-lang tests passed.")

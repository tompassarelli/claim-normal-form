#lang racket

(require "cnf.rkt" "datalog.rkt" "graph.rkt" json)

(provide setup-python-lang!
         parse-python-program! parse-python-file!
         add-python-function! remove-python-function! modify-python-function!
         render-python-program render-python-fn render-python-expr
         py-has-param-pred py-position-pred py-body-pred py-calls-pred
         py-has-type-pred py-return-type-pred py-expr-kind-pred
         py-has-arg-pred py-has-child-pred py-form-kind-pred
         py-has-base-pred py-has-decorator-pred py-has-method-pred
         py-is-async-pred)

;; --- Predicate accessors ---

(define (py-has-param-pred) (ctx-ref 'py-has-param-pred))
(define (py-position-pred) (ctx-ref 'py-position-pred))
(define (py-body-pred) (ctx-ref 'py-body-pred))
(define (py-calls-pred) (ctx-ref 'py-calls-pred))
(define (py-has-type-pred) (ctx-ref 'py-has-type-pred))
(define (py-return-type-pred) (ctx-ref 'py-return-type-pred))
(define (py-expr-kind-pred) (ctx-ref 'py-expr-kind-pred))
(define (py-has-arg-pred) (ctx-ref 'py-has-arg-pred))
(define (py-has-child-pred) (ctx-ref 'py-has-child-pred))
(define (py-form-kind-pred) (ctx-ref 'py-form-kind-pred))
(define (py-has-base-pred) (ctx-ref 'py-has-base-pred))
(define (py-has-decorator-pred) (ctx-ref 'py-has-decorator-pred))
(define (py-has-method-pred) (ctx-ref 'py-has-method-pred))
(define (py-is-async-pred) (ctx-ref 'py-is-async-pred))

;; --- Setup ---

(define (setup-python-lang!)
  (ctx-set! 'py-has-param-pred (named! "py-has-param"))
  (ctx-set! 'py-position-pred (named! "py-position"))
  (ctx-set! 'py-body-pred (named! "py-body"))
  (ctx-set! 'py-calls-pred (named! "py-calls"))
  (ctx-set! 'py-has-type-pred (named! "py-has-type"))
  (ctx-set! 'py-return-type-pred (named! "py-return-type"))
  (ctx-set! 'py-expr-kind-pred (named! "py-expr-kind"))
  (ctx-set! 'py-has-arg-pred (named! "py-has-arg"))
  (ctx-set! 'py-has-child-pred (named! "py-has-child"))
  (ctx-set! 'py-form-kind-pred (named! "py-form-kind"))
  (ctx-set! 'py-has-base-pred (named! "py-has-base"))
  (ctx-set! 'py-has-decorator-pred (named! "py-has-decorator"))
  (ctx-set! 'py-has-method-pred (named! "py-has-method"))
  (ctx-set! 'py-is-async-pred (named! "py-is-async"))

  ;; Datalog rules
  (define cp (py-calls-pred))
  (define chp (py-has-child-pred))
  (define bp (py-body-pred))
  (define fkp (py-form-kind-pred))
  (define defn-val (value! "function"))
  (define class-val (value! "class"))

  (define-rule (py-contains-call (? expr) (? fn))
    (current-triple (? expr) cp (? fn)))
  (define-rule (py-contains-call (? expr) (? fn))
    (current-triple (? expr) chp (? child))
    (py-contains-call (? child) (? fn)))
  (define-rule (py-fn-depends-on (? caller) (? callee))
    (current-triple (? caller) fkp defn-val)
    (current-triple (? caller) bp (? body))
    (py-contains-call (? body) (? callee))
    (current-triple (? callee) fkp defn-val))
  (void))

;; --- Parse Python via AST helper ---

(define python-helper-path
  (path->string (build-path (current-directory) "python-ast-helper.py")))

(define (parse-python-source source)
  (define-values (proc stdout stdin stderr)
    (subprocess #f #f #f (find-executable-path "python3") python-helper-path))
  (write-string source stdin)
  (close-output-port stdin)
  (define result (port->string stdout))
  (close-input-port stdout)
  (close-input-port stderr)
  (subprocess-wait proc)
  (with-input-from-string result read-json))

(define (parse-python-program! source)
  (define ast-json (parse-python-source source))
  (define body (hash-ref ast-json 'body '()))
  (for/list ([node (in-list body)]
             #:when (member (hash-ref node 'type #f) '("function_def" "class_def")))
    (parse-top-node! node)))

(define (parse-python-file! path)
  (parse-python-program! (file->string path)))

;; --- Top-level node dispatch ---

(define (parse-top-node! node)
  (define type (hash-ref node 'type))
  (cond
    [(equal? type "function_def") (parse-function-def! node)]
    [(equal? type "class_def") (parse-class-def! node)]
    [else
     (define e (entity!))
     (claim! e (py-form-kind-pred) (value! type))
     e]))

(define (parse-function-def! node)
  (define fn (entity!))
  (give-name! fn (hash-ref node 'name))
  (claim! fn (py-form-kind-pred) (value! "function"))

  (when (hash-ref node 'async #f)
    (claim! fn (py-is-async-pred) (value! #t)))

  (when (hash-ref node 'return_annotation #f)
    (claim! fn (py-return-type-pred)
            (value! (hash-ref node 'return_annotation))))

  (for ([dec (in-list (hash-ref node 'decorators '()))])
    (claim! fn (py-has-decorator-pred) (value! dec)))

  (define params (hash-ref node 'params '()))
  (define scope (make-hash))
  (define param-entities
    (for/list ([p (in-list params)]
               [i (in-naturals)])
      (define pe (entity!))
      (give-name! pe (hash-ref p 'name))
      (claim! fn (py-has-param-pred) pe)
      (claim! pe (py-position-pred) (value! i))
      (when (hash-ref p 'annotation #f)
        (claim! pe (py-has-type-pred) (value! (hash-ref p 'annotation))))
      (when (hash-ref p 'default #f)
        (claim! pe (py-expr-kind-pred) (value! (format "default=~a" (hash-ref p 'default)))))
      (hash-set! scope (hash-ref p 'name) pe)
      pe))

  (when (hash-ref node 'vararg #f)
    (define vp (entity!))
    (give-name! vp (format "*~a" (hash-ref node 'vararg)))
    (claim! fn (py-has-param-pred) vp)
    (claim! vp (py-position-pred) (value! (length params))))

  (when (hash-ref node 'kwarg #f)
    (define kp (entity!))
    (give-name! kp (format "**~a" (hash-ref node 'kwarg)))
    (claim! fn (py-has-param-pred) kp)
    (claim! kp (py-position-pred) (value! (+ (length params) 1))))

  (define body-wrapper (entity!))
  (claim! body-wrapper (py-expr-kind-pred) (value! "block"))
  (for ([stmt (in-list (hash-ref node 'body '()))]
        [i (in-naturals)])
    (define child (parse-expr-node! stmt scope))
    (claim! body-wrapper (py-has-child-pred) child)
    (claim! child (py-position-pred) (value! i)))
  (claim! fn (py-body-pred) body-wrapper)

  fn)

(define (parse-class-def! node)
  (define cls (entity!))
  (give-name! cls (hash-ref node 'name))
  (claim! cls (py-form-kind-pred) (value! "class"))

  (for ([base (in-list (hash-ref node 'bases '()))])
    (claim! cls (py-has-base-pred) (value! base)))

  (for ([dec (in-list (hash-ref node 'decorators '()))])
    (claim! cls (py-has-decorator-pred) (value! dec)))

  (for ([member-node (in-list (hash-ref node 'body '()))])
    (define mtype (hash-ref member-node 'type #f))
    (cond
      [(equal? mtype "function_def")
       (define method (parse-function-def! member-node))
       (claim! cls (py-has-method-pred) method)
       (claim! cls (py-has-child-pred) method)]
      [else
       (define child (parse-expr-node! member-node (make-hash)))
       (claim! cls (py-has-child-pred) child)]))
  cls)

;; --- Expression walker ---

(define (parse-expr-node! node scope)
  (define type (hash-ref node 'type "unknown"))
  (cond
    [(equal? type "call")
     (define e (entity!))
     (claim! e (py-expr-kind-pred) (value! "call"))
     (define func-name (hash-ref node 'func "?"))
     (define fn-ref
       (cond
         [(hash-ref scope func-name #f) => values]
         [(resolve-py-name func-name) => values]
         [else (value! func-name)]))
     (claim! e (py-calls-pred) fn-ref)
     (for ([arg (in-list (hash-ref node 'args '()))]
           [i (in-naturals)])
       (define child (parse-expr-node! arg scope))
       (claim! e (py-has-arg-pred) child)
       (claim! child (py-position-pred) (value! i))
       (claim! e (py-has-child-pred) child))
     (for ([kw (in-list (hash-ref node 'kwargs '()))])
       (define child (parse-expr-node! (hash-ref kw 'value) scope))
       (claim! e (py-has-child-pred) child))
     e]

    [(equal? type "name")
     (define id (hash-ref node 'id "?"))
     (cond
       [(hash-ref scope id #f) => values]
       [else (value! id)])]

    [(equal? type "constant")
     (value! (hash-ref node 'value))]

    [(equal? type "attribute")
     (define e (entity!))
     (claim! e (py-expr-kind-pred) (value! "attribute"))
     (define val-node (parse-expr-node! (hash-ref node 'value) scope))
     (claim! e (py-has-child-pred) val-node)
     (define attr-name (hash-ref node 'attr "?"))
     (define attr-ref (or (resolve-py-name attr-name) (value! attr-name)))
     (claim! e (py-calls-pred) attr-ref)
     e]

    [(equal? type "return")
     (define e (entity!))
     (claim! e (py-expr-kind-pred) (value! "return"))
     (when (hash-ref node 'value #f)
       (define child (parse-expr-node! (hash-ref node 'value) scope))
       (claim! e (py-has-child-pred) child))
     e]

    [(equal? type "if")
     (define e (entity!))
     (claim! e (py-expr-kind-pred) (value! "if"))
     (define test (parse-expr-node! (hash-ref node 'test) scope))
     (claim! e (py-has-child-pred) test)
     (for ([stmt (in-list (hash-ref node 'body '()))])
       (define child (parse-expr-node! stmt scope))
       (claim! e (py-has-child-pred) child))
     (for ([stmt (in-list (hash-ref node 'orelse '()))])
       (define child (parse-expr-node! stmt scope))
       (claim! e (py-has-child-pred) child))
     e]

    [(equal? type "for")
     (define e (entity!))
     (claim! e (py-expr-kind-pred) (value! "for"))
     (define iter-expr (parse-expr-node! (hash-ref node 'iter) scope))
     (claim! e (py-has-child-pred) iter-expr)
     (define inner-scope (hash-copy scope))
     (define target-name (hash-ref node 'target "?"))
     (when (string? target-name)
       (define te (entity!))
       (give-name! te target-name)
       (hash-set! inner-scope target-name te))
     (for ([stmt (in-list (hash-ref node 'body '()))])
       (define child (parse-expr-node! stmt inner-scope))
       (claim! e (py-has-child-pred) child))
     e]

    [(equal? type "while")
     (define e (entity!))
     (claim! e (py-expr-kind-pred) (value! "while"))
     (define test (parse-expr-node! (hash-ref node 'test) scope))
     (claim! e (py-has-child-pred) test)
     (for ([stmt (in-list (hash-ref node 'body '()))])
       (define child (parse-expr-node! stmt scope))
       (claim! e (py-has-child-pred) child))
     e]

    [(equal? type "with")
     (define e (entity!))
     (claim! e (py-expr-kind-pred) (value! "with"))
     (define inner-scope (hash-copy scope))
     (for ([item (in-list (hash-ref node 'items '()))])
       (define ctx-expr (parse-expr-node! (hash-ref item 'context) scope))
       (claim! e (py-has-child-pred) ctx-expr)
       (when (hash-ref item 'as #f)
         (define ae (entity!))
         (give-name! ae (hash-ref item 'as))
         (hash-set! inner-scope (hash-ref item 'as) ae)))
     (for ([stmt (in-list (hash-ref node 'body '()))])
       (define child (parse-expr-node! stmt inner-scope))
       (claim! e (py-has-child-pred) child))
     e]

    [(equal? type "try")
     (define e (entity!))
     (claim! e (py-expr-kind-pred) (value! "try"))
     (for ([stmt (in-list (hash-ref node 'body '()))])
       (define child (parse-expr-node! stmt scope))
       (claim! e (py-has-child-pred) child))
     (for ([handler (in-list (hash-ref node 'handlers '()))])
       (for ([stmt (in-list (hash-ref handler 'body '()))])
         (define child (parse-expr-node! stmt scope))
         (claim! e (py-has-child-pred) child)))
     (for ([stmt (in-list (hash-ref node 'finalbody '()))])
       (define child (parse-expr-node! stmt scope))
       (claim! e (py-has-child-pred) child))
     e]

    [(equal? type "assign")
     (define e (entity!))
     (claim! e (py-expr-kind-pred) (value! "assign"))
     (define val (parse-expr-node! (hash-ref node 'value) scope))
     (claim! e (py-has-child-pred) val)
     (for ([target (in-list (hash-ref node 'targets '()))])
       (when (string? target)
         (define te (entity!))
         (give-name! te target)
         (hash-set! scope target te)))
     e]

    [(equal? type "ann_assign")
     (define e (entity!))
     (claim! e (py-expr-kind-pred) (value! "ann_assign"))
     (when (hash-ref node 'value #f)
       (define val (parse-expr-node! (hash-ref node 'value) scope))
       (claim! e (py-has-child-pred) val))
     e]

    [(equal? type "expr_stmt")
     (parse-expr-node! (hash-ref node 'value) scope)]

    [(equal? type "binop")
     (define e (entity!))
     (claim! e (py-expr-kind-pred) (value! (format "binop:~a" (hash-ref node 'op "?"))))
     (define left (parse-expr-node! (hash-ref node 'left) scope))
     (define right (parse-expr-node! (hash-ref node 'right) scope))
     (claim! e (py-has-child-pred) left)
     (claim! e (py-has-child-pred) right)
     e]

    [(equal? type "compare")
     (define e (entity!))
     (claim! e (py-expr-kind-pred) (value! "compare"))
     (define left (parse-expr-node! (hash-ref node 'left) scope))
     (claim! e (py-has-child-pred) left)
     (for ([comp (in-list (hash-ref node 'comparators '()))])
       (define child (parse-expr-node! comp scope))
       (claim! e (py-has-child-pred) child))
     e]

    [(equal? type "boolop")
     (define e (entity!))
     (claim! e (py-expr-kind-pred) (value! (format "boolop:~a" (hash-ref node 'op "?"))))
     (for ([val (in-list (hash-ref node 'values '()))])
       (define child (parse-expr-node! val scope))
       (claim! e (py-has-child-pred) child))
     e]

    [(equal? type "unaryop")
     (define e (entity!))
     (claim! e (py-expr-kind-pred) (value! "unaryop"))
     (define operand (parse-expr-node! (hash-ref node 'operand) scope))
     (claim! e (py-has-child-pred) operand)
     e]

    [(equal? type "ifexp")
     (define e (entity!))
     (claim! e (py-expr-kind-pred) (value! "ifexp"))
     (define test (parse-expr-node! (hash-ref node 'test) scope))
     (define body (parse-expr-node! (hash-ref node 'body) scope))
     (define orelse (parse-expr-node! (hash-ref node 'orelse) scope))
     (claim! e (py-has-child-pred) test)
     (claim! e (py-has-child-pred) body)
     (claim! e (py-has-child-pred) orelse)
     e]

    [(equal? type "lambda")
     (define e (entity!))
     (claim! e (py-expr-kind-pred) (value! "lambda"))
     (define inner-scope (hash-copy scope))
     (for ([p (in-list (hash-ref node 'params '()))])
       (define pe (entity!))
       (give-name! pe (hash-ref p 'name))
       (claim! e (py-has-param-pred) pe)
       (hash-set! inner-scope (hash-ref p 'name) pe))
     (define body (parse-expr-node! (hash-ref node 'body) inner-scope))
     (claim! e (py-has-child-pred) body)
     e]

    [(member type '("listcomp" "setcomp" "genexp" "dictcomp"))
     (define e (entity!))
     (claim! e (py-expr-kind-pred) (value! type))
     (when (hash-ref node 'elt #f)
       (define elt (parse-expr-node! (hash-ref node 'elt) scope))
       (claim! e (py-has-child-pred) elt))
     (when (hash-ref node 'key #f)
       (define k (parse-expr-node! (hash-ref node 'key) scope))
       (define v (parse-expr-node! (hash-ref node 'value) scope))
       (claim! e (py-has-child-pred) k)
       (claim! e (py-has-child-pred) v))
     (for ([gen (in-list (hash-ref node 'generators '()))])
       (define iter-expr (parse-expr-node! (hash-ref gen 'iter) scope))
       (claim! e (py-has-child-pred) iter-expr))
     e]

    [(member type '("list" "tuple" "set"))
     (define e (entity!))
     (claim! e (py-expr-kind-pred) (value! type))
     (for ([elt (in-list (hash-ref node 'elts '()))])
       (define child (parse-expr-node! elt scope))
       (claim! e (py-has-child-pred) child))
     e]

    [(equal? type "dict")
     (define e (entity!))
     (claim! e (py-expr-kind-pred) (value! "dict"))
     (for ([v (in-list (hash-ref node 'values '()))])
       (define child (parse-expr-node! v scope))
       (claim! e (py-has-child-pred) child))
     e]

    [(equal? type "subscript")
     (define e (entity!))
     (claim! e (py-expr-kind-pred) (value! "subscript"))
     (define val (parse-expr-node! (hash-ref node 'value) scope))
     (define sl (parse-expr-node! (hash-ref node 'slice) scope))
     (claim! e (py-has-child-pred) val)
     (claim! e (py-has-child-pred) sl)
     e]

    [(equal? type "fstring")
     (define e (entity!))
     (claim! e (py-expr-kind-pred) (value! "fstring"))
     (for ([v (in-list (hash-ref node 'values '()))])
       (define child (parse-expr-node! v scope))
       (claim! e (py-has-child-pred) child))
     e]

    [(equal? type "formatted_value")
     (parse-expr-node! (hash-ref node 'value) scope)]

    [(member type '("yield" "yield_from" "starred" "await"))
     (define e (entity!))
     (claim! e (py-expr-kind-pred) (value! type))
     (when (hash-ref node 'value #f)
       (define child (parse-expr-node! (hash-ref node 'value) scope))
       (claim! e (py-has-child-pred) child))
     e]

    [(member type '("pass" "break" "continue"))
     (value! type)]

    [(member type '("raise" "assert" "delete"))
     (define e (entity!))
     (claim! e (py-expr-kind-pred) (value! type))
     (for ([key '(exc test msg)])
       (when (hash-ref node key #f)
         (define child (parse-expr-node! (hash-ref node key) scope))
         (claim! e (py-has-child-pred) child)))
     e]

    [(equal? type "import")
     (define e (entity!))
     (claim! e (py-expr-kind-pred) (value! "import"))
     (for ([name-info (in-list (hash-ref node 'names '()))])
       (define n (hash-ref name-info 'name))
       (claim! e (py-has-child-pred) (value! n)))
     e]

    [(equal? type "match")
     (define e (entity!))
     (claim! e (py-expr-kind-pred) (value! "match"))
     (define subj (parse-expr-node! (hash-ref node 'subject) scope))
     (claim! e (py-has-child-pred) subj)
     (for ([c (in-list (hash-ref node 'cases '()))])
       (for ([stmt (in-list (hash-ref c 'body '()))])
         (define child (parse-expr-node! stmt scope))
         (claim! e (py-has-child-pred) child)))
     e]

    [(or (equal? type "aug_assign") (equal? type "global") (equal? type "nonlocal"))
     (define e (entity!))
     (claim! e (py-expr-kind-pred) (value! type))
     (when (hash-ref node 'value #f)
       (define child (parse-expr-node! (hash-ref node 'value) scope))
       (claim! e (py-has-child-pred) child))
     e]

    [else
     (define src (hash-ref node 'source #f))
     (value! (or src (format "<~a>" type)))]))

;; --- Name resolution ---

(define (resolve-py-name name-str)
  (define vid (value-id name-str))
  (and vid
       (let ([cs (current-claims-where #:p (name-pred) #:r vid)])
         (and (not (null? cs))
              (list-ref (first cs) 2)))))

;; --- Incremental operations ---

(define (py-get-ordered-params fn-id)
  (define param-claims (current-claims-where #:l fn-id #:p (py-has-param-pred)))
  (define params
    (for/list ([c (in-list param-claims)])
      (define pid (list-ref c 3))
      (define pos-claims (current-claims-where #:l pid #:p (py-position-pred)))
      (define pos (if (null? pos-claims) 999
                      (resolve-value (list-ref (first pos-claims) 3))))
      (cons pos pid)))
  (map cdr (sort params < #:key car)))

(define (py-get-body fn-id)
  (define cs (current-claims-where #:l fn-id #:p (py-body-pred)))
  (and (not (null? cs))
       (list-ref (first cs) 3)))

(define (py-collect-children expr-id)
  (cond
    [(value-object? expr-id) '()]
    [else
     (define children
       (append
        (map (lambda (c) (list-ref c 3))
             (current-claims-where #:l expr-id #:p (py-has-child-pred)))
        (let ([bc (current-claims-where #:l expr-id #:p (py-body-pred))])
          (if (null? bc) '() (list (list-ref (first bc) 3))))
        (map (lambda (c) (list-ref c 3))
             (current-claims-where #:l expr-id #:p (py-has-arg-pred)))))
     (cons expr-id (append-map py-collect-children children))]))

(define (py-invalidate-claims! entity-id)
  (define claims (current-claims-where #:l entity-id))
  (for ([c (in-list claims)])
    (invalidate! (first c))))

(define (py-retract-internals! fn-id)
  (define params (py-get-ordered-params fn-id))
  (for ([p (in-list params)])
    (py-invalidate-claims! p))
  (define body-claims (current-claims-where #:l fn-id #:p (py-body-pred)))
  (when (not (null? body-claims))
    (define body-id (list-ref (first body-claims) 3))
    (define entities (py-collect-children body-id))
    (for ([e (in-list entities)])
      (py-invalidate-claims! e)))
  (define param-claims (current-claims-where #:l fn-id #:p (py-has-param-pred)))
  (for ([c (in-list param-claims)]) (invalidate! (first c)))
  (for ([c (in-list body-claims)]) (invalidate! (first c)))
  (define ret-claims (current-claims-where #:l fn-id #:p (py-return-type-pred)))
  (for ([c (in-list ret-claims)]) (invalidate! (first c)))
  (define dec-claims (current-claims-where #:l fn-id #:p (py-has-decorator-pred)))
  (for ([c (in-list dec-claims)]) (invalidate! (first c)))
  (define async-claims (current-claims-where #:l fn-id #:p (py-is-async-pred)))
  (for ([c (in-list async-claims)]) (invalidate! (first c))))

(define (add-python-function! source)
  (define fns (parse-python-program! source))
  (when (null? fns)
    (error 'add-python-function! "no functions parsed"))
  (first fns))

(define (remove-python-function! fn-name)
  (define fn-id (resolve-py-name fn-name))
  (unless fn-id
    (error 'remove-python-function! "unknown function: ~a" fn-name))
  (py-retract-internals! fn-id)
  (py-invalidate-claims! fn-id)
  fn-id)

(define (modify-python-function! fn-name new-source)
  (define fn-id (resolve-py-name fn-name))
  (unless fn-id
    (error 'modify-python-function! "unknown function: ~a" fn-name))
  (py-retract-internals! fn-id)
  (define ast-json (parse-python-source new-source))
  (define body (hash-ref ast-json 'body '()))
  (define node (first (filter (lambda (n) (equal? (hash-ref n 'type #f) "function_def")) body)))
  (define new-name (hash-ref node 'name))
  (unless (equal? new-name fn-name)
    (void (rename! fn-id new-name)))

  (when (hash-ref node 'return_annotation #f)
    (claim! fn-id (py-return-type-pred) (value! (hash-ref node 'return_annotation))))

  (define params (hash-ref node 'params '()))
  (define scope (make-hash))
  (for ([p (in-list params)]
        [i (in-naturals)])
    (define pe (entity!))
    (give-name! pe (hash-ref p 'name))
    (claim! fn-id (py-has-param-pred) pe)
    (claim! pe (py-position-pred) (value! i))
    (when (hash-ref p 'annotation #f)
      (claim! pe (py-has-type-pred) (value! (hash-ref p 'annotation))))
    (hash-set! scope (hash-ref p 'name) pe))

  (define body-wrapper (entity!))
  (claim! body-wrapper (py-expr-kind-pred) (value! "block"))
  (for ([stmt (in-list (hash-ref node 'body '()))]
        [i (in-naturals)])
    (define child (parse-expr-node! stmt scope))
    (claim! body-wrapper (py-has-child-pred) child)
    (claim! child (py-position-pred) (value! i)))
  (claim! fn-id (py-body-pred) body-wrapper)
  fn-id)

;; --- Renderer ---

(define (render-python-program fn-ids)
  (string-join (map render-python-fn fn-ids) "\n\n"))

(define (render-python-fn fn-id)
  (define fk-claims (current-claims-where #:l fn-id #:p (py-form-kind-pred)))
  (define fk (and (not (null? fk-claims))
                  (resolve-value (list-ref (first fk-claims) 3))))
  (cond
    [(equal? fk "class")
     (define name (render-ref fn-id))
     (define base-claims (current-claims-where #:l fn-id #:p (py-has-base-pred)))
     (define bases
       (for/list ([c (in-list base-claims)])
         (resolve-value (list-ref c 3))))
     (define method-claims (current-claims-where #:l fn-id #:p (py-has-method-pred)))
     (define methods
       (for/list ([c (in-list method-claims)])
         (list-ref c 3)))
     (define bases-str (if (null? bases) "" (format "(~a)" (string-join bases ", "))))
     (define method-strs (map (lambda (m) (format "    ~a" (render-python-fn m))) methods))
     (format "class ~a~a:\n~a" name bases-str
             (if (null? method-strs) "    pass"
                 (string-join method-strs "\n\n")))]

    [else
     (define name (render-ref fn-id))
     (define params (py-get-ordered-params fn-id))
     (define param-strs
       (for/list ([p (in-list params)])
         (define pname (render-ref p))
         (define tc (current-claims-where #:l p #:p (py-has-type-pred)))
         (if (null? tc) pname
             (format "~a: ~a" pname (resolve-value (list-ref (first tc) 3))))))
     (define ret-claims (current-claims-where #:l fn-id #:p (py-return-type-pred)))
     (define ret-str
       (if (null? ret-claims) ""
           (format " -> ~a" (resolve-value (list-ref (first ret-claims) 3)))))
     (define dec-claims (current-claims-where #:l fn-id #:p (py-has-decorator-pred)))
     (define dec-strs
       (for/list ([c (in-list dec-claims)])
         (format "@~a" (resolve-value (list-ref c 3)))))
     (define async-claims (current-claims-where #:l fn-id #:p (py-is-async-pred)))
     (define async? (not (null? async-claims)))
     (define body-id (py-get-body fn-id))
     (define body-str (render-python-body body-id 1))
     (string-join
      (append
       dec-strs
       (list (format "~adef ~a(~a)~a:\n~a"
                     (if async? "async " "")
                     name (string-join param-strs ", ") ret-str
                     body-str)))
      "\n")]))

(define (render-python-body body-id indent-level)
  (define indent (make-string (* indent-level 4) #\space))
  (cond
    [(not body-id) (format "~apass" indent)]
    [(value-object? body-id) (format "~a~a" indent (resolve-value body-id))]
    [else
     (define children (py-get-ordered-children body-id))
     (if (null? children)
         (format "~apass" indent)
         (string-join
          (for/list ([c (in-list children)])
            (format "~a~a" indent (render-python-expr c)))
          "\n"))]))

(define (py-get-ordered-children expr-id)
  (define child-claims (current-claims-where #:l expr-id #:p (py-has-child-pred)))
  (define children
    (for/list ([c (in-list child-claims)])
      (define cid (list-ref c 3))
      (define pos-claims (current-claims-where #:l cid #:p (py-position-pred)))
      (define pos (if (null? pos-claims) 999
                      (resolve-value (list-ref (first pos-claims) 3))))
      (cons pos cid)))
  (map cdr (sort children < #:key car)))

(define (render-python-expr expr-id)
  (cond
    [(not expr-id) "None"]
    [(value-object? expr-id)
     (define v (resolve-value expr-id))
     (cond
       [(string? v) (format "~s" v)]
       [(eq? v 'null) "None"]
       [else (format "~a" v)])]
    [else
     (define kind-claims (current-claims-where #:l expr-id #:p (py-expr-kind-pred)))
     (define kind (and (not (null? kind-claims))
                       (resolve-value (list-ref (first kind-claims) 3))))
     (cond
       [(equal? kind "call")
        (define call-claims (current-claims-where #:l expr-id #:p (py-calls-pred)))
        (define fn-ref
          (if (null? call-claims) "?"
              (let ([t (list-ref (first call-claims) 3)])
                (if (value-object? t)
                    (resolve-value t)
                    (render-ref t)))))
        (define arg-claims (current-claims-where #:l expr-id #:p (py-has-arg-pred)))
        (define args
          (for/list ([c (in-list arg-claims)])
            (define aid (list-ref c 3))
            (define pos-claims (current-claims-where #:l aid #:p (py-position-pred)))
            (define pos (if (null? pos-claims) 999
                           (resolve-value (list-ref (first pos-claims) 3))))
            (cons pos aid)))
        (define sorted-args (map cdr (sort args < #:key car)))
        (format "~a(~a)" fn-ref
                (string-join (map render-python-expr sorted-args) ", "))]

       [(equal? kind "return")
        (define children (py-get-ordered-children expr-id))
        (if (null? children) "return"
            (format "return ~a" (render-python-expr (first children))))]

       [(equal? kind "if")
        (define children (py-get-ordered-children expr-id))
        (if (null? children) "if ...:"
            (format "if ~a: ..." (render-python-expr (first children))))]

       [(equal? kind "assign")
        (define children (py-get-ordered-children expr-id))
        (if (null? children) "..."
            (format "... = ~a" (render-python-expr (first children))))]

       [(equal? kind "attribute")
        (define call-claims (current-claims-where #:l expr-id #:p (py-calls-pred)))
        (define attr
          (if (null? call-claims) "?"
              (let ([t (list-ref (first call-claims) 3)])
                (if (value-object? t) (resolve-value t) (render-ref t)))))
        (define children (py-get-ordered-children expr-id))
        (if (null? children)
            (format "?.~a" attr)
            (format "~a.~a" (render-python-expr (first children)) attr))]

       [(and kind (string-prefix? kind "binop:"))
        (define op (substring kind 6))
        (define children (py-get-ordered-children expr-id))
        (if (< (length children) 2)
            (format "(~a)" op)
            (format "(~a ~a ~a)" (render-python-expr (first children))
                    op (render-python-expr (second children))))]

       [(equal? kind "lambda")
        (define ps (py-get-ordered-params expr-id))
        (define children (py-get-ordered-children expr-id))
        (format "lambda ~a: ~a"
                (string-join (map render-ref ps) ", ")
                (if (null? children) "None"
                    (render-python-expr (first children))))]

       [(equal? kind "block")
        (define children (py-get-ordered-children expr-id))
        (string-join (map render-python-expr children) "; ")]

       [(equal? kind "ifexp")
        (define children (py-get-ordered-children expr-id))
        (cond
          [(>= (length children) 3)
           (format "(~a if ~a else ~a)"
                   (render-python-expr (second children))
                   (render-python-expr (first children))
                   (render-python-expr (third children)))]
          [else "... if ... else ..."])]

       [kind
        (define children (py-get-ordered-children expr-id))
        (if (null? children) (format "<~a>" kind)
            (format "~a" (string-join (map render-python-expr children) ", ")))]

       [else (render-ref expr-id)])]))

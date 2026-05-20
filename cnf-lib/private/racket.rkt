#lang racket

;; Minimal Racket bridge. Handles: define, struct, lambda, let/let*,
;; if/cond/when/unless, begin, and/or, function calls. No macros,
;; no module-level require/provide, no syntax objects.

(require "kernel.rkt" "datalog.rkt" "graph.rkt")

(provide setup-racket-lang!
         parse-racket-program! parse-racket-file!
         add-racket-function! remove-racket-function! modify-racket-function!
         render-racket-program render-racket-fn render-racket-expr
         rkt-has-param-pred rkt-position-pred rkt-body-pred rkt-calls-pred
         rkt-has-child-pred rkt-form-kind-pred rkt-expr-kind-pred
         rkt-has-field-pred)

;; --- Predicate accessors ---

(define (rkt-has-param-pred) (ctx-ref 'rkt-has-param-pred))
(define (rkt-position-pred) (ctx-ref 'rkt-position-pred))
(define (rkt-body-pred) (ctx-ref 'rkt-body-pred))
(define (rkt-calls-pred) (ctx-ref 'rkt-calls-pred))
(define (rkt-has-child-pred) (ctx-ref 'rkt-has-child-pred))
(define (rkt-form-kind-pred) (ctx-ref 'rkt-form-kind-pred))
(define (rkt-expr-kind-pred) (ctx-ref 'rkt-expr-kind-pred))
(define (rkt-has-field-pred) (ctx-ref 'rkt-has-field-pred))

;; --- Setup ---

(define (setup-racket-lang!)
  (ctx-set! 'rkt-has-param-pred (named! "rkt-has-param"))
  (ctx-set! 'rkt-position-pred (named! "rkt-position"))
  (ctx-set! 'rkt-body-pred (named! "rkt-body"))
  (ctx-set! 'rkt-calls-pred (named! "rkt-calls"))
  (ctx-set! 'rkt-has-child-pred (named! "rkt-has-child"))
  (ctx-set! 'rkt-form-kind-pred (named! "rkt-form-kind"))
  (ctx-set! 'rkt-expr-kind-pred (named! "rkt-expr-kind"))
  (ctx-set! 'rkt-has-field-pred (named! "rkt-has-field"))

  (define cp (rkt-calls-pred))
  (define chp (rkt-has-child-pred))
  (define bp (rkt-body-pred))
  (define fkp (rkt-form-kind-pred))
  (define fn-val (value! "function"))

  (define-rule (rkt-contains-call (? expr) (? fn))
    (current-triple (? expr) cp (? fn)))
  (define-rule (rkt-contains-call (? expr) (? fn))
    (current-triple (? expr) chp (? child))
    (rkt-contains-call (? child) (? fn)))
  (define-rule (rkt-fn-depends-on (? caller) (? callee))
    (current-triple (? caller) fkp fn-val)
    (current-triple (? caller) bp (? body))
    (rkt-contains-call (? body) (? callee))
    (current-triple (? callee) fkp fn-val))
  (void))

;; --- Parser ---

(define (parse-racket-program! source)
  (define port (open-input-string source))
  (let loop ([forms '()])
    (define form (read port))
    (if (eof-object? form)
        (reverse forms)
        (let ([parsed (parse-top-form! form)])
          (if parsed
              (loop (cons parsed forms))
              (loop forms))))))

(define (parse-racket-file! path)
  (define source (file->string path))
  (define port (open-input-string source))
  ;; skip #lang line if present
  (define first-form (read port))
  (define rest-source
    (if (and (symbol? first-form)
             (regexp-match? #rx"^#" (format "~a" first-form)))
        (port->string port)
        (begin
          (close-input-port port)
          source)))
  (when (input-port? port) (close-input-port port))
  (parse-racket-program! rest-source))

;; --- Top-level dispatch ---

(define (parse-top-form! form)
  (match form
    ;; (define (name params ...) body ...)
    [(list 'define (list-rest (? symbol? name) params) body ...)
     (parse-function-def! name params body)]
    ;; (define name expr)
    [(list 'define (? symbol? name) expr)
     (parse-constant-def! name expr)]
    ;; (struct name (fields ...))
    [(list 'struct (? symbol? name) (list (? symbol? fields) ...) rest ...)
     (parse-struct-def! name fields)]
    [_ #f]))

(define (parse-function-def! name params body)
  (define fn (entity!))
  (give-name! fn (symbol->string name))
  (claim! fn (rkt-form-kind-pred) (value! "function"))

  (define scope (make-hash))
  (define flat-params (flatten-params params))
  (for ([p (in-list flat-params)]
        [i (in-naturals)])
    (define pe (entity!))
    (give-name! pe (symbol->string p))
    (claim! fn (rkt-has-param-pred) pe)
    (claim! pe (rkt-position-pred) (value! i))
    (hash-set! scope p pe))

  (define body-wrapper (entity!))
  (claim! body-wrapper (rkt-expr-kind-pred) (value! "begin"))
  (for ([expr (in-list body)]
        [i (in-naturals)])
    (define child (parse-expr! expr scope))
    (claim! body-wrapper (rkt-has-child-pred) child)
    (claim! child (rkt-position-pred) (value! i)))
  (claim! fn (rkt-body-pred) body-wrapper)
  fn)

(define (flatten-params params)
  (cond
    [(null? params) '()]
    [(symbol? params) (list params)]
    [(pair? params)
     (define head (car params))
     (define rest (cdr params))
     (cond
       [(symbol? head) (cons head (flatten-params rest))]
       ;; keyword arg like [x default]
       [(and (list? head) (symbol? (first head)))
        (cons (first head) (flatten-params rest))]
       [else (flatten-params rest)])]
    [else '()]))

(define (parse-constant-def! name expr)
  (define e (entity!))
  (give-name! e (symbol->string name))
  (claim! e (rkt-form-kind-pred) (value! "constant"))
  (define scope (make-hash))
  (define val (parse-expr! expr scope))
  (claim! e (rkt-body-pred) val)
  e)

(define (parse-struct-def! name fields)
  (define e (entity!))
  (give-name! e (symbol->string name))
  (claim! e (rkt-form-kind-pred) (value! "struct"))
  (for ([f (in-list fields)]
        [i (in-naturals)])
    (define fe (entity!))
    (give-name! fe (symbol->string f))
    (claim! e (rkt-has-field-pred) fe)
    (claim! fe (rkt-position-pred) (value! i)))
  e)

;; --- Expression walker ---

(define (parse-expr! form scope)
  (cond
    [(number? form) (value! form)]
    [(string? form) (value! form)]
    [(boolean? form) (value! form)]
    [(char? form) (value! (string form))]
    [(symbol? form)
     (cond
       [(hash-ref scope form #f) => values]
       [(resolve-rkt-name form) => values]
       [else (value! (symbol->string form))])]
    [(and (pair? form) (list? form))
     (parse-list-expr! form scope)]
    [else (value! (format "~s" form))]))

(define (parse-list-expr! form scope)
  (define head (first form))
  (cond
    ;; (if test then else)
    [(eq? head 'if)
     (define e (entity!))
     (claim! e (rkt-expr-kind-pred) (value! "if"))
     (for ([child-form (in-list (cdr form))]
           [i (in-naturals)])
       (define child (parse-expr! child-form scope))
       (claim! e (rkt-has-child-pred) child)
       (claim! child (rkt-position-pred) (value! i)))
     e]

    ;; (cond [test body ...] ...)
    [(eq? head 'cond)
     (define e (entity!))
     (claim! e (rkt-expr-kind-pred) (value! "cond"))
     (for ([clause (in-list (cdr form))]
           [i (in-naturals)])
       (when (list? clause)
         (for ([expr (in-list clause)])
           (define child (parse-expr! expr scope))
           (claim! e (rkt-has-child-pred) child))))
     e]

    ;; (when test body ...) / (unless test body ...)
    [(or (eq? head 'when) (eq? head 'unless))
     (define e (entity!))
     (claim! e (rkt-expr-kind-pred) (value! (symbol->string head)))
     (for ([child-form (in-list (cdr form))]
           [i (in-naturals)])
       (define child (parse-expr! child-form scope))
       (claim! e (rkt-has-child-pred) child)
       (claim! child (rkt-position-pred) (value! i)))
     e]

    ;; (let ([x e] ...) body ...) / (let* ([x e] ...) body ...)
    [(or (eq? head 'let) (eq? head 'let*))
     (define e (entity!))
     (claim! e (rkt-expr-kind-pred) (value! (symbol->string head)))
     (define bindings (second form))
     (define inner-scope (hash-copy scope))
     (when (list? bindings)
       (for ([b (in-list bindings)])
         (when (and (list? b) (>= (length b) 2) (symbol? (first b)))
           (define val (parse-expr! (second b) (if (eq? head 'let*) inner-scope scope)))
           (claim! e (rkt-has-child-pred) val)
           (define be (entity!))
           (give-name! be (symbol->string (first b)))
           (hash-set! inner-scope (first b) be))))
     (for ([body-form (in-list (cddr form))]
           [i (in-naturals)])
       (define child (parse-expr! body-form inner-scope))
       (claim! e (rkt-has-child-pred) child))
     e]

    ;; (lambda (params ...) body ...)
    [(eq? head 'lambda)
     (define e (entity!))
     (claim! e (rkt-expr-kind-pred) (value! "lambda"))
     (define inner-scope (hash-copy scope))
     (define raw-params (second form))
     (define flat (flatten-params raw-params))
     (for ([p (in-list flat)]
           [i (in-naturals)])
       (define pe (entity!))
       (give-name! pe (symbol->string p))
       (claim! e (rkt-has-param-pred) pe)
       (claim! pe (rkt-position-pred) (value! i))
       (hash-set! inner-scope p pe))
     (for ([body-form (in-list (cddr form))])
       (define child (parse-expr! body-form inner-scope))
       (claim! e (rkt-has-child-pred) child))
     e]

    ;; (begin body ...)
    [(eq? head 'begin)
     (define e (entity!))
     (claim! e (rkt-expr-kind-pred) (value! "begin"))
     (for ([body-form (in-list (cdr form))]
           [i (in-naturals)])
       (define child (parse-expr! body-form scope))
       (claim! e (rkt-has-child-pred) child)
       (claim! child (rkt-position-pred) (value! i)))
     e]

    ;; (and ...) / (or ...)
    [(or (eq? head 'and) (eq? head 'or))
     (define e (entity!))
     (claim! e (rkt-expr-kind-pred) (value! (symbol->string head)))
     (for ([child-form (in-list (cdr form))])
       (define child (parse-expr! child-form scope))
       (claim! e (rkt-has-child-pred) child))
     e]

    ;; (quote x) / 'x
    [(eq? head 'quote)
     (value! (format "'~s" (second form)))]

    ;; (define ...) inside body — local define
    [(eq? head 'define)
     (match form
       [(list 'define (list-rest (? symbol? name) params) body ...)
        (define fn (entity!))
        (give-name! fn (symbol->string name))
        (claim! fn (rkt-form-kind-pred) (value! "function"))
        (define inner-scope (hash-copy scope))
        (hash-set! inner-scope name fn)
        (define flat (flatten-params params))
        (for ([p (in-list flat)]
              [i (in-naturals)])
          (define pe (entity!))
          (give-name! pe (symbol->string p))
          (claim! fn (rkt-has-param-pred) pe)
          (claim! pe (rkt-position-pred) (value! i))
          (hash-set! inner-scope p pe))
        (define body-wrapper (entity!))
        (claim! body-wrapper (rkt-expr-kind-pred) (value! "begin"))
        (for ([b (in-list body)]
              [i (in-naturals)])
          (define child (parse-expr! b inner-scope))
          (claim! body-wrapper (rkt-has-child-pred) child)
          (claim! child (rkt-position-pred) (value! i)))
        (claim! fn (rkt-body-pred) body-wrapper)
        (hash-set! scope name fn)
        fn]
       [(list 'define (? symbol? name) expr)
        (define val (parse-expr! expr scope))
        (define ce (entity!))
        (give-name! ce (symbol->string name))
        (hash-set! scope name ce)
        (claim! ce (rkt-body-pred) val)
        ce]
       [_ (value! (format "~s" form))])]

    ;; function call — (fn arg ...)
    [else
     (define e (entity!))
     (claim! e (rkt-expr-kind-pred) (value! "call"))
     (define fn-ref (parse-expr! head scope))
     (claim! e (rkt-calls-pred) fn-ref)
     (for ([arg (in-list (cdr form))]
           [i (in-naturals)])
       (define child (parse-expr! arg scope))
       (claim! e (rkt-has-child-pred) child)
       (claim! child (rkt-position-pred) (value! i)))
     e]))

;; --- Name resolution ---

(define (resolve-rkt-name name-sym)
  (define name-str (symbol->string name-sym))
  (define vid (value-id name-str))
  (and vid
       (let ([cs (current-claims-where #:p (name-pred) #:r vid)])
         (and (not (null? cs))
              (list-ref (first cs) 2)))))

;; --- Incremental operations ---

(define (rkt-get-ordered-params fn-id)
  (define param-claims (current-claims-where #:l fn-id #:p (rkt-has-param-pred)))
  (define params
    (for/list ([c (in-list param-claims)])
      (define pid (list-ref c 3))
      (define pos-claims (current-claims-where #:l pid #:p (rkt-position-pred)))
      (define pos (if (null? pos-claims) 999
                      (resolve-value (list-ref (first pos-claims) 3))))
      (cons pos pid)))
  (map cdr (sort params < #:key car)))

(define (rkt-get-body fn-id)
  (define cs (current-claims-where #:l fn-id #:p (rkt-body-pred)))
  (and (not (null? cs))
       (list-ref (first cs) 3)))

(define (rkt-collect-children expr-id)
  (cond
    [(value-object? expr-id) '()]
    [else
     (define children
       (append
        (map (lambda (c) (list-ref c 3))
             (current-claims-where #:l expr-id #:p (rkt-has-child-pred)))
        (let ([bc (current-claims-where #:l expr-id #:p (rkt-body-pred))])
          (if (null? bc) '() (list (list-ref (first bc) 3))))
        (map (lambda (c) (list-ref c 3))
             (current-claims-where #:l expr-id #:p (rkt-has-param-pred)))))
     (cons expr-id (append-map rkt-collect-children children))]))

(define (rkt-invalidate-claims! entity-id)
  (define claims (current-claims-where #:l entity-id))
  (for ([c (in-list claims)])
    (invalidate! (first c))))

(define (rkt-retract-internals! fn-id)
  (define params (rkt-get-ordered-params fn-id))
  (for ([p (in-list params)])
    (rkt-invalidate-claims! p))
  (define body-claims (current-claims-where #:l fn-id #:p (rkt-body-pred)))
  (when (not (null? body-claims))
    (define body-id (list-ref (first body-claims) 3))
    (define entities (rkt-collect-children body-id))
    (for ([e (in-list entities)])
      (rkt-invalidate-claims! e)))
  (define param-claims (current-claims-where #:l fn-id #:p (rkt-has-param-pred)))
  (for ([c (in-list param-claims)]) (invalidate! (first c)))
  (for ([c (in-list body-claims)]) (invalidate! (first c)))
  (define field-claims (current-claims-where #:l fn-id #:p (rkt-has-field-pred)))
  (for ([c (in-list field-claims)]) (invalidate! (first c))))

(define (add-racket-function! source)
  (define fns (parse-racket-program! source))
  (when (null? fns)
    (error 'add-racket-function! "no forms parsed"))
  (first fns))

(define (remove-racket-function! fn-name)
  (define fn-id (resolve-rkt-name (string->symbol fn-name)))
  (unless fn-id
    (error 'remove-racket-function! "unknown: ~a" fn-name))
  (rkt-retract-internals! fn-id)
  (rkt-invalidate-claims! fn-id)
  fn-id)

(define (modify-racket-function! fn-name new-source)
  (define fn-id (resolve-rkt-name (string->symbol fn-name)))
  (unless fn-id
    (error 'modify-racket-function! "unknown: ~a" fn-name))
  (rkt-retract-internals! fn-id)
  (define port (open-input-string new-source))
  (define form (read port))
  (match form
    [(list 'define (list-rest (? symbol? name) params) body ...)
     (unless (equal? (symbol->string name) fn-name)
       (rename! fn-id (symbol->string name)))
     (claim! fn-id (rkt-form-kind-pred) (value! "function"))
     (define scope (make-hash))
     (define flat (flatten-params params))
     (for ([p (in-list flat)]
           [i (in-naturals)])
       (define pe (entity!))
       (give-name! pe (symbol->string p))
       (claim! fn-id (rkt-has-param-pred) pe)
       (claim! pe (rkt-position-pred) (value! i))
       (hash-set! scope p pe))
     (define body-wrapper (entity!))
     (claim! body-wrapper (rkt-expr-kind-pred) (value! "begin"))
     (for ([expr (in-list body)]
           [i (in-naturals)])
       (define child (parse-expr! expr scope))
       (claim! body-wrapper (rkt-has-child-pred) child)
       (claim! child (rkt-position-pred) (value! i)))
     (claim! fn-id (rkt-body-pred) body-wrapper)
     fn-id]
    [_ (error 'modify-racket-function! "expected (define (name ...) body ...)")]))

;; --- Renderer ---

(define (render-racket-program fn-ids)
  (string-join (map render-racket-fn fn-ids) "\n\n"))

(define (render-racket-fn fn-id)
  (define fk-claims (current-claims-where #:l fn-id #:p (rkt-form-kind-pred)))
  (define fk (and (not (null? fk-claims))
                  (resolve-value (list-ref (first fk-claims) 3))))
  (cond
    [(equal? fk "struct")
     (define name (render-ref fn-id))
     (define field-claims (current-claims-where #:l fn-id #:p (rkt-has-field-pred)))
     (define fields
       (for/list ([c (in-list field-claims)])
         (define fid (list-ref c 3))
         (define pos-claims (current-claims-where #:l fid #:p (rkt-position-pred)))
         (define pos (if (null? pos-claims) 999
                         (resolve-value (list-ref (first pos-claims) 3))))
         (cons pos fid)))
     (define sorted-fields (map cdr (sort fields < #:key car)))
     (format "(struct ~a (~a))"
             name (string-join (map render-ref sorted-fields) " "))]

    [(equal? fk "constant")
     (define name (render-ref fn-id))
     (define body-id (rkt-get-body fn-id))
     (format "(define ~a ~a)" name (render-racket-expr body-id))]

    [else
     (define name (render-ref fn-id))
     (define params (rkt-get-ordered-params fn-id))
     (define param-strs (map render-ref params))
     (define body-id (rkt-get-body fn-id))
     (define body-str (render-racket-body body-id 1))
     (format "(define (~a~a)\n~a)"
             name
             (if (null? param-strs) ""
                 (format " ~a" (string-join param-strs " ")))
             body-str)]))

(define (render-racket-body body-id indent-level)
  (define indent (make-string (* indent-level 2) #\space))
  (cond
    [(not body-id) (format "~a(void)" indent)]
    [(value-object? body-id) (format "~a~a" indent (render-racket-expr body-id))]
    [else
     (define children (rkt-get-ordered-children body-id))
     (if (null? children)
         (format "~a(void)" indent)
         (string-join
          (for/list ([c (in-list children)])
            (format "~a~a" indent (render-racket-expr c)))
          "\n"))]))

(define (rkt-get-ordered-children expr-id)
  (define child-claims (current-claims-where #:l expr-id #:p (rkt-has-child-pred)))
  (define children
    (for/list ([c (in-list child-claims)])
      (define cid (list-ref c 3))
      (define pos-claims (current-claims-where #:l cid #:p (rkt-position-pred)))
      (define pos (if (null? pos-claims) 999
                      (resolve-value (list-ref (first pos-claims) 3))))
      (cons pos cid)))
  (map cdr (sort children < #:key car)))

(define (render-racket-expr expr-id)
  (cond
    [(not expr-id) "#f"]
    [(value-object? expr-id)
     (define v (resolve-value expr-id))
     (cond
       [(string? v)
        (cond
          [(string-prefix? v "'") v]
          [(regexp-match? #rx"^<" v) v]
          [else (format "~s" v)])]
       [(boolean? v) (if v "#t" "#f")]
       [else (format "~a" v)])]
    [else
     (define kind-claims (current-claims-where #:l expr-id #:p (rkt-expr-kind-pred)))
     (define kind (and (not (null? kind-claims))
                       (resolve-value (list-ref (first kind-claims) 3))))
     (cond
       [(equal? kind "call")
        (define call-claims (current-claims-where #:l expr-id #:p (rkt-calls-pred)))
        (define fn-ref
          (if (null? call-claims) "?"
              (let ([t (list-ref (first call-claims) 3)])
                (if (value-object? t)
                    (resolve-value t)
                    (render-ref t)))))
        (define args (rkt-get-ordered-children expr-id))
        (if (null? args)
            (format "(~a)" fn-ref)
            (format "(~a ~a)" fn-ref
                    (string-join (map render-racket-expr args) " ")))]

       [(equal? kind "if")
        (define children (rkt-get-ordered-children expr-id))
        (case (length children)
          [(3) (format "(if ~a ~a ~a)"
                       (render-racket-expr (first children))
                       (render-racket-expr (second children))
                       (render-racket-expr (third children)))]
          [(2) (format "(if ~a ~a)"
                       (render-racket-expr (first children))
                       (render-racket-expr (second children)))]
          [else "(if ...)"])]

       [(equal? kind "cond")
        (define children (rkt-get-ordered-children expr-id))
        (format "(cond ~a)"
                (string-join (map render-racket-expr children) " "))]

       [(or (equal? kind "when") (equal? kind "unless"))
        (define children (rkt-get-ordered-children expr-id))
        (if (null? children) (format "(~a ...)" kind)
            (format "(~a ~a)" kind
                    (string-join (map render-racket-expr children) " ")))]

       [(or (equal? kind "let") (equal? kind "let*"))
        (define children (rkt-get-ordered-children expr-id))
        (format "(~a (...) ~a)" kind
                (string-join (map render-racket-expr children) " "))]

       [(equal? kind "lambda")
        (define ps (rkt-get-ordered-params expr-id))
        (define children (rkt-get-ordered-children expr-id))
        (format "(lambda (~a) ~a)"
                (string-join (map render-ref ps) " ")
                (string-join (map render-racket-expr children) " "))]

       [(equal? kind "begin")
        (define children (rkt-get-ordered-children expr-id))
        (if (= (length children) 1)
            (render-racket-expr (first children))
            (format "(begin ~a)"
                    (string-join (map render-racket-expr children) " ")))]

       [(or (equal? kind "and") (equal? kind "or"))
        (define children (rkt-get-ordered-children expr-id))
        (format "(~a ~a)" kind
                (string-join (map render-racket-expr children) " "))]

       ;; function form-kind (local define rendered inline)
       [(let ([fk-claims (current-claims-where #:l expr-id #:p (rkt-form-kind-pred))])
          (and (not (null? fk-claims))
               (equal? (resolve-value (list-ref (first fk-claims) 3)) "function")))
        (render-racket-fn expr-id)]

       [kind (format "<~a>" kind)]

       [else (render-ref expr-id)])]))

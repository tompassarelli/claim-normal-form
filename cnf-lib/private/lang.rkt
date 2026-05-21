#lang racket

(require "kernel.rkt" "datalog.rkt" "eval.rkt" "graph.rkt")

(provide setup-lang!
         parse-program!
         add-function!
         remove-function!
         modify-function!
         eval-function!
         collect-expr-entities
         render-program
         render-fn
         render-expr
         get-body
         get-ordered-params
         has-param-pred position-pred body-pred calls-pred)

;; Text ↔ CNF projection.
;;
;; Parse a tiny functional language into graph-eval-compatible claims.
;; Render claims back to text.
;; Rename by claim, edit by supersession — text updates automatically.

;; --- Predicate accessors ---

(define (has-param-pred) (ctx-ref 'has-param))
(define (position-pred) (ctx-ref 'position-pred))
(define (body-pred) (ctx-ref 'body-pred))
(define (calls-pred) (ctx-ref 'calls-pred))

;; --- Setup ---

(define (setup-lang!)
  (ctx-set! 'has-param (named! "has-param"))
  (ctx-set! 'position-pred (named! "position"))
  (ctx-set! 'body-pred (named! "body"))
  (ctx-set! 'calls-pred (named! "calls"))
  (ctx-set! 'builtins (make-hash))
  (for ([pair (list (cons '+ +) (cons '- -) (cons '* *) (cons '/ /) (cons '= =))])
    (define sym (car pair))
    (define proc (cdr pair))
    (define name-str (symbol->string sym))
    (hash-set! (ctx-ref 'builtins) sym name-str)
    (register-primitive! name-str proc))
  (define bp (body-pred))
  (define cp (calls-pred))
  (define lp (left-pred))
  (define rp (right-pred))
  (define fp (fn-pred))
  (define ap (arg-pred))
  (define-rule (contains-call (? expr) (? fn))
    (current-triple (? expr) cp (? fn)))
  (define-rule (contains-call (? expr) (? fn))
    (current-triple (? expr) lp (? child))
    (contains-call (? child) (? fn)))
  (define-rule (contains-call (? expr) (? fn))
    (current-triple (? expr) rp (? child))
    (contains-call (? child) (? fn)))
  (define-rule (contains-call (? expr) (? fn))
    (current-triple (? expr) fp (? child))
    (contains-call (? child) (? fn)))
  (define-rule (contains-call (? expr) (? fn))
    (current-triple (? expr) ap (? child))
    (contains-call (? child) (? fn)))
  (define cdp (cond-pred))
  (define tp (then-pred))
  (define ep (else-pred))
  (define-rule (contains-call (? expr) (? fn))
    (current-triple (? expr) cdp (? child))
    (contains-call (? child) (? fn)))
  (define-rule (contains-call (? expr) (? fn))
    (current-triple (? expr) tp (? child))
    (contains-call (? child) (? fn)))
  (define-rule (contains-call (? expr) (? fn))
    (current-triple (? expr) ep (? child))
    (contains-call (? child) (? fn)))
  (define-rule (fn-depends-on (? caller) (? callee))
    (current-triple (? caller) bp (? body))
    (contains-call (? body) (? callee)))
  (void))

;; --- Parser ---

(define (parse-program! source)
  (define port (open-input-string source))
  (let loop ([fns '()])
    (define form (read port))
    (if (eof-object? form)
        (reverse fns)
        (loop (cons (parse-defn! form) fns)))))

(define (parse-defn! form)
  (match form
    [(list 'defn (? symbol? name) (list (? symbol? params) ...) body)
     (define fn (entity!))
     (give-name! fn (symbol->string name))
     (claim! fn (kind-pred) (value! "binding"))
     (claim! fn (binding-name-pred) (value! (symbol->string name)))
     (define param-bindings
       (for/list ([p (in-list params)]
                  [i (in-naturals)])
         (define param (entity!))
         (give-name! param (symbol->string p))
         (claim! param (kind-pred) (value! "binding"))
         (claim! param (binding-name-pred) (value! (symbol->string p)))
         (claim! fn (has-param-pred) param)
         (claim! param (position-pred) (value! i))
         param))
     (define scope (make-hash))
     (for ([p (in-list params)]
           [e (in-list param-bindings)])
       (hash-set! scope p e))
     (define body-expr (parse-expr! body scope))
     (claim! fn (body-pred) body-expr)
     fn]))

(define (parse-expr! form scope)
  (cond
    [(number? form)
     (lit! form)]
    [(symbol? form)
     (define binding (hash-ref scope form
       (lambda () (error 'parse-expr! "unbound variable: ~a" form))))
     (var! binding)]
    [(list? form)
     (define head (first form))
     (define builtins (ctx-ref 'builtins))
     (cond
       [(eq? head 'if)
        (if! (parse-expr! (second form) scope)
             (parse-expr! (third form) scope)
             (parse-expr! (fourth form) scope))]
       [(hash-has-key? builtins head)
        (binop! (hash-ref builtins head)
                (parse-expr! (second form) scope)
                (parse-expr! (third form) scope))]
       [else
        (define fn-entity (resolve-fn-name head))
        (unless fn-entity
          (error 'parse-expr! "unknown function: ~a" head))
        (define args (rest form))
        (define parsed-args (map (lambda (a) (parse-expr! a scope)) args))
        (define fn-ref (var! fn-entity))
        (define result
          (foldl (lambda (arg acc) (app! acc arg)) fn-ref parsed-args))
        (claim! result (calls-pred) fn-entity)
        result])]))

(define (resolve-fn-name name-sym)
  (define name-str (symbol->string name-sym))
  (define vid (value-id name-str))
  (and vid
       (let ([cs (current-claims-where #:p (name-pred) #:r vid)])
         (for/first ([c cs]
                     #:when (null? (current-claims-where
                                    #:l (list-ref c 2)
                                    #:p (position-pred))))
           (list-ref c 2)))))

;; --- Incremental parse ---

(define (collect-expr-entities expr-id)
  (cond
    [(value-object? expr-id) '()]
    [else
     (define (children-for pred)
       (define cs (current-claims-where #:l expr-id #:p pred))
       (if (null? cs) '()
           (collect-expr-entities (list-ref (first cs) 3))))
     (cons expr-id
           (append (children-for (left-pred))
                   (children-for (right-pred))
                   (children-for (fn-pred))
                   (children-for (arg-pred))
                   (children-for (cond-pred))
                   (children-for (then-pred))
                   (children-for (else-pred))))]))

(define (invalidate-entity-claims! entity-id)
  (define claims (current-claims-where #:l entity-id))
  (for ([c (in-list claims)])
    (invalidate! (first c))))

(define (retract-function-internals! fn-id)
  (define params (get-ordered-params fn-id))
  (for ([p (in-list params)])
    (invalidate-entity-claims! p))
  (define body-claims (current-claims-where #:l fn-id #:p (body-pred)))
  (when (not (null? body-claims))
    (define body-id (list-ref (first body-claims) 3))
    (define expr-entities (collect-expr-entities body-id))
    (for ([e (in-list expr-entities)])
      (invalidate-entity-claims! e)))
  (define param-claims (current-claims-where #:l fn-id #:p (has-param-pred)))
  (for ([c (in-list param-claims)])
    (invalidate! (first c)))
  (for ([c (in-list body-claims)])
    (invalidate! (first c))))

(define (add-function! source)
  (define port (open-input-string source))
  (define form (read port))
  (parse-defn! form))

(define (remove-function! fn-name)
  (define fn-id (resolve-fn-name (string->symbol fn-name)))
  (unless fn-id
    (error 'remove-function! "unknown function: ~a" fn-name))
  (retract-function-internals! fn-id)
  (invalidate-entity-claims! fn-id)
  fn-id)

(define (modify-function! fn-name new-source)
  (define fn-id (resolve-fn-name (string->symbol fn-name)))
  (unless fn-id
    (error 'modify-function! "unknown function: ~a" fn-name))
  (retract-function-internals! fn-id)
  (define port (open-input-string new-source))
  (define form (read port))
  (match form
    [(list 'defn (? symbol? name) (list (? symbol? params) ...) body)
     (unless (equal? (symbol->string name) fn-name)
       (rename! fn-id (symbol->string name)))
     (define param-bindings
       (for/list ([p (in-list params)]
                  [i (in-naturals)])
         (define param (entity!))
         (give-name! param (symbol->string p))
         (claim! param (kind-pred) (value! "binding"))
         (claim! param (binding-name-pred) (value! (symbol->string p)))
         (claim! fn-id (has-param-pred) param)
         (claim! param (position-pred) (value! i))
         param))
     (define scope (make-hash))
     (for ([p (in-list params)]
           [e (in-list param-bindings)])
       (hash-set! scope p e))
     (define body-expr (parse-expr! body scope))
     (claim! fn-id (body-pred) body-expr)
     fn-id]))

;; --- Evaluate ---

(define (eval-function! fn-id arg-values #:fuel [fuel 10000])
  (define all-body-claims (current-claims-where #:p (body-pred)))
  (define all-fn-ids
    (remove-duplicates (map (lambda (c) (list-ref c 2)) all-body-claims)))

  (define ep (ctx-ref 'eval/param))
  (define eb (ctx-ref 'eval/body))
  (define (make-curried-lambda params body-id)
    (foldr (lambda (p inner)
             (define lam (entity!))
             (claim! lam (kind-pred) (value! "lambda"))
             (claim! lam ep p)
             (claim! lam eb inner)
             lam)
           body-id params))

  (define fn-lambdas
    (for/list ([fid (in-list all-fn-ids)])
      (cons fid (make-curried-lambda (get-ordered-params fid) (get-body fid)))))

  (define env-nodes (make-hash))
  (define shared-env
    (for/fold ([env (empty-env)])
              ([pair (in-list fn-lambdas)])
      (define fid (car pair))
      (define new-env (extend-env env fid (lit! 'placeholder)))
      (hash-set! env-nodes fid new-env)
      new-env))

  (for ([pair (in-list fn-lambdas)])
    (define fid (car pair))
    (define lam (cdr pair))
    (define closure (graph-eval lam shared-env #:fuel fuel))
    (claim! (hash-ref env-nodes fid) (env-value-pred) closure))

  (define call-expr
    (foldl (lambda (val acc) (app! acc (lit! val)))
           (var! fn-id)
           arg-values))

  (define run (entity!))
  (claim! run (kind-pred) (value! "eval-run"))
  (claim! run (run-root-pred) fn-id)
  (claim! run (fuel-limit-pred) (value! fuel))

  (define fuel-used-box (box 0))
  (define-values (result status reason error-node)
    (with-handlers
      ([exn:fuel?
        (lambda (e)
          (values (exn:fuel-node-id e) "incomplete" "fuel-exhausted"
                  (exn:fuel-node-id e)))]
       [exn:fail?
        (lambda (e)
          (values #f "error" (exn-message e) #f))])
      (define r (graph-eval call-expr shared-env
                            #:fuel fuel #:fuel-used fuel-used-box))
      (values r "complete" #f #f)))

  (claim! run (run-status-pred) (value! status))
  (claim! run (fuel-used-pred) (value! (unbox fuel-used-box)))
  (when result (claim! run (run-result-pred) result))
  (when reason (claim! run (run-reason-pred) (value! reason)))
  (when error-node (claim! run (run-error-node-pred) error-node))

  run)

;; --- Renderer ---

(define (render-program fn-ids)
  (string-join (map render-fn fn-ids) "\n\n"))

(define (render-fn fn-id)
  (define name (render-ref fn-id))
  (define params (get-ordered-params fn-id))
  (define param-strs (map render-ref params))
  (define body-id (get-body fn-id))
  (format "(defn ~a [~a]\n  ~a)"
          name (string-join param-strs " ") (render-expr body-id)))

(define (get-ordered-params fn-id)
  (define param-claims (current-claims-where #:l fn-id #:p (has-param-pred)))
  (define params
    (for/list ([c (in-list param-claims)])
      (define param-id (list-ref c 3))
      (define pos-claims
        (current-claims-where #:l param-id #:p (position-pred)))
      (define pos (resolve-value (list-ref (first pos-claims) 3)))
      (cons pos param-id)))
  (map cdr (sort params < #:key car)))

(define (get-body fn-id)
  (define cs (current-claims-where #:l fn-id #:p (body-pred)))
  (list-ref (first cs) 3))

(define (collect-app-args expr-id)
  (define k (node-kind expr-id))
  (cond
    [(equal? k "apply")
     (define fn-part (node-ref expr-id (fn-pred)))
     (define arg-part (node-ref expr-id (arg-pred)))
     (define-values (inner-fn inner-args) (collect-app-args fn-part))
     (values inner-fn (append inner-args (list arg-part)))]
    [else
     (values expr-id '())]))

(define (render-expr expr-id)
  (cond
    [(value-object? expr-id)
     (format "~a" (resolve-value expr-id))]
    [else
     (define k (node-kind expr-id))
     (define call-cs (current-claims-where #:l expr-id #:p (calls-pred)))
     (cond
       [(equal? k "literal")
        (format "~a" (node-value expr-id))]
       [(equal? k "var")
        (define binding-id (node-ref expr-id (binding-pred)))
        (render-ref binding-id)]
       [(equal? k "binop")
        (define op-ref (node-ref expr-id (op-pred)))
        (define op-str (or (resolve-value op-ref) (render-ref op-ref)))
        (define left-id (node-ref expr-id (left-pred)))
        (define right-id (node-ref expr-id (right-pred)))
        (format "(~a ~a ~a)" op-str (render-expr left-id) (render-expr right-id))]
       [(equal? k "if")
        (define c (node-ref expr-id (cond-pred)))
        (define t (node-ref expr-id (then-pred)))
        (define e (node-ref expr-id (else-pred)))
        (format "(if ~a ~a ~a)" (render-expr c) (render-expr t) (render-expr e))]
       [(not (null? call-cs))
        (define fn-id (list-ref (first call-cs) 3))
        (define-values (_ args) (collect-app-args expr-id))
        (define arg-strs (map render-expr args))
        (format "(~a ~a)" (render-ref fn-id) (string-join arg-strs " "))]
       [(not (null? (current-claims-where #:l expr-id #:p (op-pred))))
        ;; Legacy binop without kind (backward compat)
        (define op-ref
          (list-ref (first (current-claims-where #:l expr-id #:p (op-pred))) 3))
        (define op-str (or (resolve-value op-ref) (render-ref op-ref)))
        (define left-id
          (list-ref (first (current-claims-where #:l expr-id #:p (left-pred))) 3))
        (define right-id
          (list-ref (first (current-claims-where #:l expr-id #:p (right-pred))) 3))
        (format "(~a ~a ~a)" op-str (render-expr left-id) (render-expr right-id))]
       [else
        (render-ref expr-id)])]))

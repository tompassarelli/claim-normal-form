#lang racket

(require "cnf.rkt" "datalog.rkt" "eval.rkt" "graph.rkt"
         beagle/private/parse
         beagle/private/types)

(provide setup-beagle-lang!
         parse-beagle-program!
         parse-beagle-file!
         add-beagle-function!
         remove-beagle-function!
         modify-beagle-function!
         render-beagle-program
         render-beagle-fn
         render-beagle-expr
         get-body
         get-ordered-params
         has-param-pred position-pred body-pred calls-pred
         has-type-pred return-type-pred expr-kind-pred has-arg-pred
         has-child-pred has-field-pred form-kind-pred is-private-pred
         has-binding-pred binding-value-pred has-condition-pred
         has-then-pred has-else-pred rest-param-pred)

;; Bridge: beagle AST → CNF claim graph.
;;
;; Parses beagle source via beagle's parser, walks AST structs,
;; creates entities and claims. Structural analysis via Datalog.

;; --- Predicate accessors ---

(define (has-param-pred)    (ctx-ref 'has-param))
(define (position-pred)     (ctx-ref 'position-pred))
(define (body-pred)         (ctx-ref 'body-pred))
(define (calls-pred)        (ctx-ref 'calls-pred))
(define (has-type-pred)     (ctx-ref 'has-type-pred))
(define (return-type-pred)  (ctx-ref 'return-type-pred))
(define (expr-kind-pred)    (ctx-ref 'expr-kind-pred))
(define (has-arg-pred)      (ctx-ref 'has-arg-pred))
(define (has-child-pred)    (ctx-ref 'has-child-pred))
(define (has-field-pred)    (ctx-ref 'has-field-pred))
(define (form-kind-pred)    (ctx-ref 'form-kind-pred))
(define (is-private-pred)   (ctx-ref 'is-private-pred))
(define (has-binding-pred)  (ctx-ref 'has-binding-pred))
(define (binding-value-pred)(ctx-ref 'binding-value-pred))
(define (has-condition-pred)(ctx-ref 'has-condition-pred))
(define (has-then-pred)     (ctx-ref 'has-then-pred))
(define (has-else-pred)     (ctx-ref 'has-else-pred))
(define (rest-param-pred)   (ctx-ref 'rest-param-pred))

;; --- Setup ---

(define (setup-beagle-lang!)
  (ctx-set! 'has-param      (named! "has-param"))
  (ctx-set! 'position-pred  (named! "position"))
  (ctx-set! 'body-pred      (named! "body"))
  (ctx-set! 'calls-pred     (named! "calls"))
  (ctx-set! 'has-type-pred  (named! "has-type"))
  (ctx-set! 'return-type-pred (named! "return-type"))
  (ctx-set! 'expr-kind-pred (named! "expr-kind"))
  (ctx-set! 'has-arg-pred   (named! "has-arg"))
  (ctx-set! 'has-child-pred (named! "has-child"))
  (ctx-set! 'has-field-pred (named! "has-field"))
  (ctx-set! 'form-kind-pred (named! "form-kind"))
  (ctx-set! 'is-private-pred (named! "is-private"))
  (ctx-set! 'has-binding-pred (named! "has-binding"))
  (ctx-set! 'binding-value-pred (named! "binding-value"))
  (ctx-set! 'has-condition-pred (named! "has-condition"))
  (ctx-set! 'has-then-pred  (named! "has-then"))
  (ctx-set! 'has-else-pred  (named! "has-else"))
  (ctx-set! 'rest-param-pred (named! "rest-param"))

  ;; Datalog rules: contains-call walks the expression tree via has-child
  (define cp (calls-pred))
  (define chp (has-child-pred))
  (define bp (body-pred))
  (define fkp (form-kind-pred))
  (define defn-val (value! "defn"))
  (define-rule (contains-call (? expr) (? fn))
    (current-triple (? expr) cp (? fn)))
  (define-rule (contains-call (? expr) (? fn))
    (current-triple (? expr) chp (? child))
    (contains-call (? child) (? fn)))
  (define-rule (fn-depends-on (? caller) (? callee))
    (current-triple (? caller) fkp defn-val)
    (current-triple (? caller) bp (? body))
    (contains-call (? body) (? callee))
    (current-triple (? callee) fkp defn-val))
  (void))

;; --- Read beagle source from string ---

(define (read-beagle-string source)
  (define stripped
    (if (regexp-match? #rx"^#lang " source)
        (let ([nl (regexp-match-positions #rx"\n" source)])
          (if nl (substring source (cdar nl)) source))
        source))
  (define port (open-input-string stripped))
  (port-count-lines! port)
  (parameterize ([read-square-bracket-with-tag BRACKET-TAG])
    (let loop ([acc '()])
      (define d (read-syntax 'beagle-source port))
      (if (eof-object? d) (reverse acc) (loop (cons d acc))))))

;; --- Top-level form dispatch ---

(define (parse-beagle-program! source)
  (define stxs (read-beagle-string source))
  (define prog (parse-program stxs))
  (define forms (program-forms prog))
  (for/list ([form (in-list forms)])
    (parse-top-form! form)))

(define (parse-beagle-file! path)
  (parse-beagle-program! (file->string path)))

(define (parse-top-form! form)
  (cond
    [(defn-form? form)   (parse-defn-form! form)]
    [(defn-multi? form)  (parse-defn-multi! form)]
    [(def-form? form)    (parse-def-form! form)]
    [(record-form? form) (parse-record-form! form)]
    [else
     (define e (entity!))
     (define kind-name (symbol->string (object-name form)))
     (define clean-name (regexp-replace #rx"-form$" kind-name ""))
     (claim! e (form-kind-pred) (value! clean-name))
     (when (and (struct? form) (procedure? object-name))
       (cond
         [(call-form? form)
          (define fn-sym (call-form-fn form))
          (give-name! e (format "~a" fn-sym))
          (claim! e (expr-kind-pred) (value! "call"))
          (define fn-ref
            (cond
              [(symbol? fn-sym)
               (define resolved (resolve-fn-name fn-sym))
               (or resolved (value! (symbol->string fn-sym)))]
              [else (value! (format "~a" fn-sym))]))
          (claim! e (calls-pred) fn-ref)
          (for ([arg (in-list (call-form-args form))]
                [i (in-naturals)])
            (define arg-expr (parse-expr! arg (make-hash)))
            (claim! e (has-arg-pred) arg-expr)
            (claim! arg-expr (position-pred) (value! i))
            (claim! e (has-child-pred) arg-expr))]
         [else (void)]))
     e]))

;; --- defn → function entity ---

(define (parse-defn-form! form)
  (define fn (entity!))
  (give-name! fn (symbol->string (defn-form-name form)))
  (claim! fn (form-kind-pred) (value! "defn"))

  (when (defn-form-private? form)
    (claim! fn (is-private-pred) (value! #t)))

  (when (defn-form-return-type form)
    (claim! fn (return-type-pred)
            (value! (type->string (defn-form-return-type form)))))

  (define param-entities (parse-params! fn (defn-form-params form)))
  (when (defn-form-rest-param form)
    (define rp (entity!))
    (give-name! rp (symbol->string (param-name (defn-form-rest-param form))))
    (claim! fn (rest-param-pred) rp)
    (when (param-type (defn-form-rest-param form))
      (claim! rp (has-type-pred)
              (value! (type->string (param-type (defn-form-rest-param form)))))))

  (define scope (build-scope param-entities (defn-form-params form)))
  (define body-expr (parse-body-exprs! (defn-form-body form) scope))
  (claim! fn (body-pred) body-expr)
  fn)

;; --- defn-multi → function entity with first arity ---

(define (parse-defn-multi! form)
  (define fn (entity!))
  (give-name! fn (symbol->string (defn-multi-name form)))
  (claim! fn (form-kind-pred) (value! "defn"))

  (when (defn-multi-private? form)
    (claim! fn (is-private-pred) (value! #t)))

  (define first-arity (car (defn-multi-arities form)))
  (define param-entities (parse-params! fn (arity-clause-params first-arity)))

  (when (arity-clause-return-type first-arity)
    (claim! fn (return-type-pred)
            (value! (type->string (arity-clause-return-type first-arity)))))

  (define scope (build-scope param-entities (arity-clause-params first-arity)))
  (define body-expr (parse-body-exprs! (arity-clause-body first-arity) scope))
  (claim! fn (body-pred) body-expr)

  (claim! fn (value! "arity-count")
          (value! (length (defn-multi-arities form))))
  fn)

;; --- def → binding entity ---

(define (parse-def-form! form)
  (define e (entity!))
  (give-name! e (symbol->string (def-form-name form)))
  (claim! e (form-kind-pred) (value! "def"))
  (when (def-form-type form)
    (claim! e (has-type-pred)
            (value! (type->string (def-form-type form)))))
  (define scope (make-hash))
  (define val-expr (parse-expr! (def-form-value form) scope))
  (claim! e (body-pred) val-expr)
  e)

;; --- defrecord → record entity + fields ---

(define (parse-record-form! form)
  (define e (entity!))
  (give-name! e (symbol->string (record-form-name form)))
  (claim! e (form-kind-pred) (value! "defrecord"))
  (for ([field (in-list (record-form-fields form))]
        [i (in-naturals)])
    (define f (entity!))
    (give-name! f (symbol->string (param-name field)))
    (claim! e (has-field-pred) f)
    (claim! f (position-pred) (value! i))
    (when (param-type field)
      (claim! f (has-type-pred)
              (value! (type->string (param-type field))))))
  e)

;; --- Parameter parsing ---

(define (parse-params! fn params)
  (for/list ([p (in-list params)]
             [i (in-naturals)])
    (define param-entity (entity!))
    (define pname
      (cond
        [(param? p) (param-name p)]
        [(map-destructure? p) (or (map-destructure-as-name p) (gensym "map-destr"))]
        [(seq-destructure? p) (gensym "seq-destr")]
        [else (gensym "param")]))
    (give-name! param-entity (symbol->string pname))
    (claim! fn (has-param-pred) param-entity)
    (claim! param-entity (position-pred) (value! i))
    (when (and (param? p) (param-type p))
      (claim! param-entity (has-type-pred)
              (value! (type->string (param-type p)))))
    param-entity))

(define (build-scope param-entities params)
  (define scope (make-hash))
  (for ([pe (in-list param-entities)]
        [p (in-list params)])
    (when (param? p)
      (hash-set! scope (param-name p) pe)))
  scope)

;; --- Expression walker ---

(define (parse-body-exprs! body-forms scope)
  (cond
    [(not (list? body-forms))
     (parse-expr! body-forms scope)]
    [(= (length body-forms) 1)
     (parse-expr! (car body-forms) scope)]
    [else
     (let ([wrapper (entity!)])
       (claim! wrapper (expr-kind-pred) (value! "do"))
       (for ([f (in-list body-forms)]
             [i (in-naturals)])
         (define child (parse-expr! f scope))
         (claim! wrapper (has-child-pred) child)
         (claim! child (position-pred) (value! i)))
       wrapper)]))

(define (parse-expr! form scope)
  (cond
    ;; Literals
    [(string? form)  (value! form)]
    [(number? form)  (value! form)]
    [(boolean? form) (value! form)]
    [(keyword? form) (value! (format "~a" form))]

    ;; Symbol reference
    [(symbol? form)
     (hash-ref scope form
       (lambda ()
         (define fn-entity (resolve-fn-name form))
         (or fn-entity (value! (symbol->string form)))))]

    ;; Call
    [(call-form? form)
     (define e (entity!))
     (claim! e (expr-kind-pred) (value! "call"))
     (define fn-sym (call-form-fn form))
     (define fn-entity
       (cond
         [(symbol? fn-sym) (resolve-fn-name fn-sym)]
         [else #f]))
     (when fn-entity
       (claim! e (calls-pred) fn-entity))
     (when (and (symbol? fn-sym) (not fn-entity))
       (claim! e (calls-pred) (value! (symbol->string fn-sym))))
     (for ([arg (in-list (call-form-args form))]
           [i (in-naturals)])
       (define arg-expr (parse-expr! arg scope))
       (claim! e (has-arg-pred) arg-expr)
       (claim! arg-expr (position-pred) (value! i))
       (claim! e (has-child-pred) arg-expr))
     e]

    ;; If
    [(if-form? form)
     (define e (entity!))
     (claim! e (expr-kind-pred) (value! "if"))
     (define cond-expr (parse-expr! (if-form-cond-expr form) scope))
     (define then-expr (parse-expr! (if-form-then-expr form) scope))
     (claim! e (has-condition-pred) cond-expr)
     (claim! e (has-then-pred) then-expr)
     (claim! e (has-child-pred) cond-expr)
     (claim! e (has-child-pred) then-expr)
     (when (if-form-else-expr form)
       (define else-expr (parse-expr! (if-form-else-expr form) scope))
       (claim! e (has-else-pred) else-expr)
       (claim! e (has-child-pred) else-expr))
     e]

    ;; Let
    [(let-form? form)
     (define e (entity!))
     (claim! e (expr-kind-pred) (value! "let"))
     (define inner-scope (hash-copy scope))
     (for ([b (in-list (let-form-bindings form))])
       (define val-expr (parse-expr! (let-binding-value b) inner-scope))
       (define binding-entity (entity!))
       (give-name! binding-entity (symbol->string (let-binding-name b)))
       (claim! e (has-binding-pred) binding-entity)
       (claim! binding-entity (binding-value-pred) val-expr)
       (claim! e (has-child-pred) val-expr)
       (hash-set! inner-scope (let-binding-name b) binding-entity))
     (define body-expr (parse-body-exprs! (let-form-body form) inner-scope))
     (claim! e (body-pred) body-expr)
     (claim! e (has-child-pred) body-expr)
     e]

    ;; Do (begin)
    [(do-form? form)
     (define e (entity!))
     (claim! e (expr-kind-pred) (value! "do"))
     (for ([f (in-list (do-form-body form))]
           [i (in-naturals)])
       (define child (parse-expr! f scope))
       (claim! e (has-child-pred) child)
       (claim! child (position-pred) (value! i)))
     e]

    ;; When
    [(when-form? form)
     (define e (entity!))
     (claim! e (expr-kind-pred) (value! "when"))
     (define cond-expr (parse-expr! (when-form-cond-expr form) scope))
     (claim! e (has-condition-pred) cond-expr)
     (claim! e (has-child-pred) cond-expr)
     (define body-expr (parse-body-exprs! (when-form-body form) scope))
     (claim! e (body-pred) body-expr)
     (claim! e (has-child-pred) body-expr)
     e]

    ;; Cond
    [(cond-form? form)
     (define e (entity!))
     (claim! e (expr-kind-pred) (value! "cond"))
     (for ([clause (in-list (cond-form-clauses form))])
       (define test-expr (parse-expr! (cond-clause-test clause) scope))
       (define body-expr (parse-body-exprs! (cond-clause-body clause) scope))
       (claim! e (has-child-pred) test-expr)
       (claim! e (has-child-pred) body-expr))
     e]

    ;; Fn (lambda)
    [(fn-form? form)
     (define e (entity!))
     (claim! e (expr-kind-pred) (value! "fn"))
     (define inner-scope (hash-copy scope))
     (for ([p (in-list (fn-form-params form))])
       (when (param? p)
         (define pe (entity!))
         (give-name! pe (symbol->string (param-name p)))
         (claim! e (has-param-pred) pe)
         (hash-set! inner-scope (param-name p) pe)))
     (define body-expr (parse-body-exprs! (fn-form-body form) inner-scope))
     (claim! e (body-pred) body-expr)
     (claim! e (has-child-pred) body-expr)
     e]

    ;; Match
    [(match-form? form)
     (define e (entity!))
     (claim! e (expr-kind-pred) (value! "match"))
     (define target (parse-expr! (match-form-target form) scope))
     (claim! e (has-child-pred) target)
     (for ([clause (in-list (match-form-clauses form))])
       (define body-expr (parse-body-exprs! (match-clause-body clause) scope))
       (claim! e (has-child-pred) body-expr))
     e]

    ;; Vec literal
    [(vec-form? form)
     (define e (entity!))
     (claim! e (expr-kind-pred) (value! "vec"))
     (for ([item (in-list (vec-form-items form))])
       (define child (parse-expr! item scope))
       (claim! e (has-child-pred) child))
     e]

    ;; Map literal
    [(map-form? form)
     (define e (entity!))
     (claim! e (expr-kind-pred) (value! "map"))
     (for ([pair (in-list (map-form-pairs form))])
       (define k (parse-expr! (car pair) scope))
       (define v (parse-expr! (cdr pair) scope))
       (claim! e (has-child-pred) k)
       (claim! e (has-child-pred) v))
     e]

    ;; Method call (.method target args...)
    [(method-call? form)
     (define e (entity!))
     (claim! e (expr-kind-pred) (value! "method-call"))
     (claim! e (calls-pred) (value! (symbol->string (method-call-method-name form))))
     (define target (parse-expr! (method-call-target form) scope))
     (claim! e (has-child-pred) target)
     (for ([arg (in-list (method-call-args form))])
       (define child (parse-expr! arg scope))
       (claim! e (has-child-pred) child))
     e]

    ;; Keyword access (:field target)
    [(kw-access? form)
     (define e (entity!))
     (claim! e (expr-kind-pred) (value! "kw-access"))
     (claim! e (calls-pred) (value! (format "~a" (kw-access-kw form))))
     (define target (parse-expr! (kw-access-target form) scope))
     (claim! e (has-child-pred) target)
     e]

    ;; For comprehension
    [(for-form? form)
     (define e (entity!))
     (claim! e (expr-kind-pred) (value! "for"))
     (define inner-scope (hash-copy scope))
     (for ([clause (in-list (for-form-clauses form))])
       (when (for-binding? clause)
         (define val-expr (parse-expr! (for-binding-expr clause) inner-scope))
         (claim! e (has-child-pred) val-expr)
         (when (symbol? (for-binding-name clause))
           (define be (entity!))
           (give-name! be (symbol->string (for-binding-name clause)))
           (hash-set! inner-scope (for-binding-name clause) be))))
     (define body-expr (parse-body-exprs! (for-form-body form) inner-scope))
     (claim! e (has-child-pred) body-expr)
     e]

    ;; Loop/recur
    [(loop-form? form)
     (define e (entity!))
     (claim! e (expr-kind-pred) (value! "loop"))
     (define inner-scope (hash-copy scope))
     (for ([b (in-list (loop-form-bindings form))])
       (define val-expr (parse-expr! (let-binding-value b) inner-scope))
       (claim! e (has-child-pred) val-expr)
       (define be (entity!))
       (give-name! be (symbol->string (let-binding-name b)))
       (hash-set! inner-scope (let-binding-name b) be))
     (define body-expr (parse-body-exprs! (loop-form-body form) inner-scope))
     (claim! e (has-child-pred) body-expr)
     e]

    [(recur-form? form)
     (define e (entity!))
     (claim! e (expr-kind-pred) (value! "recur"))
     (for ([arg (in-list (recur-form-args form))])
       (define child (parse-expr! arg scope))
       (claim! e (has-child-pred) child))
     e]

    ;; Try/catch
    [(try-form? form)
     (define e (entity!))
     (claim! e (expr-kind-pred) (value! "try"))
     (for ([f (in-list (try-form-body form))])
       (define child (parse-expr! f scope))
       (claim! e (has-child-pred) child))
     (for ([c (in-list (try-form-catches form))])
       (define body-expr (parse-body-exprs! (catch-clause-body c) scope))
       (claim! e (has-child-pred) body-expr))
     (when (try-form-finally-body form)
       (for ([f (in-list (try-form-finally-body form))])
         (define child (parse-expr! f scope))
         (claim! e (has-child-pred) child)))
     e]

    ;; if-let / when-let / if-some / when-some
    [(if-let-form? form)
     (define e (entity!))
     (claim! e (expr-kind-pred) (value! "if-let"))
     (define val-expr (parse-expr! (if-let-form-expr form) scope))
     (define be (entity!))
     (give-name! be (symbol->string (if-let-form-name form)))
     (claim! be (binding-value-pred) val-expr)
     (claim! e (has-binding-pred) be)
     (define inner-scope (hash-copy scope))
     (hash-set! inner-scope (if-let-form-name form) be)
     (define then-expr (parse-body-exprs! (if-let-form-then-body form) inner-scope))
     (define else-expr (parse-body-exprs! (if-let-form-else-body form) scope))
     (claim! e (has-then-pred) then-expr)
     (claim! e (has-else-pred) else-expr)
     (claim! e (has-child-pred) val-expr)
     (claim! e (has-child-pred) then-expr)
     (claim! e (has-child-pred) else-expr)
     e]

    [(when-let-form? form)
     (define e (entity!))
     (claim! e (expr-kind-pred) (value! "when-let"))
     (define val-expr (parse-expr! (when-let-form-expr form) scope))
     (define be (entity!))
     (give-name! be (symbol->string (when-let-form-name form)))
     (claim! be (binding-value-pred) val-expr)
     (claim! e (has-binding-pred) be)
     (define inner-scope (hash-copy scope))
     (hash-set! inner-scope (when-let-form-name form) be)
     (define body-expr (parse-body-exprs! (when-let-form-body form) inner-scope))
     (claim! e (body-pred) body-expr)
     (claim! e (has-child-pred) val-expr)
     (claim! e (has-child-pred) body-expr)
     e]

    [(if-some-form? form)
     (define e (entity!))
     (claim! e (expr-kind-pred) (value! "if-some"))
     (define val-expr (parse-expr! (if-some-form-expr form) scope))
     (define inner-scope (hash-copy scope))
     (hash-set! inner-scope (if-some-form-name form)
                (let ([be (entity!)]) (give-name! be (symbol->string (if-some-form-name form))) be))
     (define then-expr (parse-body-exprs! (if-some-form-then-body form) inner-scope))
     (define else-expr (parse-body-exprs! (if-some-form-else-body form) scope))
     (claim! e (has-child-pred) val-expr)
     (claim! e (has-child-pred) then-expr)
     (claim! e (has-child-pred) else-expr)
     e]

    [(when-some-form? form)
     (define e (entity!))
     (claim! e (expr-kind-pred) (value! "when-some"))
     (define val-expr (parse-expr! (when-some-form-expr form) scope))
     (define inner-scope (hash-copy scope))
     (hash-set! inner-scope (when-some-form-name form)
                (let ([be (entity!)]) (give-name! be (symbol->string (when-some-form-name form))) be))
     (define body-expr (parse-body-exprs! (when-some-form-body form) inner-scope))
     (claim! e (has-child-pred) val-expr)
     (claim! e (has-child-pred) body-expr)
     e]

    ;; case
    [(case-form? form)
     (define e (entity!))
     (claim! e (expr-kind-pred) (value! "case"))
     (define test-expr (parse-expr! (case-form-test form) scope))
     (claim! e (has-child-pred) test-expr)
     (for ([clause (in-list (case-form-clauses form))])
       (define body-expr (parse-body-exprs! (case-clause-body clause) scope))
       (claim! e (has-child-pred) body-expr))
     (when (case-form-default form)
       (define default-expr (parse-body-exprs! (case-form-default form) scope))
       (claim! e (has-child-pred) default-expr))
     e]

    ;; doseq
    [(doseq-form? form)
     (define e (entity!))
     (claim! e (expr-kind-pred) (value! "doseq"))
     (define inner-scope (hash-copy scope))
     (for ([clause (in-list (doseq-form-clauses form))])
       (when (for-binding? clause)
         (define val-expr (parse-expr! (for-binding-expr clause) inner-scope))
         (claim! e (has-child-pred) val-expr)
         (when (symbol? (for-binding-name clause))
           (define be (entity!))
           (give-name! be (symbol->string (for-binding-name clause)))
           (hash-set! inner-scope (for-binding-name clause) be))))
     (define body-expr (parse-body-exprs! (doseq-form-body form) inner-scope))
     (claim! e (has-child-pred) body-expr)
     e]

    ;; dotimes
    [(dotimes-form? form)
     (define e (entity!))
     (claim! e (expr-kind-pred) (value! "dotimes"))
     (define count-expr (parse-expr! (dotimes-form-count-expr form) scope))
     (claim! e (has-child-pred) count-expr)
     (define inner-scope (hash-copy scope))
     (define be (entity!))
     (give-name! be (symbol->string (dotimes-form-name form)))
     (hash-set! inner-scope (dotimes-form-name form) be)
     (define body-expr (parse-body-exprs! (dotimes-form-body form) inner-scope))
     (claim! e (has-child-pred) body-expr)
     e]

    ;; set!
    [(set!-form? form)
     (define e (entity!))
     (claim! e (expr-kind-pred) (value! "set!"))
     (define val-expr (parse-expr! (set!-form-value form) scope))
     (claim! e (has-child-pred) val-expr)
     e]

    ;; await
    [(await-form? form)
     (define e (entity!))
     (claim! e (expr-kind-pred) (value! "await"))
     (define inner (parse-expr! (await-form-expr form) scope))
     (claim! e (has-child-pred) inner)
     e]

    ;; new
    [(new-form? form)
     (define e (entity!))
     (claim! e (expr-kind-pred) (value! "new"))
     (for ([arg (in-list (new-form-args form))])
       (define child (parse-expr! arg scope))
       (claim! e (has-child-pred) child))
     e]

    ;; with (record update)
    [(with-form? form)
     (define e (entity!))
     (claim! e (expr-kind-pred) (value! "with"))
     (define target (parse-expr! (with-form-target form) scope))
     (claim! e (has-child-pred) target)
     (for ([u (in-list (with-form-updates form))])
       (define val-expr (parse-expr! (with-update-value u) scope))
       (claim! e (has-child-pred) val-expr))
     e]

    ;; condp
    [(condp-form? form)
     (define e (entity!))
     (claim! e (expr-kind-pred) (value! "condp"))
     (define test-expr (parse-expr! (condp-form-test-expr form) scope))
     (claim! e (has-child-pred) test-expr)
     (for ([clause (in-list (condp-form-clauses form))])
       (define body-expr (parse-body-exprs! (cond-clause-body clause) scope))
       (claim! e (has-child-pred) body-expr))
     (when (condp-form-default form)
       (define default-expr (parse-body-exprs! (condp-form-default form) scope))
       (claim! e (has-child-pred) default-expr))
     e]

    ;; letfn
    [(letfn-form? form)
     (define e (entity!))
     (claim! e (expr-kind-pred) (value! "letfn"))
     (define inner-scope (hash-copy scope))
     (for ([f (in-list (letfn-form-fns form))])
       (define fe (entity!))
       (give-name! fe (symbol->string (letfn-fn-name f)))
       (hash-set! inner-scope (letfn-fn-name f) fe))
     (for ([f (in-list (letfn-form-fns form))])
       (define body-expr (parse-body-exprs! (letfn-fn-body f) inner-scope))
       (claim! e (has-child-pred) body-expr))
     (define body-expr (parse-body-exprs! (letfn-form-body form) inner-scope))
     (claim! e (has-child-pred) body-expr)
     e]

    ;; doto
    [(doto-form? form)
     (define e (entity!))
     (claim! e (expr-kind-pred) (value! "doto"))
     (define target (parse-expr! (doto-form-target form) scope))
     (claim! e (has-child-pred) target)
     (for ([f (in-list (doto-form-forms form))])
       (define child (parse-expr! f scope))
       (claim! e (has-child-pred) child))
     e]

    ;; unsafe
    [(unsafe-clj? form) (value! (format "(unsafe ~s)" (unsafe-clj-clj-string form)))]
    [(unsafe-expr? form)
     (define e (entity!))
     (claim! e (expr-kind-pred) (value! "unsafe-expr"))
     (define inner (parse-expr! (unsafe-expr-inner form) scope))
     (claim! e (has-child-pred) inner)
     e]

    ;; dynamic-var
    [(dynamic-var? form) (value! (format "*~a*" (dynamic-var-name form)))]

    ;; set literal
    [(set-form? form)
     (define e (entity!))
     (claim! e (expr-kind-pred) (value! "set"))
     (for ([item (in-list (set-form-items form))])
       (define child (parse-expr! item scope))
       (claim! e (has-child-pred) child))
     e]

    ;; regex
    [(regex-lit? form) (value! (format "#\"%a\"" (regex-lit-pattern form)))]

    ;; with-open
    [(with-open-form? form)
     (define e (entity!))
     (claim! e (expr-kind-pred) (value! "with-open"))
     (for ([b (in-list (with-open-form-bindings form))])
       (define val-expr (parse-expr! (let-binding-value b) scope))
       (claim! e (has-child-pred) val-expr))
     (define body-expr (parse-body-exprs! (with-open-form-body form) scope))
     (claim! e (has-child-pred) body-expr)
     e]

    ;; Quoted data
    [(quoted? form) (value! (format "'~a" (quoted-datum form)))]

    ;; Fallback: store as string value
    [else (value! (format "~s" form))]))

;; --- Function name resolution ---

(define (resolve-fn-name name-sym)
  (define name-str (symbol->string name-sym))
  (define vid (value-id name-str))
  (and vid
       (let ([cs (current-claims-where #:p (name-pred) #:r vid)])
         (and (not (null? cs))
              (list-ref (first cs) 2)))))

;; --- Incremental operations ---

(define (collect-child-entities expr-id)
  (cond
    [(value-object? expr-id) '()]
    [else
     (define children
       (append
        (map (lambda (c) (list-ref c 3))
             (current-claims-where #:l expr-id #:p (has-child-pred)))
        (let ([body-cs (current-claims-where #:l expr-id #:p (body-pred))])
          (if (null? body-cs) '() (list (list-ref (first body-cs) 3))))
        (map (lambda (c) (list-ref c 3))
             (current-claims-where #:l expr-id #:p (has-arg-pred)))
        (map (lambda (c) (list-ref c 3))
             (current-claims-where #:l expr-id #:p (has-binding-pred)))))
     (cons expr-id
           (append-map collect-child-entities children))]))

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
    (define expr-entities (collect-child-entities body-id))
    (for ([e (in-list expr-entities)])
      (invalidate-entity-claims! e)))
  (define param-claims (current-claims-where #:l fn-id #:p (has-param-pred)))
  (for ([c (in-list param-claims)])
    (invalidate! (first c)))
  (for ([c (in-list body-claims)])
    (invalidate! (first c)))
  (define type-claims (current-claims-where #:l fn-id #:p (return-type-pred)))
  (for ([c (in-list type-claims)])
    (invalidate! (first c)))
  (define priv-claims (current-claims-where #:l fn-id #:p (is-private-pred)))
  (for ([c (in-list priv-claims)])
    (invalidate! (first c))))

(define (add-beagle-function! source)
  (define stxs (read-beagle-string source))
  (define prog (parse-program stxs))
  (define forms (program-forms prog))
  (when (null? forms)
    (error 'add-beagle-function! "no forms parsed"))
  (parse-top-form! (car forms)))

(define (remove-beagle-function! fn-name)
  (define fn-id (resolve-fn-name (string->symbol fn-name)))
  (unless fn-id
    (error 'remove-beagle-function! "unknown function: ~a" fn-name))
  (retract-function-internals! fn-id)
  (invalidate-entity-claims! fn-id)
  fn-id)

(define (modify-beagle-function! fn-name new-source)
  (define fn-id (resolve-fn-name (string->symbol fn-name)))
  (unless fn-id
    (error 'modify-beagle-function! "unknown function: ~a" fn-name))
  (retract-function-internals! fn-id)
  (define stxs (read-beagle-string new-source))
  (define prog (parse-program stxs))
  (define forms (program-forms prog))
  (when (null? forms)
    (error 'modify-beagle-function! "no forms parsed"))
  (define new-form (car forms))
  (define new-name
    (cond
      [(defn-form? new-form) (symbol->string (defn-form-name new-form))]
      [(defn-multi? new-form) (symbol->string (defn-multi-name new-form))]
      [else fn-name]))
  (unless (equal? new-name fn-name)
    (rename! fn-id new-name))

  (cond
    [(defn-form? new-form)
     (define param-entities (parse-params! fn-id (defn-form-params new-form)))
     (when (defn-form-return-type new-form)
       (claim! fn-id (return-type-pred)
               (value! (type->string (defn-form-return-type new-form)))))
     (when (defn-form-private? new-form)
       (claim! fn-id (is-private-pred) (value! #t)))
     (define scope (build-scope param-entities (defn-form-params new-form)))
     (define body-expr (parse-body-exprs! (defn-form-body new-form) scope))
     (claim! fn-id (body-pred) body-expr)]
    [else
     (error 'modify-beagle-function! "expected defn form, got: ~a" new-form)])
  fn-id)

;; --- Renderer ---

(define (render-beagle-program fn-ids)
  (string-join (map render-beagle-fn fn-ids) "\n\n"))

(define (render-beagle-fn fn-id)
  (define fk-claims (current-claims-where #:l fn-id #:p (form-kind-pred)))
  (define fk (and (not (null? fk-claims))
                  (resolve-value (list-ref (first fk-claims) 3))))
  (cond
    [(equal? fk "defrecord")
     (define name (render-ref fn-id))
     (define field-claims (current-claims-where #:l fn-id #:p (has-field-pred)))
     (define fields
       (for/list ([c (in-list field-claims)])
         (define fld (list-ref c 3))
         (define pos-claims (current-claims-where #:l fld #:p (position-pred)))
         (define pos (if (null? pos-claims) 999
                        (resolve-value (list-ref (first pos-claims) 3))))
         (cons pos fld)))
     (define sorted (map cdr (sort fields < #:key car)))
     (define field-strs
       (for/list ([f (in-list sorted)])
         (define fname (render-ref f))
         (define tc (current-claims-where #:l f #:p (has-type-pred)))
         (if (null? tc) fname
             (format "(~a : ~a)" fname (resolve-value (list-ref (first tc) 3))))))
     (format "(defrecord ~a [~a])" name (string-join field-strs " "))]

    [(or (equal? fk "defn") (not fk))
     (define name (render-ref fn-id))
     (define params (get-ordered-params fn-id))
     (define param-strs
       (for/list ([p (in-list params)])
         (define pname (render-ref p))
         (define type-claims (current-claims-where #:l p #:p (has-type-pred)))
         (if (null? type-claims)
             pname
             (format "(~a : ~a)" pname (resolve-value (list-ref (first type-claims) 3))))))
     (define ret-claims (current-claims-where #:l fn-id #:p (return-type-pred)))
     (define ret-str
       (if (null? ret-claims) ""
           (format " : ~a" (resolve-value (list-ref (first ret-claims) 3)))))
     (define body-id (get-body fn-id))
     (format "(defn ~a [~a]~a\n  ~a)"
             name (string-join param-strs " ") ret-str
             (render-beagle-expr body-id))]

    [(equal? fk "def")
     (define name (render-ref fn-id))
     (define tc (current-claims-where #:l fn-id #:p (has-type-pred)))
     (define type-str
       (if (null? tc) ""
           (format " ^~a" (resolve-value (list-ref (first tc) 3)))))
     (define bv-claims (current-claims-where #:l fn-id #:p (binding-value-pred)))
     (define val-str
       (if (null? bv-claims) "nil"
           (render-beagle-expr (list-ref (first bv-claims) 3))))
     (format "(def ~a~a ~a)" name type-str val-str)]

    [(equal? fk "call")
     (render-beagle-expr fn-id)]

    [else
     (format "(~a ~a)" fk (render-ref fn-id))]))

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
  (and (not (null? cs))
       (list-ref (first cs) 3)))

(define (render-beagle-expr expr-id)
  (cond
    [(not expr-id) "nil"]
    [(value-object? expr-id)
     (define v (resolve-value expr-id))
     (cond
       [(string? v) (format "~s" v)]
       [else (format "~a" v)])]
    [else
     (define kind-claims (current-claims-where #:l expr-id #:p (expr-kind-pred)))
     (define kind (and (not (null? kind-claims))
                       (resolve-value (list-ref (first kind-claims) 3))))
     (cond
       [(equal? kind "call")
        (define call-claims (current-claims-where #:l expr-id #:p (calls-pred)))
        (define fn-ref
          (if (null? call-claims) "?"
              (let ([target (list-ref (first call-claims) 3)])
                (if (value-object? target)
                    (resolve-value target)
                    (render-ref target)))))
        (define arg-claims (current-claims-where #:l expr-id #:p (has-arg-pred)))
        (define args
          (for/list ([c (in-list arg-claims)])
            (define arg-id (list-ref c 3))
            (define pos-claims (current-claims-where #:l arg-id #:p (position-pred)))
            (define pos (if (null? pos-claims) 999
                           (resolve-value (list-ref (first pos-claims) 3))))
            (cons pos arg-id)))
        (define sorted-args (map cdr (sort args < #:key car)))
        (format "(~a~a)" fn-ref
                (if (null? sorted-args) ""
                    (string-append " " (string-join (map render-beagle-expr sorted-args) " "))))]

       [(equal? kind "if")
        (define cond-c (current-claims-where #:l expr-id #:p (has-condition-pred)))
        (define then-c (current-claims-where #:l expr-id #:p (has-then-pred)))
        (define else-c (current-claims-where #:l expr-id #:p (has-else-pred)))
        (format "(if ~a\n  ~a~a)"
                (render-beagle-expr (and (not (null? cond-c)) (list-ref (first cond-c) 3)))
                (render-beagle-expr (and (not (null? then-c)) (list-ref (first then-c) 3)))
                (if (null? else-c) ""
                    (format "\n  ~a" (render-beagle-expr (list-ref (first else-c) 3)))))]

       [(equal? kind "let")
        (define bind-claims (current-claims-where #:l expr-id #:p (has-binding-pred)))
        (define bindings
          (for/list ([c (in-list bind-claims)])
            (define be (list-ref c 3))
            (define val-claims (current-claims-where #:l be #:p (binding-value-pred)))
            (define val-id (and (not (null? val-claims))
                               (list-ref (first val-claims) 3)))
            (format "~a ~a" (render-ref be) (render-beagle-expr val-id))))
        (define body-id (get-body expr-id))
        (format "(let [~a]\n  ~a)"
                (string-join bindings " ")
                (render-beagle-expr body-id))]

       [(equal? kind "do")
        (define children (get-ordered-children expr-id))
        (format "(do ~a)" (string-join (map render-beagle-expr children) "\n  "))]

       [(equal? kind "fn")
        (define ps (get-ordered-params expr-id))
        (define param-strs (map render-ref ps))
        (define body-id (get-body expr-id))
        (format "(fn [~a] ~a)"
                (string-join param-strs " ")
                (render-beagle-expr body-id))]

       [(equal? kind "when")
        (define cond-c (current-claims-where #:l expr-id #:p (has-condition-pred)))
        (define body-id (get-body expr-id))
        (format "(when ~a\n  ~a)"
                (render-beagle-expr (and (not (null? cond-c)) (list-ref (first cond-c) 3)))
                (render-beagle-expr body-id))]

       [(equal? kind "if-let")
        (define bind-claims (current-claims-where #:l expr-id #:p (has-binding-pred)))
        (define bind-str
          (if (null? bind-claims) "x _"
              (let ([be (list-ref (first bind-claims) 3)])
                (define val-claims (current-claims-where #:l be #:p (binding-value-pred)))
                (format "~a ~a" (render-ref be)
                        (if (null? val-claims) "_"
                            (render-beagle-expr (list-ref (first val-claims) 3)))))))
        (define then-c (current-claims-where #:l expr-id #:p (has-then-pred)))
        (define else-c (current-claims-where #:l expr-id #:p (has-else-pred)))
        (format "(if-let [~a]\n  ~a~a)" bind-str
                (render-beagle-expr (and (not (null? then-c)) (list-ref (first then-c) 3)))
                (if (null? else-c) ""
                    (format "\n  ~a" (render-beagle-expr (list-ref (first else-c) 3)))))]

       [(equal? kind "when-let")
        (define bind-claims (current-claims-where #:l expr-id #:p (has-binding-pred)))
        (define bind-str
          (if (null? bind-claims) "x _"
              (let ([be (list-ref (first bind-claims) 3)])
                (define val-claims (current-claims-where #:l be #:p (binding-value-pred)))
                (format "~a ~a" (render-ref be)
                        (if (null? val-claims) "_"
                            (render-beagle-expr (list-ref (first val-claims) 3)))))))
        (define body-id (get-body expr-id))
        (format "(when-let [~a]\n  ~a)" bind-str (render-beagle-expr body-id))]

       [(equal? kind "match")
        (define children (get-ordered-children expr-id))
        (if (null? children)
            "(match)"
            (format "(match ~a\n  ~a)"
                    (render-beagle-expr (first children))
                    (string-join (map render-beagle-expr (rest children)) "\n  ")))]

       [(equal? kind "cond")
        (define children (get-ordered-children expr-id))
        (format "(cond\n  ~a)"
                (string-join (map render-beagle-expr children) "\n  "))]

       [(equal? kind "vec")
        (define children (get-ordered-children expr-id))
        (format "[~a]" (string-join (map render-beagle-expr children) " "))]

       [(equal? kind "map")
        (define children (get-ordered-children expr-id))
        (format "{~a}" (string-join (map render-beagle-expr children) " "))]

       [(equal? kind "method-call")
        (define call-claims (current-claims-where #:l expr-id #:p (calls-pred)))
        (define method-name
          (if (null? call-claims) ".?"
              (let ([t (list-ref (first call-claims) 3)])
                (if (value-object? t) (format ".~a" (resolve-value t)) ".?"))))
        (define children (get-ordered-children expr-id))
        (if (null? children)
            (format "(~a)" method-name)
            (format "(~a ~a)" method-name
                    (string-join (map render-beagle-expr children) " ")))]

       [(equal? kind "kw-access")
        (define call-claims (current-claims-where #:l expr-id #:p (calls-pred)))
        (define kw
          (if (null? call-claims) ":?"
              (let ([t (list-ref (first call-claims) 3)])
                (if (value-object? t) (resolve-value t) ":?"))))
        (define children (get-ordered-children expr-id))
        (if (null? children)
            (format "(~a)" kw)
            (format "(~a ~a)" kw
                    (string-join (map render-beagle-expr children) " ")))]

       [(equal? kind "for")
        (define children (get-ordered-children expr-id))
        (format "(for ... ~a)" (string-join (map render-beagle-expr children) " "))]

       [(equal? kind "recur")
        (define children (get-ordered-children expr-id))
        (format "(recur ~a)" (string-join (map render-beagle-expr children) " "))]

       [(equal? kind "try")
        (define children (get-ordered-children expr-id))
        (format "(try ~a)" (string-join (map render-beagle-expr children) " "))]

       [(equal? kind "set!")
        (define children (get-ordered-children expr-id))
        (format "(set! ~a)" (string-join (map render-beagle-expr children) " "))]

       [(equal? kind "new")
        (define children (get-ordered-children expr-id))
        (format "(new ~a)" (string-join (map render-beagle-expr children) " "))]

       [(or (equal? kind "if-some") (equal? kind "when-some"))
        (define children (get-ordered-children expr-id))
        (format "(~a ~a)" kind (string-join (map render-beagle-expr children) " "))]

       [kind
        (define children (get-ordered-children expr-id))
        (if (null? children)
            (format "(~a)" kind)
            (format "(~a ~a)" kind (string-join (map render-beagle-expr children) " ")))]

       ;; Fallback: render as name reference
       [else (render-ref expr-id)])]))

(define (get-ordered-children expr-id)
  (define child-claims (current-claims-where #:l expr-id #:p (has-child-pred)))
  (define children
    (for/list ([c (in-list child-claims)])
      (define child-id (list-ref c 3))
      (define pos-claims (current-claims-where #:l child-id #:p (position-pred)))
      (define pos (if (null? pos-claims) 999
                      (resolve-value (list-ref (first pos-claims) 3))))
      (cons pos child-id)))
  (map cdr (sort children < #:key car)))

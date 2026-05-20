#lang racket

(require "cnf.rkt" "datalog.rkt" "eval.rkt" "graph.rkt")

(provide setup-lang!
         parse-program!
         render-program
         render-fn
         render-expr
         get-body
         get-ordered-params
         has-param-pred position-pred body-pred calls-pred)

;; Text ↔ CNF projection.
;;
;; Parse a tiny functional language into claims.
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
  (for ([pair (list (cons '+ +) (cons '- -) (cons '* *) (cons '/ /))])
    (define sym (car pair))
    (define proc (cdr pair))
    (define op (named! (symbol->string sym)))
    (give-name! op (symbol->string sym))
    (hash-set! (ctx-ref 'builtins) sym op)
    (register-primitive! op proc))
  (define bp (body-pred))
  (define cp (calls-pred))
  (define lp (left-pred))
  (define rp (right-pred))
  (define-rule (contains-call (? expr) (? fn))
    (current-triple (? expr) cp (? fn)))
  (define-rule (contains-call (? expr) (? fn))
    (current-triple (? expr) lp (? child))
    (contains-call (? child) (? fn)))
  (define-rule (contains-call (? expr) (? fn))
    (current-triple (? expr) rp (? child))
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
     (define param-entities
       (for/list ([p (in-list params)]
                  [i (in-naturals)])
         (define param (entity!))
         (give-name! param (symbol->string p))
         (claim! fn (has-param-pred) param)
         (claim! param (position-pred) (value! i))
         param))
     (define scope (make-hash))
     (for ([p (in-list params)]
           [e (in-list param-entities)])
       (hash-set! scope p e))
     (define body-expr (parse-expr! body scope))
     (claim! fn (body-pred) body-expr)
     fn]))

(define (parse-expr! form scope)
  (cond
    [(number? form)
     (value! form)]
    [(symbol? form)
     (hash-ref scope form
       (lambda () (error 'parse-expr! "unbound variable: ~a" form)))]
    [(list? form)
     (define head (first form))
     (define builtins (ctx-ref 'builtins))
     (cond
       [(hash-has-key? builtins head)
        (expr! (hash-ref builtins head)
               (parse-expr! (second form) scope)
               (parse-expr! (third form) scope))]
       [else
        (define fn-entity (resolve-fn-name head))
        (unless fn-entity
          (error 'parse-expr! "unknown function: ~a" head))
        (define call (entity!))
        (claim! call (calls-pred) fn-entity)
        (claim! call (left-pred) (parse-expr! (second form) scope))
        (claim! call (right-pred) (parse-expr! (third form) scope))
        call])]))

(define (resolve-fn-name name-sym)
  (define name-str (symbol->string name-sym))
  (define vid (value-id name-str))
  (and vid
       (let ([cs (current-claims-where #:p (name-pred) #:r vid)])
         (and (not (null? cs))
              (list-ref (first cs) 2)))))

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

(define (render-expr expr-id)
  (define op-claims (current-claims-where #:l expr-id #:p (op-pred)))
  (define call-claims (current-claims-where #:l expr-id #:p (calls-pred)))
  (cond
    [(value-object? expr-id)
     (format "~a" (resolve-value expr-id))]
    [(not (null? op-claims))
     (define op-id (list-ref (first op-claims) 3))
     (define left-id
       (list-ref (first (current-claims-where #:l expr-id #:p (left-pred))) 3))
     (define right-id
       (list-ref (first (current-claims-where #:l expr-id #:p (right-pred))) 3))
     (format "(~a ~a ~a)"
             (render-ref op-id) (render-expr left-id) (render-expr right-id))]
    [(not (null? call-claims))
     (define fn-id (list-ref (first call-claims) 3))
     (define left-id
       (list-ref (first (current-claims-where #:l expr-id #:p (left-pred))) 3))
     (define right-id
       (list-ref (first (current-claims-where #:l expr-id #:p (right-pred))) 3))
     (format "(~a ~a ~a)"
             (render-ref fn-id) (render-expr left-id) (render-expr right-id))]
    [else
     (render-ref expr-id)]))

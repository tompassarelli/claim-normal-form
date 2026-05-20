#lang racket

(provide entity!
         value!
         value-id
         value-object?
         claim!
         named!
         claim-v!
         resolve-symbol
         resolve-value
         claims-about
         claims-targeting
         claims-where
         all-objects
         reset-store!
         symbol-predicate-id
         cnf-ctx?
         current-ctx
         make-cnf-ctx
         ctx-ref
         ctx-set!
         superseded?
         object-exists?
         get-claim)

;; --- Context ---

(struct cnf-ctx
  (next-id        ; box(integer)
   objects        ; mutable-hash: id -> #t
   values         ; mutable-hash: id -> literal
   val-intern     ; mutable-hash: literal -> id
   claims         ; mutable-hash: id -> claim-rec
   idx-by-l       ; mutable-hash: l -> (listof cid)
   idx-by-p       ; mutable-hash: p -> (listof cid)
   idx-by-r       ; mutable-hash: r -> (listof cid)
   idx-by-lp      ; mutable-hash: (l . p) -> (listof cid)
   idx-by-pr      ; mutable-hash: (p . r) -> (listof cid)
   symbol-pred-id ; box(string-or-#f)
   ext            ; mutable-hash: symbol -> any (module extensions)
   superseded))   ; mutable-hash: cid -> #t (maintained on claim!)

(define current-ctx (make-parameter #f))

(define (ctx-ref key [default #f])
  (hash-ref (cnf-ctx-ext (current-ctx)) key default))

(define (ctx-set! key val)
  (hash-set! (cnf-ctx-ext (current-ctx)) key val))

;; --- Store ---

(struct claim-rec (l p r) #:transparent)

;; --- ID generation ---

(define (fresh-id!)
  (define b (cnf-ctx-next-id (current-ctx)))
  (define n (add1 (unbox b)))
  (set-box! b n)
  (number->string n))

;; --- Core constructors ---

(define (entity!)
  (define ctx (current-ctx))
  (define id (fresh-id!))
  (hash-set! (cnf-ctx-objects ctx) id #t)
  id)

(define (value! val)
  (define ctx (current-ctx))
  (define vi (cnf-ctx-val-intern ctx))
  (cond
    [(hash-has-key? vi val)
     (hash-ref vi val)]
    [else
     (define id (fresh-id!))
     (hash-set! (cnf-ctx-objects ctx) id #t)
     (hash-set! (cnf-ctx-values ctx) id val)
     (hash-set! vi val id)
     id]))

(define (index-claim! cid l p r)
  (define ctx (current-ctx))
  (hash-update! (cnf-ctx-idx-by-l ctx) l (lambda (old) (cons cid old)) '())
  (hash-update! (cnf-ctx-idx-by-p ctx) p (lambda (old) (cons cid old)) '())
  (hash-update! (cnf-ctx-idx-by-r ctx) r (lambda (old) (cons cid old)) '())
  (hash-update! (cnf-ctx-idx-by-lp ctx) (cons l p) (lambda (old) (cons cid old)) '())
  (hash-update! (cnf-ctx-idx-by-pr ctx) (cons p r) (lambda (old) (cons cid old)) '()))

(define (claim! l p r)
  (define ctx (current-ctx))
  (define id (fresh-id!))
  (hash-set! (cnf-ctx-objects ctx) id #t)
  (hash-set! (cnf-ctx-claims ctx) id (claim-rec l p r))
  (index-claim! id l p r)
  (define sup-pred (ctx-ref 'supersedes-pred-id #f))
  (when (and sup-pred (equal? p sup-pred))
    (hash-set! (cnf-ctx-superseded ctx) r #t)
    (for ([hook (in-list (ctx-ref 'on-supersede-hooks '()))])
      (hook r)))
  (for ([hook (in-list (ctx-ref 'on-claim-hooks '()))])
    (hook id l p r))
  id)

;; --- Bootstrap ---

(define (make-cnf-ctx)
  (define ctx
    (cnf-ctx
     (box 0) (make-hash) (make-hash) (make-hash) (make-hash)
     (make-hash) (make-hash) (make-hash) (make-hash) (make-hash)
     (box #f) (make-hash) (make-hash)))
  (parameterize ([current-ctx ctx])
    (define sym-id (entity!))
    (set-box! (cnf-ctx-symbol-pred-id ctx) sym-id)
    (claim! sym-id sym-id (value! "symbol")))
  ctx)

(define (symbol-predicate-id)
  (unbox (cnf-ctx-symbol-pred-id (current-ctx))))

;; --- Sugar ---

(define (named! sym)
  (define obj (entity!))
  (claim! obj (symbol-predicate-id) (value! sym))
  obj)

(define (claim-v! l p val)
  (define vid (value! val))
  (define cid (claim! l p vid))
  (values cid vid))

(define (value-object? id)
  (hash-has-key? (cnf-ctx-values (current-ctx)) id))

(define (value-id val)
  (hash-ref (cnf-ctx-val-intern (current-ctx)) val #f))

(define (resolve-symbol sym)
  (define ctx (current-ctx))
  (define vid (value-id sym))
  (and vid
       (let ([cids (hash-ref (cnf-ctx-idx-by-pr ctx)
                              (cons (symbol-predicate-id) vid) '())])
         (and (not (null? cids))
              (claim-rec-l (hash-ref (cnf-ctx-claims ctx) (first cids)))))))

(define (resolve-value id)
  (hash-ref (cnf-ctx-values (current-ctx)) id #f))

;; --- Query ---

(define (claims-about id)
  (define ctx (current-ctx))
  (for/list ([cid (in-list (hash-ref (cnf-ctx-idx-by-l ctx) id '()))])
    (define rec (hash-ref (cnf-ctx-claims ctx) cid))
    (list cid (claim-rec-p rec) (claim-rec-r rec))))

(define (claims-targeting id)
  (define ctx (current-ctx))
  (for/list ([cid (in-list (hash-ref (cnf-ctx-idx-by-r ctx) id '()))])
    (define rec (hash-ref (cnf-ctx-claims ctx) cid))
    (list cid (claim-rec-p rec) (claim-rec-l rec))))

(define (claims-where #:l [l #f] #:p [p #f] #:r [r #f])
  (define ctx (current-ctx))
  (cond
    [(not (or l p r))
     (for/list ([(cid rec) (in-hash (cnf-ctx-claims ctx))])
       (list cid (claim-rec-p rec) (claim-rec-l rec) (claim-rec-r rec)))]
    [else
     (define cids
       (cond
         [(and l p) (hash-ref (cnf-ctx-idx-by-lp ctx) (cons l p) '())]
         [(and p r) (hash-ref (cnf-ctx-idx-by-pr ctx) (cons p r) '())]
         [l (hash-ref (cnf-ctx-idx-by-l ctx) l '())]
         [p (hash-ref (cnf-ctx-idx-by-p ctx) p '())]
         [r (hash-ref (cnf-ctx-idx-by-r ctx) r '())]))
     (for*/list ([cid (in-list cids)]
                 [rec (in-value (hash-ref (cnf-ctx-claims ctx) cid))]
                 #:when (or (not l) (equal? (claim-rec-l rec) l))
                 #:when (or (not p) (equal? (claim-rec-p rec) p))
                 #:when (or (not r) (equal? (claim-rec-r rec) r)))
       (list cid (claim-rec-p rec) (claim-rec-l rec) (claim-rec-r rec)))]))

(define (all-objects)
  (hash-keys (cnf-ctx-objects (current-ctx))))

;; --- Supersession + introspection ---

(define (superseded? cid)
  (hash-has-key? (cnf-ctx-superseded (current-ctx)) cid))

(define (object-exists? id)
  (hash-has-key? (cnf-ctx-objects (current-ctx)) id))

(define (get-claim cid)
  (define rec (hash-ref (cnf-ctx-claims (current-ctx)) cid #f))
  (and rec (list (claim-rec-l rec) (claim-rec-p rec) (claim-rec-r rec))))

;; --- Reset ---

(define (reset-store!)
  (current-ctx (make-cnf-ctx)))

;; --- Initialize default context ---

(current-ctx (make-cnf-ctx))

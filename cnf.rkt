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
         symbol-predicate-id)

;; --- Store ---
;; objects(id)            — all addressable identities
;; values(id, literal)    — subset grounded to host literals (interned)
;; claims(id, l, p, r)    — subset asserting a triple

(struct claim-rec (l p r) #:transparent)

(define next-id (make-parameter 0))
(define objects (make-parameter (make-hash)))   ; id -> #t
(define values* (make-parameter (make-hash)))   ; id -> literal
(define val-intern (make-parameter (make-hash))) ; literal -> id
(define claims  (make-parameter (make-hash)))   ; id -> claim-rec

;; --- Indexes ---

(define idx-by-l  (make-parameter (make-hash)))  ; l -> (listof cid)
(define idx-by-p  (make-parameter (make-hash)))  ; p -> (listof cid)
(define idx-by-r  (make-parameter (make-hash)))  ; r -> (listof cid)
(define idx-by-lp (make-parameter (make-hash)))  ; (l . p) -> (listof cid)
(define idx-by-pr (make-parameter (make-hash)))  ; (p . r) -> (listof cid)

(define (index-claim! cid l p r)
  (hash-update! (idx-by-l) l (λ (old) (cons cid old)) '())
  (hash-update! (idx-by-p) p (λ (old) (cons cid old)) '())
  (hash-update! (idx-by-r) r (λ (old) (cons cid old)) '())
  (hash-update! (idx-by-lp) (cons l p) (λ (old) (cons cid old)) '())
  (hash-update! (idx-by-pr) (cons p r) (λ (old) (cons cid old)) '()))

(define symbol-predicate-id (make-parameter #f))

;; --- ID generation ---

(define (fresh-id!)
  (define n (add1 (next-id)))
  (next-id n)
  (number->string n))

;; --- Core constructors ---

(define (entity!)
  (define id (fresh-id!))
  (hash-set! (objects) id #t)
  id)

(define (value! val)
  (cond
    [(hash-has-key? (val-intern) val)
     (hash-ref (val-intern) val)]
    [else
     (define id (fresh-id!))
     (hash-set! (objects) id #t)
     (hash-set! (values*) id val)
     (hash-set! (val-intern) val id)
     id]))

(define (claim! l p r)
  (define id (fresh-id!))
  (hash-set! (objects) id #t)
  (hash-set! (claims) id (claim-rec l p r))
  (index-claim! id l p r)
  id)

;; --- Bootstrap ---

(define (bootstrap!)
  (next-id 0)
  (objects (make-hash))
  (values* (make-hash))
  (val-intern (make-hash))
  (claims  (make-hash))
  (idx-by-l (make-hash))
  (idx-by-p (make-hash))
  (idx-by-r (make-hash))
  (idx-by-lp (make-hash))
  (idx-by-pr (make-hash))
  (define sym-id (entity!))
  (symbol-predicate-id sym-id)
  (claim! sym-id sym-id (value! "symbol"))
  (void))

(bootstrap!)

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
  (hash-has-key? (values*) id))

(define (value-id val)
  (hash-ref (val-intern) val #f))

(define (resolve-symbol sym)
  (define vid (value-id sym))
  (and vid
       (let ([cids (hash-ref (idx-by-pr) (cons (symbol-predicate-id) vid) '())])
         (and (not (null? cids))
              (claim-rec-l (hash-ref (claims) (first cids)))))))

(define (resolve-value id)
  (hash-ref (values*) id #f))

;; --- Query ---

(define (claims-about id)
  (for/list ([cid (in-list (hash-ref (idx-by-l) id '()))])
    (define rec (hash-ref (claims) cid))
    (list cid (claim-rec-p rec) (claim-rec-r rec))))

(define (claims-targeting id)
  (for/list ([cid (in-list (hash-ref (idx-by-r) id '()))])
    (define rec (hash-ref (claims) cid))
    (list cid (claim-rec-p rec) (claim-rec-l rec))))

(define (claims-where #:l [l #f] #:p [p #f] #:r [r #f])
  (cond
    [(not (or l p r))
     (for/list ([(cid rec) (in-hash (claims))])
       (list cid (claim-rec-p rec) (claim-rec-l rec) (claim-rec-r rec)))]
    [else
     (define cids
       (cond
         [(and l p) (hash-ref (idx-by-lp) (cons l p) '())]
         [(and p r) (hash-ref (idx-by-pr) (cons p r) '())]
         [l (hash-ref (idx-by-l) l '())]
         [p (hash-ref (idx-by-p) p '())]
         [r (hash-ref (idx-by-r) r '())]))
     (for*/list ([cid (in-list cids)]
                 [rec (in-value (hash-ref (claims) cid))]
                 #:when (or (not l) (equal? (claim-rec-l rec) l))
                 #:when (or (not p) (equal? (claim-rec-p rec) p))
                 #:when (or (not r) (equal? (claim-rec-r rec) r)))
       (list cid (claim-rec-p rec) (claim-rec-l rec) (claim-rec-r rec)))]))

(define (all-objects)
  (hash-keys (objects)))

;; --- Reset ---

(define (reset-store!)
  (bootstrap!))

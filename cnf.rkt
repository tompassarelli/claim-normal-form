#lang racket

(provide entity!
         value!
         value-id
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
  (define existing (hash-ref (val-intern) val #f))
  (cond
    [existing existing]
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
  id)

;; --- Bootstrap ---

(define (bootstrap!)
  (next-id 0)
  (objects (make-hash))
  (values* (make-hash))
  (val-intern (make-hash))
  (claims  (make-hash))
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

(define (value-id val)
  (hash-ref (val-intern) val #f))

(define (resolve-symbol sym)
  (for/first ([(cid rec) (in-hash (claims))]
              #:when (equal? (claim-rec-p rec) (symbol-predicate-id))
              #:when (equal? (hash-ref (values*) (claim-rec-r rec) #f) sym))
    (claim-rec-l rec)))

(define (resolve-value id)
  (hash-ref (values*) id #f))

;; --- Query ---

(define (claims-about id)
  (for/list ([(cid rec) (in-hash (claims))]
             #:when (equal? (claim-rec-l rec) id))
    (list cid (claim-rec-p rec) (claim-rec-r rec))))

(define (claims-targeting id)
  (for/list ([(cid rec) (in-hash (claims))]
             #:when (equal? (claim-rec-r rec) id))
    (list cid (claim-rec-p rec) (claim-rec-l rec))))

(define (claims-where #:l [l #f] #:p [p #f] #:r [r #f])
  (for/list ([(cid rec) (in-hash (claims))]
             #:when (or (not l) (equal? (claim-rec-l rec) l))
             #:when (or (not p) (equal? (claim-rec-p rec) p))
             #:when (or (not r) (equal? (claim-rec-r rec) r)))
    (list cid (claim-rec-p rec) (claim-rec-l rec) (claim-rec-r rec))))

(define (all-objects)
  (hash-keys (objects)))

;; --- Reset ---

(define (reset-store!)
  (bootstrap!))

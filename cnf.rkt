#lang racket

(provide object!
         value!
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

(struct claim-rec (l p r) #:transparent)

(define next-id (make-parameter 0))
(define objects (make-parameter (make-hash)))   ; id -> value or #f
(define claims  (make-parameter (make-hash)))   ; id -> claim-rec

(define symbol-predicate-id (make-parameter #f))

;; --- ID generation ---

(define (fresh-id!)
  (define n (add1 (next-id)))
  (next-id n)
  (number->string n))

;; --- Core constructors ---

(define (object!)
  (define id (fresh-id!))
  (hash-set! (objects) id #f)
  id)

(define (value! val)
  (define id (fresh-id!))
  (hash-set! (objects) id val)
  id)

(define (claim! l p r)
  (define id (fresh-id!))
  (hash-set! (objects) id #f)
  (hash-set! (claims) id (claim-rec l p r))
  id)

;; --- Bootstrap ---

(define (bootstrap!)
  (next-id 0)
  (objects (make-hash))
  (claims  (make-hash))
  (define sym-id (object!))
  (symbol-predicate-id sym-id)
  ;; self-name: the symbol predicate is named "symbol"
  (claim! sym-id sym-id (value! "symbol"))
  (void))

(bootstrap!)

;; --- Sugar ---

(define (named! sym)
  (define obj (object!))
  (claim! obj (symbol-predicate-id) (value! sym))
  obj)

(define (claim-v! l p val)
  (define vid (value! val))
  (define cid (claim! l p vid))
  (values cid vid))

(define (resolve-symbol sym)
  (for/first ([(cid rec) (in-hash (claims))]
              #:when (equal? (claim-rec-p rec) (symbol-predicate-id))
              #:when (equal? (hash-ref (objects) (claim-rec-r rec) #f) sym))
    (claim-rec-l rec)))

(define (resolve-value id)
  (hash-ref (objects) id #f))

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

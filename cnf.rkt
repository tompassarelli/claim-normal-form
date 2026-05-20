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
         make-blank-ctx
         export-store
         import-store!
         ctx-ref
         ctx-set!
         superseded?
         object-exists?
         get-claim
         ;; Transactions
         begin-tx!
         commit-tx!
         rollback-tx!
         call-with-transaction
         claim-tx
         tx-claims
         tx-seq
         all-txs
         claims-since
         current-tx-seq
         tx-agent
         claims-visible-as-of
         snapshot-ctx)

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
  ;; Tx association
  (define c2tx (ctx-ref 'claim-to-tx #f))
  (when c2tx
    (define current-tx-box (ctx-ref 'current-tx))
    (define tx (if (unbox current-tx-box)
                   (unbox current-tx-box)
                   (make-tx-entity!)))
    (hash-set! c2tx id tx)
    (hash-update! (ctx-ref 'tx-to-claims) tx (lambda (old) (cons id old)) '()))
  ;; Hooks (deferred during explicit tx)
  (define suppress? (ctx-ref 'tx-suppress-hooks? #f))
  (define sup-pred (ctx-ref 'supersedes-pred-id #f))
  (when (and sup-pred (equal? p sup-pred))
    (hash-set! (cnf-ctx-superseded ctx) r #t)
    (if suppress?
        (ctx-set! 'tx-pending-hooks
          (cons (list 'supersede r) (ctx-ref 'tx-pending-hooks '())))
        (for ([hook (in-list (ctx-ref 'on-supersede-hooks '()))])
          (hook r))))
  (if suppress?
      (ctx-set! 'tx-pending-hooks
        (cons (list 'claim id l p r) (ctx-ref 'tx-pending-hooks '())))
      (for ([hook (in-list (ctx-ref 'on-claim-hooks '()))])
        (hook id l p r)))
  id)

;; --- Bootstrap ---

(define (make-cnf-ctx)
  (define ctx
    (cnf-ctx
     (box 0) (make-hash) (make-hash) (make-hash) (make-hash)
     (make-hash) (make-hash) (make-hash) (make-hash) (make-hash)
     (box #f) (make-hash) (make-hash)))
  (parameterize ([current-ctx ctx])
    (init-tx-state!)
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

;; --- Transactions ---

(define (init-tx-state!)
  (ctx-set! 'tx-counter (box 0))
  (ctx-set! 'current-tx (box #f))
  (ctx-set! 'claim-to-tx (make-hash))
  (ctx-set! 'tx-to-claims (make-hash))
  (ctx-set! 'tx-meta (make-hash)))

(define (make-tx-entity! #:agent [agent #f])
  (define tx-id (fresh-id!))
  (define counter (ctx-ref 'tx-counter))
  (define seq (add1 (unbox counter)))
  (set-box! counter seq)
  (define effective-agent (or agent (ctx-ref 'current-agent #f)))
  (define meta (if effective-agent
                   (hasheq 'seq seq 'agent effective-agent)
                   (hasheq 'seq seq)))
  (hash-set! (ctx-ref 'tx-meta) tx-id meta)
  tx-id)

(define (restore-hash! target source)
  (hash-clear! target)
  (for ([(k v) (in-hash source)]) (hash-set! target k v)))

(define (make-rollback-snapshot)
  (define ctx (current-ctx))
  (hasheq
   'next-id (unbox (cnf-ctx-next-id ctx))
   'objects (hash-copy (cnf-ctx-objects ctx))
   'values (hash-copy (cnf-ctx-values ctx))
   'val-intern (hash-copy (cnf-ctx-val-intern ctx))
   'claims (hash-copy (cnf-ctx-claims ctx))
   'idx-by-l (hash-copy (cnf-ctx-idx-by-l ctx))
   'idx-by-p (hash-copy (cnf-ctx-idx-by-p ctx))
   'idx-by-r (hash-copy (cnf-ctx-idx-by-r ctx))
   'idx-by-lp (hash-copy (cnf-ctx-idx-by-lp ctx))
   'idx-by-pr (hash-copy (cnf-ctx-idx-by-pr ctx))
   'superseded (hash-copy (cnf-ctx-superseded ctx))
   'claim-to-tx (hash-copy (ctx-ref 'claim-to-tx))
   'tx-to-claims (hash-copy (ctx-ref 'tx-to-claims))
   'tx-meta (hash-copy (ctx-ref 'tx-meta))
   'tx-counter (unbox (ctx-ref 'tx-counter))))

(define (restore-from-snapshot! snap)
  (define ctx (current-ctx))
  (set-box! (cnf-ctx-next-id ctx) (hash-ref snap 'next-id))
  (restore-hash! (cnf-ctx-objects ctx) (hash-ref snap 'objects))
  (restore-hash! (cnf-ctx-values ctx) (hash-ref snap 'values))
  (restore-hash! (cnf-ctx-val-intern ctx) (hash-ref snap 'val-intern))
  (restore-hash! (cnf-ctx-claims ctx) (hash-ref snap 'claims))
  (restore-hash! (cnf-ctx-idx-by-l ctx) (hash-ref snap 'idx-by-l))
  (restore-hash! (cnf-ctx-idx-by-p ctx) (hash-ref snap 'idx-by-p))
  (restore-hash! (cnf-ctx-idx-by-r ctx) (hash-ref snap 'idx-by-r))
  (restore-hash! (cnf-ctx-idx-by-lp ctx) (hash-ref snap 'idx-by-lp))
  (restore-hash! (cnf-ctx-idx-by-pr ctx) (hash-ref snap 'idx-by-pr))
  (restore-hash! (cnf-ctx-superseded ctx) (hash-ref snap 'superseded))
  (restore-hash! (ctx-ref 'claim-to-tx) (hash-ref snap 'claim-to-tx))
  (restore-hash! (ctx-ref 'tx-to-claims) (hash-ref snap 'tx-to-claims))
  (restore-hash! (ctx-ref 'tx-meta) (hash-ref snap 'tx-meta))
  (set-box! (ctx-ref 'tx-counter) (hash-ref snap 'tx-counter)))

(define (begin-tx! #:agent [agent #f])
  (define current (ctx-ref 'current-tx))
  (when (unbox current)
    (error 'begin-tx! "nested transactions not supported"))
  (ctx-set! 'tx-snapshot (make-rollback-snapshot))
  (define tx-id (make-tx-entity! #:agent agent))
  (set-box! current tx-id)
  (ctx-set! 'tx-pending-hooks '())
  (ctx-set! 'tx-suppress-hooks? #t)
  tx-id)

(define (commit-tx!)
  (define current (ctx-ref 'current-tx))
  (define tx-id (unbox current))
  (unless tx-id (error 'commit-tx! "no active transaction"))
  (set-box! current #f)
  (ctx-set! 'tx-suppress-hooks? #f)
  (define pending (reverse (ctx-ref 'tx-pending-hooks '())))
  (ctx-set! 'tx-pending-hooks '())
  (ctx-set! 'tx-snapshot #f)
  (for ([entry (in-list pending)])
    (case (first entry)
      [(claim)
       (for ([hook (in-list (ctx-ref 'on-claim-hooks '()))])
         (hook (second entry) (third entry) (fourth entry) (fifth entry)))]
      [(supersede)
       (for ([hook (in-list (ctx-ref 'on-supersede-hooks '()))])
         (hook (second entry)))]))
  tx-id)

(define (rollback-tx!)
  (unless (unbox (ctx-ref 'current-tx))
    (error 'rollback-tx! "no active transaction"))
  (define snap (ctx-ref 'tx-snapshot))
  (unless snap (error 'rollback-tx! "no snapshot"))
  (restore-from-snapshot! snap)
  (set-box! (ctx-ref 'current-tx) #f)
  (ctx-set! 'tx-suppress-hooks? #f)
  (ctx-set! 'tx-pending-hooks '())
  (ctx-set! 'tx-snapshot #f))

(define (call-with-transaction thunk #:agent [agent #f])
  (begin-tx! #:agent agent)
  (with-handlers ([exn:fail? (lambda (e)
                    (rollback-tx!)
                    (raise e))])
    (define result (thunk))
    (commit-tx!)
    result))

;; --- Tx queries ---

(define (claim-tx cid)
  (define c2tx (ctx-ref 'claim-to-tx #f))
  (and c2tx (hash-ref c2tx cid #f)))

(define (tx-claims tx-id)
  (define t2c (ctx-ref 'tx-to-claims #f))
  (if t2c (hash-ref t2c tx-id '()) '()))

(define (tx-seq tx-id)
  (define meta-h (ctx-ref 'tx-meta #f))
  (and meta-h
       (let ([meta (hash-ref meta-h tx-id #f)])
         (and meta (hash-ref meta 'seq #f)))))

(define (all-txs)
  (define meta-h (ctx-ref 'tx-meta #f))
  (if meta-h
      (sort (hash-keys meta-h) <
            #:key (lambda (tx) (hash-ref (hash-ref meta-h tx) 'seq)))
      '()))

(define (claims-since tx-seq-num)
  (define meta-h (ctx-ref 'tx-meta #f))
  (define t2c (ctx-ref 'tx-to-claims #f))
  (if (and meta-h t2c)
      (for*/list ([(tx meta) (in-hash meta-h)]
                  #:when (> (hash-ref meta 'seq) tx-seq-num)
                  [cid (in-list (hash-ref t2c tx '()))])
        cid)
      '()))

(define (current-tx-seq)
  (define counter (ctx-ref 'tx-counter #f))
  (if counter (unbox counter) 0))

(define (tx-agent tx-id)
  (define meta-h (ctx-ref 'tx-meta #f))
  (and meta-h
       (let ([meta (hash-ref meta-h tx-id #f)])
         (and meta (hash-ref meta 'agent #f)))))

(define (claims-visible-as-of tx-seq-num #:l [l #f] #:p [p #f] #:r [r #f])
  (define ctx (current-ctx))
  (define c2tx (ctx-ref 'claim-to-tx #f))
  (define meta-h (ctx-ref 'tx-meta #f))
  (unless (and c2tx meta-h)
    (error 'claims-visible-as-of "tx state not initialized"))
  (define sup-pred (ctx-ref 'supersedes-pred-id #f))
  (define (claim-in-range? cid)
    (define tx (hash-ref c2tx cid #f))
    (and tx
         (let ([meta (hash-ref meta-h tx #f)])
           (and meta (<= (hash-ref meta 'seq) tx-seq-num)))))
  (define superseded-as-of (make-hash))
  (when sup-pred
    (for ([(cid rec) (in-hash (cnf-ctx-claims ctx))]
          #:when (and (equal? (claim-rec-p rec) sup-pred)
                      (claim-in-range? cid)))
      (hash-set! superseded-as-of (claim-rec-r rec) #t)))
  (define candidates (claims-where #:l l #:p p #:r r))
  (filter (lambda (c)
            (define cid (first c))
            (and (claim-in-range? cid)
                 (not (hash-has-key? superseded-as-of cid))))
          candidates))

;; --- Reset ---

(define (reset-store!)
  (current-ctx (make-cnf-ctx)))

;; --- Serialization ---

(define (make-blank-ctx)
  (cnf-ctx
   (box 0) (make-hash) (make-hash) (make-hash) (make-hash)
   (make-hash) (make-hash) (make-hash) (make-hash) (make-hash)
   (box #f) (make-hash) (make-hash)))

(define (snapshot-ctx)
  (define ctx (current-ctx))
  (define new-ext (hash-copy (cnf-ctx-ext ctx)))
  (for ([key '(matview-db matview-prov matview-claim-rev matview-ent-to-resolved
               claim-to-tx tx-to-claims tx-meta builtins primitives rule-entities)])
    (define val (hash-ref new-ext key #f))
    (when (and val (hash? val) (not (immutable? val)))
      (hash-set! new-ext key (hash-copy val))))
  (for ([key '(tx-counter current-tx)])
    (define val (hash-ref new-ext key #f))
    (when (and val (box? val))
      (hash-set! new-ext key (box (unbox val)))))
  (cnf-ctx
   (box (unbox (cnf-ctx-next-id ctx)))
   (hash-copy (cnf-ctx-objects ctx))
   (hash-copy (cnf-ctx-values ctx))
   (hash-copy (cnf-ctx-val-intern ctx))
   (hash-copy (cnf-ctx-claims ctx))
   (hash-copy (cnf-ctx-idx-by-l ctx))
   (hash-copy (cnf-ctx-idx-by-p ctx))
   (hash-copy (cnf-ctx-idx-by-r ctx))
   (hash-copy (cnf-ctx-idx-by-lp ctx))
   (hash-copy (cnf-ctx-idx-by-pr ctx))
   (box (unbox (cnf-ctx-symbol-pred-id ctx)))
   new-ext
   (hash-copy (cnf-ctx-superseded ctx))))

(define (export-store)
  (define ctx (current-ctx))
  (define c2tx (ctx-ref 'claim-to-tx #f))
  (define meta-h (ctx-ref 'tx-meta #f))
  (define counter (ctx-ref 'tx-counter #f))
  (hasheq
   'version 2
   'next-id (unbox (cnf-ctx-next-id ctx))
   'objects (hash-keys (cnf-ctx-objects ctx))
   'values (for/list ([(id lit) (in-hash (cnf-ctx-values ctx))])
             (list id lit))
   'claims (for/list ([(cid rec) (in-hash (cnf-ctx-claims ctx))])
             (list cid (claim-rec-l rec) (claim-rec-p rec) (claim-rec-r rec)))
   'superseded (hash-keys (cnf-ctx-superseded ctx))
   'tx-counter (if counter (unbox counter) 0)
   'claim-txs (if c2tx
                  (for/list ([(cid tx) (in-hash c2tx)])
                    (list cid tx))
                  '())
   'tx-meta (if meta-h
                (for/list ([(tx meta) (in-hash meta-h)])
                  (define agent (hash-ref meta 'agent #f))
                  (if agent
                      (list tx (hash-ref meta 'seq) agent)
                      (list tx (hash-ref meta 'seq))))
                '())))

(define (import-store! data)
  (define ctx (current-ctx))
  (init-tx-state!)
  (for ([id (in-list (hash-ref data 'objects))])
    (hash-set! (cnf-ctx-objects ctx) id #t))
  (for ([v (in-list (hash-ref data 'values))])
    (hash-set! (cnf-ctx-values ctx) (first v) (second v))
    (hash-set! (cnf-ctx-val-intern ctx) (second v) (first v)))
  (for ([c (in-list (hash-ref data 'claims))])
    (define cid (first c))
    (hash-set! (cnf-ctx-claims ctx) cid (claim-rec (second c) (third c) (fourth c)))
    (index-claim! cid (second c) (third c) (fourth c)))
  (for ([s (in-list (hash-ref data 'superseded))])
    (hash-set! (cnf-ctx-superseded ctx) s #t))
  (set-box! (cnf-ctx-next-id ctx) (hash-ref data 'next-id))
  (set-box! (cnf-ctx-symbol-pred-id ctx) "1")
  ;; Import tx data
  (define version (hash-ref data 'version 1))
  (cond
    [(>= version 2)
     (set-box! (ctx-ref 'tx-counter) (hash-ref data 'tx-counter 0))
     (define c2tx (ctx-ref 'claim-to-tx))
     (define t2c (ctx-ref 'tx-to-claims))
     (define meta-h (ctx-ref 'tx-meta))
     (for ([pair (in-list (hash-ref data 'claim-txs '()))])
       (hash-set! c2tx (first pair) (second pair))
       (hash-update! t2c (second pair) (lambda (old) (cons (first pair) old)) '()))
     (for ([entry (in-list (hash-ref data 'tx-meta '()))])
       (define agent (and (>= (length entry) 3) (third entry)))
       (hash-set! meta-h (first entry)
                  (if agent
                      (hasheq 'seq (second entry) 'agent agent)
                      (hasheq 'seq (second entry)))))]
    [else
     (define claim-list (hash-ref data 'claims '()))
     (unless (null? claim-list)
       (define tx-id (fresh-id!))
       (set-box! (ctx-ref 'tx-counter) 1)
       (define c2tx (ctx-ref 'claim-to-tx))
       (define t2c (ctx-ref 'tx-to-claims))
       (hash-set! (ctx-ref 'tx-meta) tx-id (hasheq 'seq 1))
       (for ([c (in-list claim-list)])
         (hash-set! c2tx (first c) tx-id)
         (hash-update! t2c tx-id (lambda (old) (cons (first c) old)) '())))]))

;; --- Initialize default context ---

(current-ctx (make-cnf-ctx))

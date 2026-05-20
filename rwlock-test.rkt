#lang racket

(require rackunit)

;; Inline the rwlock implementation for testing
(struct rwlock (turnstile resource rmutex readers))

(define (make-rwlock)
  (rwlock (make-semaphore 1) (make-semaphore 1) (make-semaphore 1) (box 0)))

(define (call-with-read-lock rwl thunk)
  (semaphore-wait (rwlock-turnstile rwl))
  (semaphore-post (rwlock-turnstile rwl))
  (semaphore-wait (rwlock-rmutex rwl))
  (define count (add1 (unbox (rwlock-readers rwl))))
  (set-box! (rwlock-readers rwl) count)
  (when (= count 1)
    (semaphore-wait (rwlock-resource rwl)))
  (semaphore-post (rwlock-rmutex rwl))
  (with-handlers ([exn? (lambda (e) (rwlock-read-release! rwl) (raise e))])
    (define result (thunk))
    (rwlock-read-release! rwl)
    result))

(define (rwlock-read-release! rwl)
  (semaphore-wait (rwlock-rmutex rwl))
  (define count (sub1 (unbox (rwlock-readers rwl))))
  (set-box! (rwlock-readers rwl) count)
  (when (= count 0)
    (semaphore-post (rwlock-resource rwl)))
  (semaphore-post (rwlock-rmutex rwl)))

(define (call-with-write-lock rwl thunk)
  (semaphore-wait (rwlock-turnstile rwl))
  (semaphore-wait (rwlock-resource rwl))
  (with-handlers ([exn? (lambda (e)
                   (semaphore-post (rwlock-resource rwl))
                   (semaphore-post (rwlock-turnstile rwl))
                   (raise e))])
    (define result (thunk))
    (semaphore-post (rwlock-resource rwl))
    (semaphore-post (rwlock-turnstile rwl))
    result))

;; 1. Multiple readers run concurrently
(let ()
  (define rwl (make-rwlock))
  (define started (make-channel))
  (define results (make-channel))
  (for ([i (in-range 5)])
    (thread
     (lambda ()
       (call-with-read-lock rwl
         (lambda ()
           (channel-put started i)
           (sleep 0.05)
           (channel-put results i))))))
  (for ([i (in-range 5)])
    (channel-get started))
  (define all-started (current-inexact-milliseconds))
  (for ([i (in-range 5)])
    (channel-get results))
  (define elapsed (- (current-inexact-milliseconds) all-started))
  (check-true (< elapsed 200) "readers should run concurrently, not sequentially")
  (displayln "PASS 1 — multiple readers run concurrently"))

;; 2. Writer gets exclusive access
(let ()
  (define rwl (make-rwlock))
  (define log '())
  (define log-mutex (make-semaphore 1))
  (define (log! msg)
    (call-with-semaphore log-mutex
      (lambda () (set! log (cons msg log)))))
  (define done (make-channel))
  (call-with-write-lock rwl
    (lambda ()
      (define t
        (thread
         (lambda ()
           (call-with-write-lock rwl
             (lambda ()
               (log! 'writer-2-ran)
               (channel-put done #t))))))
      (sleep 0.05)
      (log! 'writer-1-ran)))
  (channel-get done)
  (check-equal? (reverse log) '(writer-1-ran writer-2-ran))
  (displayln "PASS 2 — writer gets exclusive access"))

;; 3. Writer blocks new readers
(let ()
  (define rwl (make-rwlock))
  (define log '())
  (define log-mutex (make-semaphore 1))
  (define (log! msg)
    (call-with-semaphore log-mutex
      (lambda () (set! log (cons msg log)))))
  (define done (make-channel))
  (call-with-write-lock rwl
    (lambda ()
      (thread
       (lambda ()
         (call-with-read-lock rwl
           (lambda ()
             (log! 'reader-ran)
             (channel-put done #t)))))
      (sleep 0.05)
      (log! 'writer-ran)))
  (channel-get done)
  (check-equal? (reverse log) '(writer-ran reader-ran))
  (displayln "PASS 3 — writer blocks new readers"))

;; 4. Writer waits for existing readers
(let ()
  (define rwl (make-rwlock))
  (define log '())
  (define log-mutex (make-semaphore 1))
  (define (log! msg)
    (call-with-semaphore log-mutex
      (lambda () (set! log (cons msg log)))))
  (define reader-started (make-channel))
  (define done (make-channel))
  (thread
   (lambda ()
     (call-with-read-lock rwl
       (lambda ()
         (channel-put reader-started #t)
         (sleep 0.1)
         (log! 'reader-done)))))
  (channel-get reader-started)
  (thread
   (lambda ()
     (call-with-write-lock rwl
       (lambda ()
         (log! 'writer-done)
         (channel-put done #t)))))
  (channel-get done)
  (check-equal? (reverse log) '(reader-done writer-done))
  (displayln "PASS 4 — writer waits for existing readers"))

;; 5. Read lock survives exceptions
(let ()
  (define rwl (make-rwlock))
  (check-exn exn:fail?
    (lambda ()
      (call-with-read-lock rwl
        (lambda () (error "boom")))))
  (check-equal? (unbox (rwlock-readers rwl)) 0)
  (call-with-read-lock rwl (lambda () 'ok))
  (displayln "PASS 5 — read lock survives exceptions"))

;; 6. Write lock survives exceptions
(let ()
  (define rwl (make-rwlock))
  (check-exn exn:fail?
    (lambda ()
      (call-with-write-lock rwl
        (lambda () (error "boom")))))
  (call-with-write-lock rwl (lambda () 'ok))
  (displayln "PASS 6 — write lock survives exceptions"))

(displayln "")
(displayln "All rwlock tests passed.")

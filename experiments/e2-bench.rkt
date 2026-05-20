#lang racket

(require cnf cnf/lang)

;; E2: Multi-operation benchmark.
;;
;; 20 sequential renames, querying dependencies after each.
;; CNF's O(1) per-operation should compound while text pays O(N) every time.
;;
;; CNF path:  rename! → query deps (×20)
;; Text path: sed rename → grep deps (×20)

;; --- Source generation (shared with E1) ---

(define (generate-source n)
  (define ops '("+" "-" "*"))
  (define (pick-op i) (list-ref ops (modulo i (length ops))))
  (string-join
   (for/list ([i (in-range n)])
     (define name (format "f~a" i))
     (if (= i 0)
         (format "(defn ~a [a b]\n  (~a a b))" name (pick-op i))
         (let ([callee (format "f~a" (modulo (sub1 i) i))]
               [op (pick-op i)])
           (format "(defn ~a [a b]\n  (~a (~a a b) b))" name op callee))))
   "\n\n"))

(define (generate-text-files n dir)
  (define ops '("+" "-" "*"))
  (define (pick-op i) (list-ref ops (modulo i (length ops))))
  (make-directory* dir)
  (for ([i (in-range n)])
    (define name (format "f~a" i))
    (define src
      (if (= i 0)
          (format "(defn ~a [a b]\n  (~a a b))" name (pick-op i))
          (let ([callee (format "f~a" (modulo (sub1 i) i))]
                [op (pick-op i)])
            (format "(defn ~a [a b]\n  (~a (~a a b) b))" name op callee))))
    (define path (build-path dir (format "~a.fn" name)))
    (call-with-output-file path (lambda (out) (display src out)) #:exists 'replace)))

;; --- Timing ---

(define (time-ms thunk)
  (define t0 (current-inexact-milliseconds))
  (define result (thunk))
  (define t1 (current-inexact-milliseconds))
  (values result (- t1 t0)))

;; --- CNF Multi-Op ---

(define (cnf-multi-op n source num-ops)
  (reset-store!)
  (setup-eval!)
  (setup-graph!)
  (setup-lang!)
  (materialize!)

  (define-values (fns load-ms)
    (time-ms (lambda () (parse-program! source))))

  (define op-times
    (for/list ([k (in-range num-ops)])
      (define target-idx (modulo k (min n 20)))
      (define fn-id (list-ref fns target-idx))
      (define new-name (format "r~a-~a" k (current-name fn-id)))
      (define-values (_r op-ms)
        (time-ms (lambda ()
          (rename! fn-id new-name)
          (query (fn-depends-on (? caller) (? callee))))))
      op-ms))

  (values load-ms op-times))

;; --- Text Multi-Op ---

(define (text-multi-op n dir num-ops)
  (define-values (_s load-ms)
    (time-ms (lambda () (generate-text-files n dir))))

  (define names (make-hash))
  (for ([i (in-range n)])
    (hash-set! names i (format "f~a" i)))

  (define op-times
    (for/list ([k (in-range num-ops)])
      (define target-idx (modulo k (min n 20)))
      (define old-name (hash-ref names target-idx))
      (define new-name (format "r~a-~a" k old-name))
      (define-values (_r op-ms)
        (time-ms (lambda ()
          ;; Rename in definition file
          (define def-path (build-path dir (format "~a.fn" old-name)))
          (when (file-exists? def-path)
            (define src (file->string def-path))
            (define new-src (string-replace src old-name new-name))
            (define new-path (build-path dir (format "~a.fn" new-name)))
            (call-with-output-file new-path
              (lambda (out) (display new-src out)) #:exists 'replace)
            (when (not (equal? def-path new-path))
              (delete-file def-path)))
          ;; Find and update all call sites
          (for ([i (in-range n)])
            (define fname (hash-ref names i))
            (when (not (= i target-idx))
              (define path (build-path dir (format "~a.fn" fname)))
              (when (file-exists? path)
                (define src (file->string path))
                (when (string-contains? src (string-append "(" old-name " "))
                  (define new-src (string-replace src
                    (string-append "(" old-name " ")
                    (string-append "(" new-name " ")))
                  (call-with-output-file path
                    (lambda (out) (display new-src out)) #:exists 'replace)))))
          ;; Grep for dependency info
          (for/list ([i (in-range n)])
            (define fname (hash-ref names i))
            (define path (build-path dir (format "~a.fn" fname)))
            (when (file-exists? path)
              (file->string path))))))
      (hash-set! names target-idx new-name)
      op-ms))

  (values load-ms op-times))

;; --- Report ---

(define (run-e2 n num-ops)
  (printf "\n══════════════════════════════════════════\n")
  (printf "  N = ~a functions, ~a operations\n" n num-ops)
  (printf "══════════════════════════════════════════\n\n")

  (define source (generate-source n))
  (define tmp-dir (make-temporary-file "cnf-e2-~a" 'directory))

  (define-values (cnf-load cnf-ops) (cnf-multi-op n source num-ops))
  (define-values (text-load text-ops) (text-multi-op n tmp-dir num-ops))

  ;; Cleanup
  (for ([f (in-list (directory-list tmp-dir #:build? #t))])
    (delete-file f))
  (delete-directory tmp-dir)

  (define cnf-ops-total (apply + cnf-ops))
  (define text-ops-total (apply + text-ops))
  (define cnf-total (+ cnf-load cnf-ops-total))
  (define text-total (+ text-load text-ops-total))

  (define cnf-per-op (/ cnf-ops-total num-ops))
  (define text-per-op (/ text-ops-total num-ops))

  (printf "  ~a~a~a\n"
          (~a "" #:min-width 20)
          (~a "CNF" #:min-width 14)
          "Text")
  (printf "  ~a\n" (make-string 48 #\─))
  (printf "  ~a~a~a\n"
          (~a "Load/Parse" #:min-width 20)
          (~a (format "~a ms" (~r cnf-load #:precision 1)) #:min-width 14)
          (format "~a ms" (~r text-load #:precision 1)))
  (printf "  ~a~a~a\n"
          (~a "Ops total" #:min-width 20)
          (~a (format "~a ms" (~r cnf-ops-total #:precision 1)) #:min-width 14)
          (format "~a ms" (~r text-ops-total #:precision 1)))
  (printf "  ~a~a~a\n"
          (~a "Per-op avg" #:min-width 20)
          (~a (format "~a ms" (~r cnf-per-op #:precision 2)) #:min-width 14)
          (format "~a ms" (~r text-per-op #:precision 2)))
  (printf "  ~a\n" (make-string 48 #\─))
  (define total-ratio
    (if (> cnf-total 0) (~r (/ text-total cnf-total) #:precision 2) "∞"))
  (define ops-ratio
    (if (> cnf-ops-total 0) (~r (/ text-ops-total cnf-ops-total) #:precision 1) "∞"))
  (printf "  ~a~a~a  (ops ~ax)\n"
          (~a "TOTAL" #:min-width 20)
          (~a (format "~a ms" (~r cnf-total #:precision 1)) #:min-width 14)
          (format "~a ms" (~r text-total #:precision 1))
          ops-ratio)
  (printf "  Total speedup: ~ax\n" total-ratio)

  ;; Per-op progression (show every 5th)
  (printf "\n  Per-op cost progression (ms):\n")
  (printf "  ~a~a~a\n"
          (~a "Op #" #:min-width 10)
          (~a "CNF" #:min-width 14)
          "Text")
  (printf "  ~a\n" (make-string 38 #\─))
  (for ([i (in-range num-ops)]
        #:when (or (= i 0) (= i (sub1 num-ops))
                   (= (modulo i 5) 4)))
    (printf "  ~a~a~a\n"
            (~a (add1 i) #:min-width 10)
            (~a (~r (list-ref cnf-ops i) #:precision 2) #:min-width 14)
            (~r (list-ref text-ops i) #:precision 2)))

  (list n cnf-total text-total cnf-ops-total text-ops-total))

;; --- Main ---

(displayln "")
(displayln "================================================================")
(displayln "    E2: Multi-Operation Benchmark")
(displayln "================================================================")
(displayln "")
(displayln "Task: 20 sequential renames, querying deps after each.")
(displayln "")
(displayln "CNF path:  rename! → query (×20)")
(displayln "Text path: sed → grep (×20)")

(define results
  (for/list ([n '(200 500 1000)])
    (run-e2 n 20)))

(displayln "")
(displayln "================================================================")
(displayln "  Summary")
(displayln "================================================================")
(displayln "")
(printf "  ~a~a~a~a~a\n"
        (~a "N" #:min-width 8)
        (~a "CNF (ms)" #:min-width 12)
        (~a "Text (ms)" #:min-width 12)
        (~a "Speedup" #:min-width 10)
        "Ops speedup")
(printf "  ~a\n" (make-string 54 #\─))
(for ([r (in-list results)])
  (define n (first r))
  (define c (second r))
  (define t (third r))
  (define co (fourth r))
  (define to (list-ref r 4))
  (define ratio (if (> c 0) (~r (/ t c) #:precision 2) "∞"))
  (define ops-ratio (if (> co 0) (~r (/ to co) #:precision 1) "∞"))
  (printf "  ~a~a~a~a~ax\n"
          (~a n #:min-width 8)
          (~a (~r c #:precision 1) #:min-width 12)
          (~a (~r t #:precision 1) #:min-width 12)
          (~a (format "~ax" ratio) #:min-width 10)
          ops-ratio))
(displayln "")

#lang racket

(require cnf cnf/lang
         racket/runtime-path)

;; E1: Scripted agent workflow benchmark.
;;
;; Simulates the operations an agent would perform for a structural
;; editing task, comparing CNF graph operations against text equivalents.
;;
;; Task:
;;   1. Load N functions (parse / write files)
;;   2. Rename a shared function
;;   3. Find all affected callers
;;   4. Render/read affected source to verify
;;   5. Update a dependent expression
;;   6. Query final dependency graph
;;
;; Both paths do equivalent work. We measure wall-time.

;; --- Source generation ---

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

;; Generate equivalent text files for the text path
(define (generate-text-files n dir)
  (define ops '("+" "-" "*"))
  (define (pick-op i) (list-ref ops (modulo i (length ops))))
  (make-directory* dir)
  (define sources (make-hash))
  (for ([i (in-range n)])
    (define name (format "f~a" i))
    (define src
      (if (= i 0)
          (format "(defn ~a [a b]\n  (~a a b))" name (pick-op i))
          (let ([callee (format "f~a" (modulo (sub1 i) i))]
                [op (pick-op i)])
            (format "(defn ~a [a b]\n  (~a (~a a b) b))" name op callee))))
    (define path (build-path dir (format "~a.fn" name)))
    (call-with-output-file path (lambda (out) (display src out)) #:exists 'replace)
    (hash-set! sources name src))
  sources)

;; --- Timing ---

(define (time-ms thunk)
  (define t0 (current-inexact-milliseconds))
  (define result (thunk))
  (define t1 (current-inexact-milliseconds))
  (values result (- t1 t0)))

;; --- CNF Agent Path ---

(define (cnf-agent-task n source)
  (define times (make-hash))

  ;; Step 1: Parse program into claim graph + materialize
  (reset-store!)
  (setup-eval!)
  (setup-graph!)
  (setup-lang!)
  (materialize!)
  (define-values (fns parse-ms)
    (time-ms (lambda () (parse-program! source))))
  (hash-set! times 'load parse-ms)

  ;; Step 2: Rename f0 → renamed-f0
  (define-values (_r rename-ms)
    (time-ms (lambda () (rename! (first fns) "renamed-f0"))))
  (hash-set! times 'rename rename-ms)

  ;; Step 3: Find all affected callers
  (define-values (deps query-ms)
    (time-ms (lambda () (query (fn-depends-on (? caller) (? callee))))))
  (define affected
    (filter (lambda (s) (equal? (hash-ref s 'callee) (first fns))) deps))
  (hash-set! times 'find-affected query-ms)

  ;; Step 4: Render affected functions to verify rename propagated
  (define affected-ids (map (lambda (s) (hash-ref s 'caller)) affected))
  (define-values (rendered verify-ms)
    (time-ms (lambda ()
      (for/list ([id (in-list affected-ids)])
        (render-fn id)))))
  (hash-set! times 'verify verify-ms)

  ;; Step 5: Render all to check consistency
  (define-values (_all render-ms)
    (time-ms (lambda () (render-program fns))))
  (hash-set! times 'render-all render-ms)

  ;; Step 6: Final dep query
  (define-values (final-deps final-ms)
    (time-ms (lambda () (query (fn-depends-on (? caller) (? callee))))))
  (hash-set! times 'final-query final-ms)

  (values times (length affected) (length final-deps)))

;; --- Text Agent Path ---

(define (text-agent-task n dir)
  (define times (make-hash))

  ;; Step 1: Write files
  (define-values (sources write-ms)
    (time-ms (lambda () (generate-text-files n dir))))
  (hash-set! times 'load write-ms)

  ;; Step 2: Rename f0 → renamed-f0 (read + edit every file)
  (define-values (_r rename-ms)
    (time-ms (lambda ()
      ;; Rename the definition
      (define def-path (build-path dir "f0.fn"))
      (define def-src (file->string def-path))
      (define new-def (string-replace def-src "f0" "renamed-f0"))
      (call-with-output-file def-path
        (lambda (out) (display new-def out)) #:exists 'replace)
      ;; Find and update all call sites (scan every file)
      (for ([i (in-range 1 n)])
        (define path (build-path dir (format "f~a.fn" i)))
        (define src (file->string path))
        (when (string-contains? src "(f0 ")
          (define new-src (string-replace src "(f0 " "(renamed-f0 "))
          (call-with-output-file path
            (lambda (out) (display new-src out)) #:exists 'replace))))))
  (hash-set! times 'rename rename-ms)

  ;; Step 3: Find all affected callers (grep all files)
  (define-values (affected grep-ms)
    (time-ms (lambda ()
      (for/list ([i (in-range 1 n)]
                 #:when (let ([src (file->string
                                    (build-path dir (format "f~a.fn" i)))])
                          (string-contains? src "renamed-f0")))
        i))))
  (hash-set! times 'find-affected grep-ms)

  ;; Step 4: Read affected files to verify
  (define-values (_v verify-ms)
    (time-ms (lambda ()
      (for/list ([i (in-list affected)])
        (file->string (build-path dir (format "f~a.fn" i)))))))
  (hash-set! times 'verify verify-ms)

  ;; Step 5: Read all files
  (define-values (_all render-ms)
    (time-ms (lambda ()
      (for/list ([i (in-range n)])
        (file->string (build-path dir (format "f~a.fn" i)))))))
  (hash-set! times 'render-all render-ms)

  ;; Step 6: Final dependency scan (grep all files for call patterns)
  (define-values (deps final-ms)
    (time-ms (lambda ()
      (for/list ([i (in-range 1 n)]
                 #:when (let ([src (file->string
                                    (build-path dir (format "f~a.fn" i)))])
                          (regexp-match? #rx"\\([a-z]" src)))
        i))))
  (hash-set! times 'final-query final-ms)

  (values times (length affected) (length deps)))

;; --- Report ---

(define steps '(load rename find-affected verify render-all final-query))
(define step-labels
  (hash 'load "Load/Parse"
        'rename "Rename"
        'find-affected "Find affected"
        'verify "Verify"
        'render-all "Render/Read all"
        'final-query "Final dep query"))

(define (run-e1 n)
  (printf "\n══════════════════════════════════════════\n")
  (printf "  N = ~a functions\n" n)
  (printf "══════════════════════════════════════════\n\n")

  (define source (generate-source n))
  (define tmp-dir (make-temporary-file "cnf-e1-~a" 'directory))

  (define-values (cnf-times cnf-affected cnf-deps) (cnf-agent-task n source))
  (define-values (text-times text-affected text-deps) (text-agent-task n tmp-dir))

  ;; Cleanup
  (for ([f (in-list (directory-list tmp-dir #:build? #t))])
    (delete-file f))
  (delete-directory tmp-dir)

  (define cnf-total
    (for/sum ([s (in-list steps)]) (hash-ref cnf-times s 0)))
  (define text-total
    (for/sum ([s (in-list steps)]) (hash-ref text-times s 0)))

  (printf "  ~a~a~a~a\n"
          (~a "Step" #:min-width 20)
          (~a "CNF (ms)" #:min-width 12)
          (~a "Text (ms)" #:min-width 12)
          "Ratio")
  (printf "  ~a\n" (make-string 56 #\─))

  (for ([s (in-list steps)])
    (define c (hash-ref cnf-times s 0))
    (define t (hash-ref text-times s 0))
    (define ratio (if (> c 0) (~r (/ t c) #:precision 1) "∞"))
    (printf "  ~a~a~a~ax\n"
            (~a (hash-ref step-labels s) #:min-width 20)
            (~a (~r c #:precision 1) #:min-width 12)
            (~a (~r t #:precision 1) #:min-width 12)
            ratio))

  (printf "  ~a\n" (make-string 56 #\─))
  (define total-ratio (if (> cnf-total 0) (~r (/ text-total cnf-total) #:precision 2) "∞"))
  (printf "  ~a~a~a~ax\n"
          (~a "TOTAL" #:min-width 20)
          (~a (~r cnf-total #:precision 1) #:min-width 12)
          (~a (~r text-total #:precision 1) #:min-width 12)
          total-ratio)

  (printf "\n  CNF: ~a affected callers, ~a total deps\n" cnf-affected cnf-deps)
  (printf "  Text: ~a affected callers, ~a deps found\n" text-affected text-deps)

  (list n cnf-total text-total))

;; --- Main ---

(displayln "")
(displayln "================================================================")
(displayln "    E1: Agent Workflow Benchmark (Scripted)")
(displayln "================================================================")
(displayln "")
(displayln "Task: load program, rename shared function, find affected callers,")
(displayln "      verify rename propagated, render all, query final deps.")
(displayln "")
(displayln "CNF path:  parse → materialize → rename! → query → render")
(displayln "Text path: write files → sed → grep → read → grep")

(define results
  (for/list ([n '(50 200 500 1000)])
    (run-e1 n)))

(displayln "")
(displayln "================================================================")
(displayln "  Summary")
(displayln "================================================================")
(displayln "")
(printf "  ~a~a~a~a\n"
        (~a "N" #:min-width 8)
        (~a "CNF (ms)" #:min-width 12)
        (~a "Text (ms)" #:min-width 12)
        "Speedup")
(printf "  ~a\n" (make-string 44 #\─))
(for ([r (in-list results)])
  (define n (first r))
  (define c (second r))
  (define t (third r))
  (define ratio (if (> c 0) (~r (/ t c) #:precision 2) "∞"))
  (printf "  ~a~a~a~ax\n"
          (~a n #:min-width 8)
          (~a (~r c #:precision 1) #:min-width 12)
          (~a (~r t #:precision 1) #:min-width 12)
          ratio))
(displayln "")

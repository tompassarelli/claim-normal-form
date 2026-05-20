#lang racket

(require cnf cnf/lang)

;; E3: Agent Comparison Benchmark
;;
;; A realistic agent refactoring session: discover patterns, rename
;; functions, define custom derived relations, evolve their definitions.
;;
;; Two paths perform equivalent operations:
;;   CNF:  claim graph + Datalog + homoiconic rules
;;   Text: files + grep + sed + ad-hoc computation
;;
;; 18 operations in 5 phases:
;;   Phase 1: Discovery (2 ops)
;;   Phase 2: Rename + query deps (5 compound ops)
;;   Phase 3: Define custom rules + query (4 ops)
;;   Phase 4: Rename + query custom rule (5 compound ops)
;;   Phase 5: Schema evolution (2 ops)
;;
;; Hub-and-spoke dependency graph:
;;   Every 5th function calls f0 (the hub); others call predecessor.
;;   Gives a rich graph with shared deps and multi-hop chains.

;; --- Source generation ---

(define (generate-source n)
  (define ops '("+" "-" "*"))
  (define (pick-op i) (list-ref ops (modulo i (length ops))))
  (string-join
   (for/list ([i (in-range n)])
     (define name (format "f~a" i))
     (if (= i 0)
         (format "(defn ~a [a b]\n  (~a a b))" name (pick-op i))
         (let ([callee (format "f~a" (if (= (modulo i 5) 0) 0 (sub1 i)))]
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
          (let ([callee (format "f~a" (if (= (modulo i 5) 0) 0 (sub1 i)))]
                [op (pick-op i)])
            (format "(defn ~a [a b]\n  (~a (~a a b) b))" name op callee))))
    (call-with-output-file (build-path dir (format "~a.fn" name))
      (lambda (out) (display src out)) #:exists 'replace)))

;; --- Timing ---

(define (time-ms thunk)
  (define t0 (current-inexact-milliseconds))
  (define result (thunk))
  (define t1 (current-inexact-milliseconds))
  (values result (- t1 t0)))

;; --- Text helpers ---

(define (text-rename! dir n names target-idx new-name)
  (define old-name (hash-ref names target-idx))
  (define def-path (build-path dir (format "~a.fn" old-name)))
  (when (file-exists? def-path)
    (define src (file->string def-path))
    (define new-src (string-replace src old-name new-name))
    (define new-path (build-path dir (format "~a.fn" new-name)))
    (call-with-output-file new-path
      (lambda (out) (display new-src out)) #:exists 'replace)
    (when (not (equal? def-path new-path))
      (delete-file def-path)))
  (for ([i (in-range n)]
        #:when (not (= i target-idx)))
    (define fname (hash-ref names i))
    (define path (build-path dir (format "~a.fn" fname)))
    (when (file-exists? path)
      (define src (file->string path))
      (when (string-contains? src (string-append "(" old-name " "))
        (define new-src (string-replace src
          (string-append "(" old-name " ")
          (string-append "(" new-name " ")))
        (call-with-output-file path
          (lambda (out) (display new-src out)) #:exists 'replace))))
  (hash-set! names target-idx new-name))

(define (text-find-callers dir n names target-idx)
  (define target-name (hash-ref names target-idx))
  (for/list ([i (in-range n)]
             #:when (not (= i target-idx))
             #:when (let ([path (build-path dir (format "~a.fn" (hash-ref names i)))])
                      (and (file-exists? path)
                           (string-contains? (file->string path)
                             (string-append "(" target-name " ")))))
    i))

(define (text-build-call-map dir n names)
  (define call-map (make-hash))
  (for ([i (in-range n)])
    (define fname (hash-ref names i))
    (define path (build-path dir (format "~a.fn" fname)))
    (when (file-exists? path)
      (define src (file->string path))
      (for ([j (in-range n)]
            #:when (not (= j i)))
        (define callee (hash-ref names j))
        (when (string-contains? src (string-append "(" callee " "))
          (hash-set! call-map i j)))))
  call-map)

(define (compute-two-hop call-map)
  (for*/list ([(a b) (in-hash call-map)]
              #:when (hash-has-key? call-map b)
              [c (in-value (hash-ref call-map b))])
    (list a c)))

(define (compute-three-hop call-map)
  (for*/list ([(a b) (in-hash call-map)]
              #:when (hash-has-key? call-map b)
              [c (in-value (hash-ref call-map b))]
              #:when (hash-has-key? call-map c)
              [d (in-value (hash-ref call-map c))])
    (list a d)))

(define (compute-shared-deps call-map)
  (define rev (make-hash))
  (for ([(caller callee) (in-hash call-map)])
    (hash-update! rev callee (lambda (s) (cons caller s)) '()))
  (for*/list ([(callee callers) (in-hash rev)]
              [a (in-list callers)]
              [b (in-list callers)])
    (list a b callee)))

;; --- CNF session ---

(define (cnf-session n source)
  (reset-store!)
  (setup-eval!)
  (setup-graph!)
  (setup-schema!)
  (setup-rule-predicates!)
  (setup-lang!)
  (materialize!)

  (define-values (fns parse-ms)
    (time-ms (lambda () (parse-program! source))))

  ;; Phase 1: Discovery
  (define-values (_d1 disc1-ms)
    (time-ms (lambda ()
      (query (fn-depends-on (list-ref fns 50) (? callee))))))
  (define-values (d2 disc2-ms)
    (time-ms (lambda ()
      (query (fn-depends-on (? caller) (list-ref fns 0))))))

  ;; Phase 2: 5 renames + dep queries
  (define phase2-ops
    (for/list ([k (in-range 5)])
      (define fn-id (list-ref fns (+ k 1)))
      (define new-name (format "r~a" k))
      (define-values (_r rename-ms)
        (time-ms (lambda () (rename! fn-id new-name))))
      (define-values (_q query-ms)
        (time-ms (lambda ()
          (query (fn-depends-on (? caller) (? callee))))))
      (+ rename-ms query-ms)))

  ;; Phase 3: Define custom rules + query
  (define-values (indirect-ent rule1-ms)
    (time-ms (lambda ()
      (define-rule!/claims
        (atom 'indirect-dep (list (var 'a) (var 'c)))
        (list (atom 'fn-depends-on (list (var 'a) (var 'b)))
              (atom 'fn-depends-on (list (var 'b) (var 'c))))))))

  (define-values (indirect-results query1-ms)
    (time-ms (lambda ()
      (query (indirect-dep (? a) (? c))))))

  (define-values (_shared-ent rule2-ms)
    (time-ms (lambda ()
      (define-rule!/claims
        (atom 'shared-dep (list (var 'a) (var 'b) (var 'c)))
        (list (atom 'fn-depends-on (list (var 'a) (var 'c)))
              (atom 'fn-depends-on (list (var 'b) (var 'c))))))))

  (define-values (shared-results query2-ms)
    (time-ms (lambda ()
      (query (shared-dep (? a) (? b) (? c))))))

  ;; Phase 4: 5 more renames + indirect-dep query
  (define phase4-ops
    (for/list ([k (in-range 5 10)])
      (define fn-id (list-ref fns (+ k 1)))
      (define new-name (format "r~a" k))
      (define-values (_r rename-ms)
        (time-ms (lambda () (rename! fn-id new-name))))
      (define-values (_q query-ms)
        (time-ms (lambda ()
          (query (indirect-dep (? a) (? c))))))
      (+ rename-ms query-ms)))

  ;; Phase 5: Schema evolution
  (define-values (_3h-ent supersede-ms)
    (time-ms (lambda ()
      (supersede-rule! indirect-ent
        (atom 'indirect-dep (list (var 'a) (var 'd)))
        (list (atom 'fn-depends-on (list (var 'a) (var 'b)))
              (atom 'fn-depends-on (list (var 'b) (var 'c)))
              (atom 'fn-depends-on (list (var 'c) (var 'd))))))))

  (define-values (three-hop-results query3-ms)
    (time-ms (lambda ()
      (query (indirect-dep (? a) (? d))))))

  (hasheq
   'parse parse-ms
   'disc1 disc1-ms  'disc2 disc2-ms
   'phase2 phase2-ops
   'rule1 rule1-ms  'query1 query1-ms
   'rule2 rule2-ms  'query2 query2-ms
   'phase4 phase4-ops
   'supersede supersede-ms  'query3 query3-ms
   'n-indirect (length indirect-results)
   'n-shared (length shared-results)
   'n-three-hop (length three-hop-results)
   'n-callers-f0 (length d2)))

;; --- Text session ---

(define (text-session n dir)
  (define-values (_g gen-ms)
    (time-ms (lambda () (generate-text-files n dir))))

  (define names (make-hash))
  (for ([i (in-range n)])
    (hash-set! names i (format "f~a" i)))

  ;; Phase 1: Discovery
  (define-values (_d1 disc1-ms)
    (time-ms (lambda ()
      (define path (build-path dir (format "~a.fn" (hash-ref names 50))))
      (define src (file->string path))
      (for/list ([j (in-range n)]
                 #:when (not (= j 50))
                 #:when (string-contains? src
                           (string-append "(" (hash-ref names j) " ")))
        j))))

  (define-values (d2 disc2-ms)
    (time-ms (lambda () (text-find-callers dir n names 0))))

  ;; Phase 2: 5 renames + read all files (dep query)
  (define phase2-ops
    (for/list ([k (in-range 5)])
      (define new-name (format "r~a" k))
      (define-values (_r op-ms)
        (time-ms (lambda ()
          (text-rename! dir n names (+ k 1) new-name)
          (for ([i (in-range n)])
            (define path (build-path dir (format "~a.fn" (hash-ref names i))))
            (when (file-exists? path)
              (file->string path))))))
      op-ms))

  ;; Phase 3: Build call map + compute derived relations
  (define call-map #f)
  (define-values (_cm map-ms)
    (time-ms (lambda ()
      (set! call-map (text-build-call-map dir n names)))))

  (define indirect-results #f)
  (define-values (_th two-hop-ms)
    (time-ms (lambda ()
      (set! indirect-results (compute-two-hop call-map)))))

  (define shared-results #f)
  (define-values (_sd shared-ms)
    (time-ms (lambda ()
      (set! shared-results (compute-shared-deps call-map)))))

  ;; Phase 4: 5 renames + rebuild map + recompute two-hop
  (define phase4-ops
    (for/list ([k (in-range 5 10)])
      (define new-name (format "r~a" k))
      (define-values (_r op-ms)
        (time-ms (lambda ()
          (text-rename! dir n names (+ k 1) new-name)
          (set! call-map (text-build-call-map dir n names))
          (compute-two-hop call-map))))
      op-ms))

  ;; Phase 5: Rebuild map + compute three-hop
  (define three-hop-results #f)
  (define-values (_3h three-hop-ms)
    (time-ms (lambda ()
      (set! call-map (text-build-call-map dir n names))
      (set! three-hop-results (compute-three-hop call-map)))))

  (hasheq
   'gen gen-ms
   'disc1 disc1-ms  'disc2 disc2-ms
   'phase2 phase2-ops
   'map map-ms  'two-hop two-hop-ms
   'shared shared-ms
   'phase4 phase4-ops
   'three-hop three-hop-ms
   'n-indirect (length indirect-results)
   'n-shared (length shared-results)
   'n-three-hop (length three-hop-results)
   'n-callers-f0 (length d2)))

;; --- Report ---

(define (fmt-ms v) (~r v #:precision 1))
(define (fmt-ms2 v) (~r v #:precision 2))
(define (col s [w 16]) (~a s #:min-width w))

(define (run-e3 n)
  (define source (generate-source n))
  (define tmp-dir (make-temporary-file "cnf-e3-~a" 'directory))

  (define cnf (cnf-session n source))
  (define txt (text-session n tmp-dir))

  ;; Cleanup
  (for ([f (in-list (directory-list tmp-dir #:build? #t))])
    (delete-file f))
  (delete-directory tmp-dir)

  (printf "\n══════════════════════════════════════════════════════\n")
  (printf "  E3: Agent Comparison — N = ~a\n" n)
  (printf "══════════════════════════════════════════════════════\n")

  (define (row label cnf-val txt-val [note ""])
    (printf "  ~a~a~a~a\n"
            (col label 26) (col (format "~a ms" (fmt-ms cnf-val)))
            (col (format "~a ms" (fmt-ms txt-val)))
            note))

  (printf "\n  ~a~a~a\n" (col "" 26) (col "CNF") "Text")
  (printf "  ~a\n" (make-string 60 #\─))
  (row "Load" (hash-ref cnf 'parse) (hash-ref txt 'gen))

  (printf "\n  Phase 1: Discovery\n")
  (row "  Deps of f50" (hash-ref cnf 'disc1) (hash-ref txt 'disc1))
  (row "  Callers of f0" (hash-ref cnf 'disc2) (hash-ref txt 'disc2))

  (define cnf-p2 (apply + (hash-ref cnf 'phase2)))
  (define txt-p2 (apply + (hash-ref txt 'phase2)))
  (printf "\n  Phase 2: Rename + dep query (×5)\n")
  (row "  Total" cnf-p2 txt-p2)
  (row "  Per-op" (/ cnf-p2 5) (/ txt-p2 5))

  (printf "\n  Phase 3: Custom rules\n")
  (row "  Define indirect-dep"
       (hash-ref cnf 'rule1)
       (hash-ref txt 'map)
       "text: build call map")
  (row "  Query indirect-dep"
       (hash-ref cnf 'query1)
       (hash-ref txt 'two-hop)
       "cnf: fixpoint recompute")
  (row "  Define shared-dep"
       (hash-ref cnf 'rule2)
       0.0
       "text: map already built")
  (row "  Query shared-dep"
       (hash-ref cnf 'query2)
       (hash-ref txt 'shared))

  (define cnf-p4 (apply + (hash-ref cnf 'phase4)))
  (define txt-p4 (apply + (hash-ref txt 'phase4)))
  (printf "\n  Phase 4: Rename + query indirect-dep (×5)\n")
  (row "  Total" cnf-p4 txt-p4)
  (row "  Per-op" (/ cnf-p4 5) (/ txt-p4 5)
       "text: rebuilds map each time")

  (printf "\n  Phase 5: Schema evolution\n")
  (row "  Supersede → 3-hop"
       (hash-ref cnf 'supersede) 0.0 "CNF only")
  (row "  Query 3-hop"
       (hash-ref cnf 'query3)
       (hash-ref txt 'three-hop)
       "text: rebuilds from scratch")

  ;; Totals
  (define cnf-ops
    (+ (hash-ref cnf 'disc1) (hash-ref cnf 'disc2)
       cnf-p2
       (hash-ref cnf 'rule1) (hash-ref cnf 'query1)
       (hash-ref cnf 'rule2) (hash-ref cnf 'query2)
       cnf-p4
       (hash-ref cnf 'supersede) (hash-ref cnf 'query3)))
  (define txt-ops
    (+ (hash-ref txt 'disc1) (hash-ref txt 'disc2)
       txt-p2
       (hash-ref txt 'map) (hash-ref txt 'two-hop)
       (hash-ref txt 'shared)
       txt-p4
       (hash-ref txt 'three-hop)))
  (define cnf-total (+ (hash-ref cnf 'parse) cnf-ops))
  (define txt-total (+ (hash-ref txt 'gen) txt-ops))

  (printf "\n  ~a\n" (make-string 60 #\─))
  (row "Ops only" cnf-ops txt-ops)
  (row "TOTAL" cnf-total txt-total)
  (printf "  ~aSpeedup: ~ax\n" (col "" 26)
          (~r (/ txt-total cnf-total) #:precision 2))

  ;; Result verification
  (printf "\n  Results:\n")
  (printf "  ~a~a~a~a\n" (col "" 4) (col "Relation" 20) (col "CNF") "Text")
  (printf "  ~a~a\n" (col "" 4) (make-string 48 #\─))
  (for ([pair (list
               (list "Indirect deps" 'n-indirect)
               (list "Shared deps" 'n-shared)
               (list "Three-hop deps" 'n-three-hop)
               (list "Callers of f0" 'n-callers-f0))])
    (define label (first pair))
    (define key (second pair))
    (define cv (hash-ref cnf key))
    (define tv (hash-ref txt key))
    (printf "  ~a~a~a~a~a\n"
            (col "" 4) (col label 20) (col cv) (col tv)
            (if (= cv tv) "✓" "✗")))

  ;; Phase 4 breakdown
  (printf "\n  Phase 4 per-op breakdown:\n")
  (for ([k (in-range 5)]
        [ct (in-list (hash-ref cnf 'phase4))]
        [tt (in-list (hash-ref txt 'phase4))])
    (printf "    Op ~a:  CNF ~a ms    Text ~a ms\n"
            (+ k 1) (fmt-ms2 ct) (fmt-ms2 tt)))

  (list n cnf-total txt-total cnf-ops txt-ops
        cnf-p4 txt-p4))

;; --- Main ---

(displayln "")
(displayln "================================================================")
(displayln "    E3: Agent Comparison Benchmark")
(displayln "================================================================")
(displayln "")
(displayln "Task: Realistic agent session — discover, rename, define")
(displayln "custom derived relations, evolve their definitions.")
(displayln "")
(displayln "CNF path:  claim graph + Datalog + homoiconic rules")
(displayln "Text path: files + grep + sed + ad-hoc computation")

(define results
  (for/list ([n '(100 200 500)])
    (run-e3 n)))

(displayln "")
(displayln "================================================================")
(displayln "  Scaling Summary")
(displayln "================================================================")
(displayln "")
(printf "  ~a~a~a~a~a~a\n"
        (col "N" 8) (col "CNF (ms)" 12) (col "Text (ms)" 12)
        (col "Speedup" 10) (col "Ops ratio") "Phase4 ratio")
(printf "  ~a\n" (make-string 70 #\─))
(for ([r (in-list results)])
  (define n (first r))
  (define ct (second r))
  (define tt (third r))
  (define co (fourth r))
  (define to (list-ref r 4))
  (define cp4 (list-ref r 5))
  (define tp4 (list-ref r 6))
  (printf "  ~a~a~a~a~a~ax\n"
          (col n 8)
          (col (fmt-ms ct) 12)
          (col (fmt-ms tt) 12)
          (col (format "~ax" (~r (/ tt ct) #:precision 2)) 10)
          (col (format "~ax" (~r (/ to co) #:precision 1)))
          (~r (/ tp4 cp4) #:precision 0)))
(displayln "")

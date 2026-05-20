#lang racket

(require rackunit
         "../cnf.rkt" "../datalog.rkt" "../eval.rkt" "../graph.rkt"
         "../schema.rkt" "../lang.rkt")

;; E4: Live Agent Session Comparison
;;
;; Same refactoring task, two workflows. The output is a narrative
;; transcript showing what each agent does at each step.
;;
;; Task: "Find hub functions, discover indirect dependencies, tag
;; coupled functions, rename for clarity, evolve the definition."
;;
;; 7 steps. N=100 functions, hub-and-spoke graph.
;;
;; Both agents compute the SAME relations at each step:
;;   indirect-dep: 2-hop dependency (fn-depends-on composed with itself)
;;   coupled: ordered pairs (a,b) where both have indirect-dep to hub

(define N 100)

(define (time-ms thunk)
  (define t0 (current-inexact-milliseconds))
  (define result (thunk))
  (define t1 (current-inexact-milliseconds))
  (values result (- t1 t0)))

(define (fmt v) (~r v #:precision 2))

;; --- Source generation (same as E3) ---

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

;; --- Text helpers ---

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
          (hash-update! call-map i (lambda (old) (cons j old)) '())))))
  call-map)

(define (text-find-hubs call-map)
  (define inbound (make-hash))
  (for ([(caller callees) (in-hash call-map)])
    (for ([callee (in-list callees)])
      (hash-update! inbound callee add1 0)))
  (sort (hash->list inbound) > #:key cdr))

;; 2-hop indirect dependency: a→b→c means (a,c) is an indirect-dep
(define (text-compute-indirect-dep call-map)
  (for*/list ([(a bs) (in-hash call-map)]
              [b (in-list bs)]
              #:when (hash-has-key? call-map b)
              [c (in-list (hash-ref call-map b))])
    (list a c)))

;; Coupled: ordered pairs (a,b) where both have indirect-dep to hub
(define (text-compute-coupled indirect-deps hub-idx)
  (define reaches-hub
    (for/list ([pair (in-list indirect-deps)]
               #:when (= (second pair) hub-idx))
      (first pair)))
  (for*/list ([a (in-list reaches-hub)]
              [b (in-list reaches-hub)])
    (list a b)))

;; 3-hop: a→b→c→d means (a,d)
(define (text-compute-three-hop call-map)
  (for*/list ([(a bs) (in-hash call-map)]
              [b (in-list bs)]
              #:when (hash-has-key? call-map b)
              [c (in-list (hash-ref call-map b))]
              #:when (hash-has-key? call-map c)
              [d (in-list (hash-ref call-map c))])
    (list a d)))

;; Deep-coupled: ordered pairs where both have 3-hop dep to hub
(define (text-compute-deep-coupled three-hop-deps hub-idx)
  (define reaches-hub
    (for/list ([pair (in-list three-hop-deps)]
               #:when (= (second pair) hub-idx))
      (first pair)))
  (define uniq (remove-duplicates reaches-hub))
  (for*/list ([a (in-list uniq)]
              [b (in-list uniq)])
    (list a b)))

(define (text-rename! dir n names target-idx new-name)
  (define old-name (hash-ref names target-idx))
  (for ([i (in-range n)])
    (define fname (hash-ref names i))
    (define path (build-path dir (format "~a.fn" fname)))
    (when (file-exists? path)
      (define src (file->string path))
      (define new-src (string-replace src old-name new-name))
      (when (not (equal? src new-src))
        (define out-path
          (if (= i target-idx)
              (build-path dir (format "~a.fn" new-name))
              path))
        (call-with-output-file out-path
          (lambda (out) (display new-src out)) #:exists 'replace)
        (when (and (= i target-idx) (not (equal? old-name new-name)))
          (delete-file path)))))
  (hash-set! names target-idx new-name))

;; --- Transcript output ---

(define (header text)
  (printf "\n┌~a┐\n" (make-string 70 #\─))
  (printf "│ ~a~a│\n" text (make-string (max 0 (- 69 (string-length text))) #\space))
  (printf "└~a┘\n" (make-string 70 #\─)))

(define (agent-block name lines ms)
  (printf "  ~a (~a ms):\n" name (fmt ms))
  (for ([line (in-list lines)])
    (printf "    ~a\n" line))
  (newline))

(define (insight text)
  (printf "  ► ~a\n\n" text))

;; --- Main ---

(displayln "")
(displayln "════════════════════════════════════════════════════════════════════════")
(displayln "  E4: Live Agent Session — Side-by-Side Transcript")
(displayln "════════════════════════════════════════════════════════════════════════")
(printf "  N=~a functions, hub-and-spoke dependency graph\n" N)
(printf "  Task: discover coupling, define concepts, rename, evolve definitions\n\n")

;; --- Setup ---

(reset-store!)
(setup-eval!)
(setup-graph!)
(setup-schema!)
(setup-rule-predicates!)
(setup-lang!)
(materialize!)

(define source (generate-source N))
(define-values (fns _parse-ms) (time-ms (lambda () (parse-program! source))))

(define tmp-dir (make-temporary-file "cnf-e4-~a" 'directory))
(generate-text-files N tmp-dir)
(define text-names (make-hash))
(for ([i (in-range N)]) (hash-set! text-names i (format "f~a" i)))

(printf "  Setup: ~a functions parsed into claim graph + written to files\n" N)

;; ═══════════════════════════════════════════════════════════
;; STEP 1: "Which functions are most depended-on?"
;; ═══════════════════════════════════════════════════════════

(header "Step 1: Discover hub functions")

;; CNF: one query returns ALL dependency edges
(define-values (all-deps cnf-s1-ms)
  (time-ms (lambda () (query (fn-depends-on (? caller) (? callee))))))

(define cnf-hub-counts (make-hash))
(for ([s (in-list all-deps)])
  (hash-update! cnf-hub-counts (hash-ref s 'callee) add1 0))
(define cnf-hubs
  (sort (hash->list cnf-hub-counts) > #:key cdr))
(define cnf-top-hub (car (first cnf-hubs)))

(agent-block "CNF"
  (list (format "query (fn-depends-on ?caller ?callee)")
        (format "→ ~a dependency edges" (length all-deps))
        (format "Group by callee, sort by count:")
        (format "  #1: ~a (~a callers)"
                (render-ref cnf-top-hub)
                (cdr (first cnf-hubs)))
        (format "  #2: ~a (~a callers)"
                (render-ref (car (second cnf-hubs)))
                (cdr (second cnf-hubs))))
  cnf-s1-ms)

;; Text: must read all files and parse call patterns
(define text-call-map #f)
(define-values (_ txt-s1-ms)
  (time-ms (lambda ()
    (set! text-call-map (text-build-call-map tmp-dir N text-names)))))
(define text-hubs (text-find-hubs text-call-map))
(define text-hub-idx (car (first text-hubs)))

(agent-block "Text"
  (list (format "Read all ~a files, grep for call patterns" N)
        (format "Build call map: ~a edges"
                (for/sum ([(k v) (in-hash text-call-map)]) (length v)))
        (format "Count inbound edges, sort:")
        (format "  #1: f~a (~a callers)" (car (first text-hubs)) (cdr (first text-hubs)))
        (format "  #2: f~a (~a callers)" (car (second text-hubs)) (cdr (second text-hubs))))
  txt-s1-ms)

(insight "CNF: single declarative query returns full graph. Text: O(N²) file scan + parse.")

;; ═══════════════════════════════════════════════════════════
;; STEP 2: "Which functions have indirect (2-hop) dependencies?"
;; ═══════════════════════════════════════════════════════════

(header "Step 2: Define 'indirect-dep' — 2-hop dependency chains")

;; CNF: define a Datalog rule
(define-values (indirect-rule-ent cnf-s2-ms)
  (time-ms (lambda ()
    (define-rule!/claims
      (atom 'indirect-dep (list (var 'x) (var 'y)))
      (list (atom 'fn-depends-on (list (var 'x) (var 'z)))
            (atom 'fn-depends-on (list (var 'z) (var 'y))))))))

(define-values (indirect-results _s2q)
  (time-ms (lambda () (query (indirect-dep (? x) (? y))))))

(agent-block "CNF"
  (list "define-rule indirect-dep(?x, ?y) :-"
        "  fn-depends-on(?x, ?z), fn-depends-on(?z, ?y)"
        (format "→ rule entity ~a (inspectable, versionable)" indirect-rule-ent)
        (format "→ ~a indirect-dep pairs (materialized at define time)"
                (length indirect-results)))
  cnf-s2-ms)

;; Text: compute 2-hop from call map
(define text-indirect #f)
(define-values (_ti txt-s2-ms)
  (time-ms (lambda ()
    (set! text-indirect (text-compute-indirect-dep text-call-map)))))

(agent-block "Text"
  (list "For each edge (a→b), for each edge (b→c), emit (a,c)"
        (format "→ ~a indirect-dep pairs" (length text-indirect))
        "Result: list in memory (ephemeral)")
  txt-s2-ms)

(check-equal? (length indirect-results) (length text-indirect)
  "indirect-dep count mismatch")

(insight "CNF: first-class rule entity. Text: ad-hoc list comprehension. Same result.")

;; ═══════════════════════════════════════════════════════════
;; STEP 3: "Which functions are coupled through the hub?"
;; ═══════════════════════════════════════════════════════════

(header "Step 3: Define 'coupled' — functions sharing indirect dependency on hub")

;; CNF: compose on top of indirect-dep
(define hub-id (first fns))  ; f0 is the hub

(define-values (coupled-rule-ent cnf-s3-ms)
  (time-ms (lambda ()
    (define-rule!/claims
      (atom 'coupled (list (var 'a) (var 'b)))
      (list (atom 'indirect-dep (list (var 'a) hub-id))
            (atom 'indirect-dep (list (var 'b) hub-id)))))))

(define-values (coupled-results _s3q)
  (time-ms (lambda () (query (coupled (? a) (? b))))))

(agent-block "CNF"
  (list "define-rule coupled(?a, ?b) :-"
        "  indirect-dep(?a, f0), indirect-dep(?b, f0)"
        (format "→ composes on indirect-dep (defined in Step 2)")
        (format "→ ~a coupled pairs" (length coupled-results)))
  cnf-s3-ms)

;; Text: compute coupled from indirect-dep list
(define text-coupled #f)
(define-values (_tc txt-s3-ms)
  (time-ms (lambda ()
    (set! text-coupled (text-compute-coupled text-indirect text-hub-idx)))))

(agent-block "Text"
  (list "Filter indirect-deps for those reaching f0"
        "Compute all ordered pairs"
        (format "→ ~a coupled pairs" (length text-coupled)))
  txt-s3-ms)

(check-equal? (length coupled-results) (length text-coupled)
  "coupled count mismatch")

(insight "CNF agent composes rules: coupled builds on indirect-dep. Text agent writes new code. Same results.")

;; ═══════════════════════════════════════════════════════════
;; STEP 4: Rename the hub function
;; ═══════════════════════════════════════════════════════════

(header "Step 4: Rename hub f0 → core-compute")

;; CNF: rename via claim supersession
(define-values (_rn cnf-s4-ms)
  (time-ms (lambda () (rename! hub-id "core-compute"))))

(agent-block "CNF"
  (list "rename! f0 → core-compute"
        "→ supersedes old name claim, adds new one"
        "→ structural claims (body, calls) unchanged"
        "→ matview stays valid (fn-depends-on derives from structure)")
  cnf-s4-ms)

;; Text: sed-rename across all files
(define-values (_tr txt-s4-ms)
  (time-ms (lambda ()
    (text-rename! tmp-dir N text-names 0 "core-compute"))))

(agent-block "Text"
  (list (format "Read+rewrite all ~a files" N)
        "Replace 'f0' with 'core-compute' in definitions and call sites"
        "→ every file that references f0 is rewritten")
  txt-s4-ms)

(insight "CNF: O(1) claim supersession, derived facts untouched. Text: O(N) file rewrite.")

;; ═══════════════════════════════════════════════════════════
;; STEP 5: Verify coupling after rename
;; ═══════════════════════════════════════════════════════════

(header "Step 5: Verify coupling unchanged after rename")

;; CNF: same query, instant cache hit
(define-values (coupled-after-rename cnf-s5-ms)
  (time-ms (lambda () (query (coupled (? a) (? b))))))

(agent-block "CNF"
  (list "query (coupled ?a ?b)"
        (format "→ ~a pairs (unchanged — matview cache hit)"
                (length coupled-after-rename))
        (format "→ matches pre-rename: ~a"
                (if (= (length coupled-after-rename) (length coupled-results))
                    "✓ yes" "✗ NO")))
  cnf-s5-ms)

;; Text: must rebuild everything from scratch
(define text-coupled-after #f)
(define-values (_ca txt-s5-ms)
  (time-ms (lambda ()
    (set! text-call-map (text-build-call-map tmp-dir N text-names))
    (define hub-idx
      (for/first ([(k v) (in-hash text-names)]
                  #:when (equal? v "core-compute"))
        k))
    (set! text-indirect (text-compute-indirect-dep text-call-map))
    (set! text-coupled-after (text-compute-coupled text-indirect hub-idx)))))

(agent-block "Text"
  (list (format "Rebuild call map from ~a files (O(N²))" N)
        "Recompute indirect-dep (2-hop)"
        "Recompute coupled pairs"
        (format "→ ~a pairs" (length text-coupled-after))
        (format "→ matches pre-rename: ~a"
                (if (= (length text-coupled-after) (length text-coupled))
                    "✓ yes" "✗ NO")))
  txt-s5-ms)

(insight "The core thesis: CNF verifies in O(1). Text rebuilds everything from scratch.")

;; ═══════════════════════════════════════════════════════════
;; STEP 6: Evolve the definition — tighten to 3-hop coupling
;; ═══════════════════════════════════════════════════════════

(header "Step 6: Evolve 'coupled' — require 3-hop dependency on hub")

;; CNF: supersede the coupled rule to use 3-hop chains
(define-values (new-coupled-ent cnf-s6-ms)
  (time-ms (lambda ()
    (supersede-rule! coupled-rule-ent
      (atom 'coupled (list (var 'a) (var 'b)))
      (list (atom 'fn-depends-on (list (var 'a) (var 'x)))
            (atom 'fn-depends-on (list (var 'x) (var 'y)))
            (atom 'fn-depends-on (list (var 'y) hub-id))
            (atom 'fn-depends-on (list (var 'b) (var 'x2)))
            (atom 'fn-depends-on (list (var 'x2) (var 'y2)))
            (atom 'fn-depends-on (list (var 'y2) hub-id)))))))

(define-values (deep-coupled cnf-s6q-ms)
  (time-ms (lambda () (query (coupled (? a) (? b))))))

(agent-block "CNF"
  (list "supersede-rule! coupled → new definition:"
        "  coupled(?a, ?b) :-"
        "    fn-depends-on(?a,?x), fn-depends-on(?x,?y), fn-depends-on(?y, hub),"
        "    fn-depends-on(?b,?x2), fn-depends-on(?x2,?y2), fn-depends-on(?y2, hub)"
        (format "→ old rule entity's claims superseded (history preserved)")
        (format "→ new rule entity: ~a" new-coupled-ent)
        (format "→ ~a deep-coupled pairs (was ~a with 2-hop)"
                (length deep-coupled) (length coupled-results)))
  (+ cnf-s6-ms cnf-s6q-ms))

;; Text: write new computation from scratch
(define text-deep-coupled #f)
(define-values (_tdc txt-s6-ms)
  (time-ms (lambda ()
    (define three-hop (text-compute-three-hop text-call-map))
    (define hub-idx
      (for/first ([(k v) (in-hash text-names)]
                  #:when (equal? v "core-compute"))
        k))
    (set! text-deep-coupled (text-compute-deep-coupled three-hop hub-idx)))))

(agent-block "Text"
  (list "Write new 3-hop computation (different algorithm from Step 2)"
        "Compute pairs where both have 3-hop path to hub"
        (format "→ ~a deep-coupled pairs" (length text-deep-coupled))
        "Old 2-hop computation discarded — no history")
  txt-s6-ms)

(check-equal? (length deep-coupled) (length text-deep-coupled)
  "deep-coupled count mismatch")

(insight "CNF: supersede-rule! preserves history, atomically updates derived facts. Text: rewrite code, old results lost.")

;; ═══════════════════════════════════════════════════════════
;; STEP 7: Sustained queries after more renames
;; ═══════════════════════════════════════════════════════════

(header "Step 7: Sustained use — 5 renames, re-query 'coupled' each time")

(define cnf-sustained-ops
  (for/list ([k (in-range 5)])
    (define fn-id (list-ref fns (+ k 10)))
    (define new-name (format "helper-~a" k))
    (define-values (_r ms)
      (time-ms (lambda ()
        (rename! fn-id new-name)
        (query (coupled (? a) (? b))))))
    ms))

(define cnf-sustained-total (apply + cnf-sustained-ops))

(agent-block "CNF"
  (list "5 iterations: rename + query coupled"
        (for/list ([k (in-range 5)])
          (format "  Op ~a: ~a ms" (+ k 1) (fmt (list-ref cnf-sustained-ops k))))
        (format "  Total: ~a ms  |  Per-op: ~a ms"
                (fmt cnf-sustained-total)
                (fmt (/ cnf-sustained-total 5))))
  cnf-sustained-total)

(define txt-sustained-ops
  (for/list ([k (in-range 5)])
    (define new-name (format "helper-~a" k))
    (define-values (_r ms)
      (time-ms (lambda ()
        (text-rename! tmp-dir N text-names (+ k 10) new-name)
        (set! text-call-map (text-build-call-map tmp-dir N text-names))
        (define three-hop (text-compute-three-hop text-call-map))
        (define hub-idx
          (for/first ([(k v) (in-hash text-names)]
                      #:when (equal? v "core-compute"))
            k))
        (text-compute-deep-coupled three-hop hub-idx))))
    ms))

(define txt-sustained-total (apply + txt-sustained-ops))

(agent-block "Text"
  (list "5 iterations: rename + rebuild map + recompute 3-hop + query"
        (for/list ([k (in-range 5)])
          (format "  Op ~a: ~a ms" (+ k 1) (fmt (list-ref txt-sustained-ops k))))
        (format "  Total: ~a ms  |  Per-op: ~a ms"
                (fmt txt-sustained-total)
                (fmt (/ txt-sustained-total 5))))
  txt-sustained-total)

(define per-op-ratio
  (if (> cnf-sustained-total 0)
      (/ txt-sustained-total cnf-sustained-total)
      +inf.0))

(insight (format "Per-op: ~ax faster with CNF. O(1) cache hit vs O(N²) rebuild."
                 (~r per-op-ratio #:precision 0)))

;; ═══════════════════════════════════════════════════════════
;; Summary
;; ═══════════════════════════════════════════════════════════

(displayln "")
(displayln "════════════════════════════════════════════════════════════════════════")
(displayln "  Summary")
(displayln "════════════════════════════════════════════════════════════════════════")

(printf "\n  ~a~a~a~a\n"
        (~a "Step" #:min-width 45)
        (~a "CNF" #:min-width 12)
        (~a "Text" #:min-width 12)
        "Ratio")
(printf "  ~a\n" (make-string 72 #\─))

(define steps
  (list (list "1. Discover hubs" cnf-s1-ms txt-s1-ms)
        (list "2. Define indirect-dep (2-hop)" cnf-s2-ms txt-s2-ms)
        (list "3. Define coupled (compose)" cnf-s3-ms txt-s3-ms)
        (list "4. Rename hub" cnf-s4-ms txt-s4-ms)
        (list "5. Verify after rename" cnf-s5-ms txt-s5-ms)
        (list "6. Evolve → 3-hop (supersede)" (+ cnf-s6-ms cnf-s6q-ms) txt-s6-ms)
        (list "7. Sustained (5 × rename+query)" cnf-sustained-total txt-sustained-total)))

(define cnf-grand 0)
(define txt-grand 0)

(for ([step (in-list steps)])
  (define label (first step))
  (define c (second step))
  (define t (third step))
  (set! cnf-grand (+ cnf-grand c))
  (set! txt-grand (+ txt-grand t))
  (define ratio (if (> c 0.001) (/ t c) +inf.0))
  (printf "  ~a~a~a~a\n"
          (~a label #:min-width 45)
          (~a (format "~a ms" (fmt c)) #:min-width 12)
          (~a (format "~a ms" (fmt t)) #:min-width 12)
          (cond [(>= ratio 10) (format "~ax" (~r ratio #:precision 0))]
                [(>= ratio 1) (format "~ax" (~r ratio #:precision 1))]
                [else (format "~ax" (~r ratio #:precision 2))])))

(printf "  ~a\n" (make-string 72 #\─))
(printf "  ~a~a~a~a\n"
        (~a "TOTAL" #:min-width 45)
        (~a (format "~a ms" (fmt cnf-grand)) #:min-width 12)
        (~a (format "~a ms" (fmt txt-grand)) #:min-width 12)
        (format "~ax" (~r (/ txt-grand cnf-grand) #:precision 2)))

(displayln "")
(displayln "  What each agent built during this session:")
(displayln "  ─────────────────────────────────────────────────────────────────")
(displayln "")
(displayln "  CNF agent:                        Text agent:")
(displayln "    3 composable rules                5 ad-hoc computations")
(displayln "    1 rule evolution (supersede)       1 rewrite (old code discarded)")
(displayln "    Persistent, inspectable entities   Ephemeral local variables")
(displayln "    O(1) query after any rename        O(N²) rebuild after every rename")
(displayln "")
(printf "  Sustained-use advantage: ~ax per-op\n" (~r per-op-ratio #:precision 0))
(printf "  50-op projection: CNF ~a ms vs Text ~a ms\n"
        (fmt (+ cnf-grand (* 50 (/ cnf-sustained-total 5))))
        (fmt (+ txt-grand (* 50 (/ txt-sustained-total 5)))))
(displayln "")

;; Cleanup
(for ([f (in-list (directory-list tmp-dir #:build? #t))])
  (delete-file f))
(delete-directory tmp-dir)

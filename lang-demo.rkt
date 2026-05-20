#lang racket

(require cnf cnf/lang)

;; Code as Claim Graph, Text as Projection
;;
;; A program IS the claim graph. Text is one projection.
;; Rename by claim. Edit by supersession. Query dependencies
;; from the substrate itself. History is free.

(define (section title)
  (printf "\n~a\n~a\n" title (make-string (string-length title) #\=)))

(define (subsection title)
  (printf "\n  ~a\n" title))

(define (indent s)
  (string-join
   (map (lambda (line) (string-append "    " line))
        (string-split s "\n"))
   "\n"))

;; ============================================================
;; Setup
;; ============================================================

(reset-store!)
(setup-eval!)
(setup-graph!)
(setup-lang!)

(displayln "")
(displayln "================================================================")
(displayln "    Code as Claim Graph, Text as Projection")
(displayln "================================================================")

;; ============================================================
;; Part 1: Parse -> Render round-trip
;; ============================================================

(section "Part 1: Source -> Claims -> Source")

(define source
  (string-join
   (list "(defn base-rate [hours level]\n  (* hours level))"
         "(defn overtime [hours level]\n  (* (base-rate hours level) 2))"
         "(defn total-pay [hours level]\n  (+ (base-rate hours level) (overtime hours level)))")
   "\n\n"))

(subsection "Source code:")
(displayln (indent source))

(define fns (parse-program! source))

(define total-objects (length (all-objects)))
(define total-claims (length (claims-where)))

(printf "\n  Parsed into ~a objects and ~a claims.\n" total-objects total-claims)

(subsection "Rendered back from claims:")
(define rendered (render-program fns))
(displayln (indent rendered))

(if (equal? rendered source)
    (printf "\n  Round-trip verified: source -> claims -> source.\n")
    (begin
      (printf "\n  Round-trip MISMATCH.\n")
      (printf "  Expected:\n~a\n" (indent source))
      (printf "  Got:\n~a\n" (indent rendered))))

;; ============================================================
;; Part 2: Rename
;; ============================================================

(section "Part 2: Rename — One Claim, Zero Find-Replace")

(define base-rate-fn (first fns))
(define overtime-fn (second fns))
(define total-pay-fn (third fns))

(subsection "Rename base-rate -> hourly-rate:")
(printf "    1 new name claim. 0 references changed.\n")
(void (rename! base-rate-fn "hourly-rate"))

(subsection "Rendered program:")
(displayln (indent (render-program fns)))

(printf "\n  Both call sites updated — no find-replace, no files searched.\n")
(printf "  The identity didn't change. Only the name claim.\n")

;; ============================================================
;; Part 3: Dependencies
;; ============================================================

(section "Part 3: Structural Dependencies (Datalog)")

(subsection "Query: fn-depends-on")
(define deps (query (fn-depends-on (? caller) (? callee))))
(for ([d (in-list deps)])
  (printf "    ~a  depends on  ~a\n"
          (render-ref (hash-ref d 'caller))
          (render-ref (hash-ref d 'callee))))

(printf "\n  Derived from graph structure — not declared, not grep'd.\n")

;; ============================================================
;; Part 4: Edit by supersession
;; ============================================================

(section "Part 4: Edit by Supersession")

(define body-id (get-body base-rate-fn))
(define builtins (ctx-ref 'builtins))
(define mul-op (hash-ref builtins '*))
(define add-op (hash-ref builtins '+))

(subsection "Change hourly-rate body: * -> +")
(printf "    1 op claim superseded. 1 new op claim.\n")
(void (change-operand! body-id (op-pred) mul-op add-op))

(subsection "Rendered program:")
(displayln (indent (render-program fns)))

(printf "\n  Only the hourly-rate body changed. Everything else untouched.\n")

;; ============================================================
;; Part 5: Provenance
;; ============================================================

(section "Part 5: Provenance — History is Free")

(subsection "Names of hourly-rate (all claims, including superseded):")
(define all-name-claims (claims-where #:l base-rate-fn #:p (name-pred)))
(for ([c (in-list all-name-claims)])
  (define val (resolve-value (list-ref c 3)))
  (define status
    (if (equal? val (current-name base-rate-fn)) "(current)" "(superseded)"))
  (printf "    ~s ~a\n" val status))

(subsection "Operators in hourly-rate body (all claims):")
(define all-op-claims (claims-where #:l body-id #:p (op-pred)))
(define current-ops (current-claims-where #:l body-id #:p (op-pred)))
(for ([c (in-list all-op-claims)])
  (define op-entity (list-ref c 3))
  (define op-name (render-ref op-entity))
  (define is-current?
    (ormap (lambda (cc) (equal? (first cc) (first c))) current-ops))
  (printf "    ~a ~a\n" op-name (if is-current? "(current)" "(superseded)")))

(printf "\n  Old claims are not deleted — they're superseded.\n")
(printf "  Every change is a claim about a claim. Full audit trail.\n")

;; ============================================================
;; Part 6: Graph-first — build a function from claims, render as text
;; ============================================================

(section "Part 6: Graph -> Text (no parsing involved)")

(subsection "Building a new function from claims alone...")

(define double-fn (entity!))
(void (give-name! double-fn "double-pay"))

(define dp-hours (entity!))
(void (give-name! dp-hours "hours"))
(void (claim! dp-hours (position-pred) (value! 0)))
(void (claim! double-fn (has-param-pred) dp-hours))

(define dp-level (entity!))
(void (give-name! dp-level "level"))
(void (claim! dp-level (position-pred) (value! 1)))
(void (claim! double-fn (has-param-pred) dp-level))

(define tp-call (entity!))
(void (claim! tp-call (calls-pred) total-pay-fn))
(void (claim! tp-call (left-pred) dp-hours))
(void (claim! tp-call (right-pred) dp-level))
(define dp-body (expr! mul-op tp-call (value! 2)))
(void (claim! double-fn (body-pred) dp-body))

(subsection "New function (never existed as text):")
(displayln (indent (render-fn double-fn)))

(subsection "Full program — 4 functions, 1 built from claims alone:")
(displayln (indent (render-program (append fns (list double-fn)))))

(subsection "Updated dependencies:")
(define deps2 (query (fn-depends-on (? caller) (? callee))))
(for ([d (in-list deps2)])
  (printf "    ~a  depends on  ~a\n"
          (render-ref (hash-ref d 'caller))
          (render-ref (hash-ref d 'callee))))

(printf "\n  The graph is the program. Text is one of its projections.\n")

;; ============================================================
;; The point
;; ============================================================

(section "The Point")
(printf "
  Text code:
    Rename:       find-replace across N files
    Dependencies: grep or language server (derived cache, can go stale)
    Edit:         modify text, re-parse, hope nothing broke
    History:      git diff (coarse-grained, per-file)

  Claim graph:
    Rename:       1 claim (identity is stable, name is projection)
    Dependencies: Datalog query on the substrate itself
    Edit:         supersede a claim (old structure preserved)
    History:      query superseded claims (fine-grained, per-fact)

  > A program is a graph of claims.
  > Text is one of its projections.
  > Rename is a claim, not find-replace.
  > Every edit has provenance.
")

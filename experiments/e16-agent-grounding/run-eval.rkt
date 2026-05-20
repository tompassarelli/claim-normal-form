#lang racket

(require "../../cnf.rkt" "../../datalog.rkt" "../../eval.rkt"
         "../../graph.rkt" "../../python-lang.rkt")

;; E16 automated evaluation: CNF answers vs ground truth

(printf "=== E16: Agent Grounding Evaluation — CNF Side ===\n\n")

(reset-store!)
(setup-eval!)
(setup-graph!)
(setup-python-lang!)

;; Parse all modules
(define all-fns '())
(for ([mod '("pricing.py" "validation.py" "processing.py" "reporting.py")])
  (define fns (parse-python-program! (file->string (build-path "codebase" mod))))
  (set! all-fns (append all-fns fns)))
(printf "Parsed ~a forms, ~a objects, ~a claims\n\n"
        (length all-fns) (length (all-objects)) (length (current-claims-where)))

;; Rules + materialize
(define-rule (py-trans-dep (? f) (? g))
  (py-fn-depends-on (? f) (? g)))
(define-rule (py-trans-dep (? f) (? g))
  (py-fn-depends-on (? f) (? m))
  (py-trans-dep (? m) (? g)))
(materialize!)

(define all-deps (query (py-fn-depends-on (? caller) (? callee))))
(define all-trans (query (py-trans-dep (? f) (? g))))

;; Helpers
(define (callers-of fn-name)
  (sort (for/list ([d all-deps]
                   #:when (equal? (render-ref (hash-ref d 'callee)) fn-name))
          (render-ref (hash-ref d 'caller))) string<?))

(define (trans-callers-of fn-name)
  (sort (for/list ([d all-trans]
                   #:when (equal? (render-ref (hash-ref d 'g)) fn-name))
          (render-ref (hash-ref d 'f))) string<?))

(define (trans-deps-of fn-name)
  (sort (for/list ([d all-trans]
                   #:when (equal? (render-ref (hash-ref d 'f)) fn-name))
          (render-ref (hash-ref d 'g))) string<?))

(define (direct-deps-of fn-name)
  (sort (for/list ([d all-deps]
                   #:when (equal? (render-ref (hash-ref d 'caller)) fn-name))
          (render-ref (hash-ref d 'callee))) string<?))

(define fn-names
  (for/list ([fn all-fns]
             #:when (let ([fk (current-claims-where #:l fn #:p (py-form-kind-pred))])
                      (and (not (null? fk))
                           (equal? (resolve-value (list-ref (first fk) 3)) "function"))))
    (render-ref fn)))

(define called-names
  (remove-duplicates (for/list ([d all-deps]) (render-ref (hash-ref d 'callee)))))

(define uncalled (sort (remove* called-names fn-names) string<?))


;; ================================================================
;; TASK 01: Rename subtotal — which call sites change?
;; ================================================================
(printf "━━━ TASK 01: Rename subtotal ━━━\n")
(define sub-callers (callers-of "subtotal"))
(printf "CNF: ~a call sites: ~a\n" (length sub-callers) sub-callers)
(printf "     These are entity references — only function calls, not dict keys.\n\n")

;; ================================================================
;; TASK 02: Blast radius of round_cents
;; ================================================================
(printf "━━━ TASK 02: Blast radius of round_cents ━━━\n")
(define rc-direct (callers-of "round_cents"))
(define rc-trans (trans-callers-of "round_cents"))
(define rc-indirect (sort (remove* rc-direct rc-trans) string<?))
(printf "CNF direct callers (~a): ~a\n" (length rc-direct) rc-direct)
(printf "CNF total affected (~a): ~a\n" (length rc-trans) rc-trans)
(printf "     Indirect only (~a): ~a\n\n" (length rc-indirect) rc-indirect)

;; ================================================================
;; TASK 03: Which functions shadow domain names?
;; ================================================================
(printf "━━━ TASK 03: Shadowed names ━━━\n")
(for ([short '("process" "total" "summary" "validate")])
  (define callers (callers-of short))
  (printf "  ~a() callers: ~a\n" short (if (null? callers) "(none — dead code)" callers)))
(printf "\n")

;; ================================================================
;; TASK 04: Dead code
;; ================================================================
(printf "━━━ TASK 04: Dead code (no callers) ━━━\n")
(printf "CNF uncalled (~a): ~a\n" (length uncalled) uncalled)
(define entry-points '("process_order" "process_batch" "full_report"
                       "revenue_report" "is_valid_order"))
(define dead (sort (remove* entry-points uncalled) string<?))
(printf "Excluding entry points, dead code (~a): ~a\n\n" (length dead) dead)

;; ================================================================
;; TASK 08: full_report dependency tree
;; ================================================================
(printf "━━━ TASK 08: full_report dependency tree ━━━\n")
(define fr-direct (direct-deps-of "full_report"))
(define fr-trans (trans-deps-of "full_report"))
(define fr-indirect (sort (remove* fr-direct fr-trans) string<?))
(printf "CNF direct calls (~a): ~a\n" (length fr-direct) fr-direct)
(printf "CNF full tree (~a): ~a\n" (length fr-trans) fr-trans)
(printf "     Depth 2+ (~a): ~a\n\n" (length fr-indirect) fr-indirect)

;; ================================================================
;; TASK 09: Rename order_total — what changes?
;; ================================================================
(printf "━━━ TASK 09: Rename order_total ━━━\n")
(define ot-callers (callers-of "order_total"))
(printf "CNF: ~a call sites: ~a\n" (length ot-callers) ot-callers)
(printf "     Entity references only — processing.total() is a different entity.\n\n")

;; ================================================================
;; TASK 10: Cross-session rename
;; ================================================================
(printf "━━━ TASK 10: Cross-session — rename round_cents ━━━\n")
(define rc-fn (findf (lambda (f) (equal? (render-ref f) "round_cents")) all-fns))
(when rc-fn
  (void (rename! rc-fn "truncate_cents"))
  (printf "Renamed round_cents -> truncate_cents\n")
  (define post-callers (callers-of "truncate_cents"))
  (printf "Callers now reference truncate_cents (~a): ~a\n"
          (length post-callers) post-callers)
  (printf "Zero grep needed — entity references auto-updated.\n\n"))

(printf "=== CNF evaluation complete ===\n")

#lang racket

;; Spike 2: Trace config constant references back to containing functions.
;; Uses py-fn-references Datalog rule (function→variable dependency).

(require cnf cnf/python)

(define codebase-dir
  (path->string
   (build-path (current-directory) "experiments/f7-graph-necessity/codebase")))

(define py-files
  '("models.py" "config.py" "store.py" "events.py" "workflow.py"
    "validation.py" "tickets.py" "permissions.py" "audit.py"
    "notifications.py" "assignment.py" "sla.py" "comments.py"
    "search.py" "tags.py" "teams.py" "reports.py" "imports_exports.py"))

(define ctx (make-cnf-ctx))
(parameterize ([current-ctx ctx])
  (setup-graph!)
  (setup-python-lang!)

  ;; Parse all files, track which file each entity came from
  (define entity-to-file (make-hash))
  (define all-entities '())

  (for ([f (in-list py-files)])
    (define path (build-path codebase-dir f))
    (with-handlers ([exn:fail?
                     (lambda (e)
                       (printf "FAILED ~a: ~a\n" f (exn-message e)))])
      (define entities (parse-python-file! (path->string path)))
      (for ([e (in-list entities)])
        (hash-set! entity-to-file e f))
      (set! all-entities (append all-entities entities))))

  (printf "Parsed ~a entities from ~a files.\n\n" (length all-entities) (length py-files))

  ;; Helper: get entity name
  (define (ename e)
    (define cs (current-claims-where #:l e #:p (name-pred)))
    (if (null? cs) (format "#~a" e)
        (resolve-value (list-ref (first cs) 3))))

  ;; --- Compute all derived relations ---

  (printf "Computing Datalog fixpoint...\n")
  (flush-output)

  (define fn-deps (query (py-fn-depends-on (? caller) (? callee))))
  (define fn-refs (query (py-fn-references (? fn) (? var))))
  (printf "  Function→function edges: ~a\n" (length fn-deps))
  (printf "  Function→variable edges: ~a\n\n" (length fn-refs))

  ;; --- Variable references ---

  (printf "=== Functions referencing critical constants ===\n\n")
  (for ([const-name (in-list '("TERMINAL_STATUSES" "ACTIVE_STATUSES"
                                "STATUSES" "VALID_TRANSITIONS"
                                "STATUS_TRANSITIONS" "HOOKS"
                                "KNOWN_EVENTS" "ROLE_PERMISSIONS"
                                "DEFAULT_SLA" "PRIORITIES"))])
    (define var-id (resolve-symbol const-name))
    (printf "~a:" const-name)
    (cond
      [var-id
       (define referrers
         (filter (lambda (r) (equal? (hash-ref r 'var) var-id)) fn-refs))
       (for ([r (in-list referrers)])
         (define fn-id (hash-ref r 'fn))
         (printf " ~a(~a)" (ename fn-id) (hash-ref entity-to-file fn-id "?")))
       (printf " [~a]\n" (length referrers))]
      [else
       (printf " NOT FOUND\n")]))

  ;; --- Function call chains ---

  (printf "\n=== Callers of key workflow functions ===\n\n")
  (for ([fn-name (in-list '("transition_ticket" "_run_hooks" "emit"
                              "is_terminal" "is_active" "is_valid_transition"
                              "has_permission" "notify" "log_action"
                              "register_listener" "setup_hooks"))])
    (define fn-id (resolve-symbol fn-name))
    (cond
      [fn-id
       (define callers
         (filter (lambda (r) (equal? (hash-ref r 'callee) fn-id)) fn-deps))
       (printf "~a (~a):" fn-name (length callers))
       (for ([r (in-list callers)])
         (printf " ~a" (ename (hash-ref r 'caller))))
       (printf "\n")]
      [else
       (printf "~a: NOT FOUND\n" fn-name)]))

  ;; --- Transitive callers ---

  (printf "\n=== Transitive callers (2 hops) ===\n\n")
  (for ([fn-name (in-list '("is_terminal" "is_active"))])
    (define fn-id (resolve-symbol fn-name))
    (when fn-id
      (define direct
        (map (lambda (r) (hash-ref r 'caller))
             (filter (lambda (r) (equal? (hash-ref r 'callee) fn-id)) fn-deps)))
      (define indirect
        (for*/list ([d (in-list direct)]
                    [r (in-list fn-deps)]
                    #:when (equal? (hash-ref r 'callee) d))
          (hash-ref r 'caller)))
      (define all-callers (remove-duplicates (append direct indirect)))
      (printf "~a (direct + 1-hop, ~a):\n" fn-name (length all-callers))
      (for ([c (in-list all-callers)])
        (printf "  ~a  (~a)\n" (ename c) (hash-ref entity-to-file c "?")))
      (printf "\n")))

  ;; --- Impact zone ---

  (printf "=== Status change impact zone ===\n")
  (printf "(Functions referencing TERMINAL_STATUSES, ACTIVE_STATUSES, STATUSES,\n")
  (printf " VALID_TRANSITIONS, STATUS_TRANSITIONS, or calling is_terminal/\n")
  (printf " is_active/is_valid_transition)\n\n")

  (define impact-set (mutable-set))

  ;; Add direct variable references
  (for ([const-name (in-list '("TERMINAL_STATUSES" "ACTIVE_STATUSES"
                                "STATUSES" "VALID_TRANSITIONS"
                                "STATUS_TRANSITIONS"))])
    (define var-id (resolve-symbol const-name))
    (when var-id
      (for ([r (in-list fn-refs)])
        (when (equal? (hash-ref r 'var) var-id)
          (set-add! impact-set (hash-ref r 'fn))))))

  ;; Add callers of status helper functions
  (for ([fn-name (in-list '("is_terminal" "is_active" "is_valid_transition"))])
    (define fn-id (resolve-symbol fn-name))
    (when fn-id
      (set-add! impact-set fn-id)
      (for ([r (in-list fn-deps)])
        (when (equal? (hash-ref r 'callee) fn-id)
          (set-add! impact-set (hash-ref r 'caller))))))

  (printf "Total functions in impact zone: ~a\n\n" (set-count impact-set))
  (define by-file (make-hash))
  (for ([fn-id (in-set impact-set)])
    (define file (hash-ref entity-to-file fn-id "?"))
    (hash-update! by-file file (lambda (l) (cons (ename fn-id) l)) '()))

  (define sorted-files (sort (hash-keys by-file) string<?))
  (for ([file (in-list sorted-files)])
    (define fns (hash-ref by-file file '()))
    (printf "  ~a:\n" file)
    (for ([fn (in-list (sort fns string<?))])
      (printf "    ~a\n" fn)))

  ;; --- Top-level variables discovered ---

  (printf "\n=== Module-level variables ===\n")
  (for ([e (in-list all-entities)])
    (define fk-claims (current-claims-where #:l e #:p (py-form-kind-pred)))
    (define kind (and (not (null? fk-claims))
                      (resolve-value (list-ref (first fk-claims) 3))))
    (when (equal? kind "variable")
      (define file (hash-ref entity-to-file e "?"))
      (printf "  ~a  (~a)\n" (ename e) file)))

  ;; --- Graph summary ---

  (define all-claims (current-claims-where))
  (printf "\n=== Summary ===\n")
  (printf "  Files: ~a\n" (length py-files))
  (printf "  Total entities: ~a\n" (length all-entities))
  (printf "  Total claims: ~a\n" (length all-claims))
  (printf "  fn→fn edges: ~a\n" (length fn-deps))
  (printf "  fn→var edges: ~a\n" (length fn-refs))
  (printf "  Impact zone: ~a functions\n" (set-count impact-set))

  (printf "\n=== Spike 2 complete ===\n"))

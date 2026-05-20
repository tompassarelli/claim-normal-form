#lang racket

;; Bridge validation spike for F7.
;; Parse all 18 Python modules, run structural queries,
;; report what the graph can and cannot answer.

(require cnf cnf/python)

(define codebase-dir
  (path->string
   (build-path (current-directory) "experiments/f7-graph-necessity/codebase")))

(define py-files
  '("models.py" "config.py" "store.py" "events.py" "workflow.py"
    "validation.py" "tickets.py" "permissions.py" "audit.py"
    "notifications.py" "assignment.py" "sla.py" "comments.py"
    "search.py" "tags.py" "teams.py" "reports.py" "imports_exports.py"))

(printf "=== CNF Bridge Validation Spike ===\n\n")

(define ctx (make-cnf-ctx))
(parameterize ([current-ctx ctx])
  (setup-graph!)
  (setup-python-lang!)

  ;; --- Parse all files ---

  (printf "--- Parsing ~a files ---\n" (length py-files))
  (define all-entities '())
  (define file-entity-map (make-hash))

  (for ([f (in-list py-files)])
    (define path (build-path codebase-dir f))
    (printf "  ~a ... " f)
    (flush-output)
    (with-handlers ([exn:fail?
                     (lambda (e)
                       (printf "FAILED: ~a\n" (exn-message e)))])
      (define entities (parse-python-file! (path->string path)))
      (printf "~a entities\n" (length entities))
      (set! all-entities (append all-entities entities))
      (hash-set! file-entity-map f entities)))

  (printf "\nTotal top-level entities: ~a\n\n" (length all-entities))

  ;; --- Helper: entity name lookup ---

  (define (entity-name e)
    (define cs (current-claims-where #:l e #:p (name-pred)))
    (if (null? cs) (format "#~a" e)
        (resolve-value (list-ref (first cs) 3))))

  (define (entity-kind e)
    (define cs (current-claims-where #:l e #:p (py-form-kind-pred)))
    (if (null? cs) "?" (resolve-value (list-ref (first cs) 3))))

  ;; --- Catalog ---

  (printf "--- Top-level entities by file ---\n")
  (define fn-count 0)
  (define class-count 0)
  (for ([(f entities) (in-hash file-entity-map)])
    (printf "  ~a:\n" f)
    (for ([e (in-list entities)])
      (define kind (entity-kind e))
      (define name (entity-name e))
      (cond
        [(equal? kind "class")
         (set! class-count (add1 class-count))
         (printf "    [class] ~a\n" name)
         (define method-claims (current-claims-where #:l e #:p (py-has-method-pred)))
         (for ([mc (in-list method-claims)])
           (define mid (list-ref mc 3))
           (printf "      .~a\n" (entity-name mid)))]
        [else
         (set! fn-count (add1 fn-count))
         (printf "    [fn] ~a\n" name)])))

  (printf "\nFunctions: ~a, Classes: ~a\n\n" fn-count class-count)

  ;; --- Query 1: Function dependencies via Datalog ---

  (printf "--- Query: py-fn-depends-on ---\n")
  (flush-output)
  (define dep-results
    (query (py-fn-depends-on (? caller) (? callee))))
  (printf "  Total dependency edges: ~a\n" (length dep-results))
  (for ([r (in-list dep-results)])
    (define caller-id (hash-ref r 'caller))
    (define callee-id (hash-ref r 'callee))
    (printf "  ~a → ~a\n" (entity-name caller-id) (entity-name callee-id)))

  ;; --- Query 2: Callers of specific functions ---

  (printf "\n--- Callers of key functions ---\n")
  (for ([fn-name (in-list '("_run_hooks" "emit" "transition_ticket"
                              "register_listener" "create_ticket"
                              "close_ticket" "check_permission"))])
    (define fn-id (resolve-symbol fn-name))
    (cond
      [fn-id
       (define callers
         (filter (lambda (r) (equal? (hash-ref r 'callee) fn-id)) dep-results))
       (printf "  ~a (~a callers):" fn-name (length callers))
       (for ([r (in-list callers)])
         (printf " ~a" (entity-name (hash-ref r 'caller))))
       (printf "\n")]
      [else
       (printf "  ~a: NOT FOUND as entity\n" fn-name)]))

  ;; --- Query 3: py-calls-pred to config constants ---

  (printf "\n--- References to config constants (via py-calls-pred) ---\n")
  (for ([name (in-list '("TERMINAL_STATUSES" "ACTIVE_STATUSES" "STATUSES"
                          "ROLE_PERMISSIONS" "HOOKS" "STATUS_TRANSITIONS"
                          "VALID_TRANSITIONS" "DEFAULT_SLA"
                          "PRIORITIES" "PRIORITY_WEIGHTS" "SOURCES"
                          "KNOWN_EVENTS" "MAX_TAGS_PER_TICKET"))])
    (define vid (value-id name))
    (cond
      [vid
       (define refs (current-claims-where #:p (py-calls-pred) #:r vid))
       (printf "  ~a: ~a call-refs" name (length refs))
       (when (> (length refs) 0)
         (define parent-fns
           (for/list ([r (in-list refs)])
             (define expr-id (list-ref r 2))
             ;; Walk up to find the function
             expr-id))
         (printf " (from ~a expressions)" (length refs)))
       (printf "\n")]
      [else
       (printf "  ~a: not in value store\n" name)]))

  ;; --- Query 4: Functions with 'status' parameter ---

  (printf "\n--- Functions with 'status' parameter ---\n")
  (define status-val-id (value-id "status"))
  (when status-val-id
    (define name-claims (current-claims-where #:p (name-pred) #:r status-val-id))
    (for ([c (in-list name-claims)])
      (define param-id (list-ref c 2))
      (define parent-claims (current-claims-where #:p (py-has-param-pred) #:r param-id))
      (for ([pc (in-list parent-claims)])
        (define fn-id (list-ref pc 2))
        (printf "  ~a\n" (entity-name fn-id)))))

  ;; --- Query 5: py-contains-call to TERMINAL_STATUSES ---

  (printf "\n--- py-contains-call to TERMINAL_STATUSES ---\n")
  (flush-output)
  (define ts-vid (value-id "TERMINAL_STATUSES"))
  (cond
    [ts-vid
     (printf "  Value ID found: ~a\n" ts-vid)
     (define results
       (run-query (list (atom 'py-contains-call (list (var 'expr) ts-vid)))))
     (printf "  Expressions referencing TERMINAL_STATUSES: ~a\n" (length results))]
    [else
     (printf "  TERMINAL_STATUSES not in value store\n")])

  ;; --- Query 6: py-contains-call to ACTIVE_STATUSES ---

  (printf "\n--- py-contains-call to ACTIVE_STATUSES ---\n")
  (flush-output)
  (define as-vid (value-id "ACTIVE_STATUSES"))
  (cond
    [as-vid
     (define results
       (run-query (list (atom 'py-contains-call (list (var 'expr) as-vid)))))
     (printf "  Expressions referencing ACTIVE_STATUSES: ~a\n" (length results))]
    [else
     (printf "  ACTIVE_STATUSES not in value store\n")])

  ;; --- Query 7: Decorators ---

  (printf "\n--- Decorated functions ---\n")
  (for ([e (in-list all-entities)])
    (define dec-claims (current-claims-where #:l e #:p (py-has-decorator-pred)))
    (when (not (null? dec-claims))
      (define decs (map (lambda (c) (resolve-value (list-ref c 3))) dec-claims))
      (printf "  ~a: ~a\n" (entity-name e) decs)))

  ;; --- Summary ---

  (printf "\n--- Graph summary ---\n")
  (define all-claims (current-claims-where))
  (printf "  Total claims: ~a\n" (length all-claims))
  (printf "  Total dependency edges: ~a\n" (length dep-results))
  (printf "  Top-level entities: ~a (~a functions, ~a classes)\n"
          (length all-entities) fn-count class-count)

  (printf "\n=== Spike complete ===\n"))

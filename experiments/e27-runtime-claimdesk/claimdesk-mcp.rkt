#lang racket

(require json racket/cmdline
         "claimdesk.rkt"
         "../../cnf-lib/private/kernel.rkt"
         "../../cnf-lib/private/datalog.rkt"
         "../../cnf-lib/private/schema.rkt")

;; MCP server for ClaimDesk domain operations.
;; Speaks JSON-RPC 2.0 over stdio (line-delimited).
;; Usage: racket claimdesk-mcp.rkt [--output-dir DIR] [--mode label|validated|properties]

(define output-dir (box #f))
(define server-mode (box "label"))

(command-line
 #:once-each
 [("--output-dir") dir "Directory for projected Python output"
  (set-box! output-dir dir)]
 [("--mode") mode "Status interface mode: label, validated, or properties"
  (unless (member mode '("label" "validated" "properties"))
    (error 'claimdesk-mcp "invalid mode: ~a" mode))
  (set-box! server-mode mode)]
 #:args () (void))

;; ── Transport ────────────────────────────────────────────────

(define mcp-out (current-output-port))
(current-output-port (current-error-port))

(define (send-response msg)
  (write-json msg mcp-out)
  (write-char #\newline mcp-out)
  (flush-output mcp-out))

(define (read-message)
  (define line (read-line (current-input-port) 'any))
  (cond
    [(eof-object? line) #f]
    [(string=? line "") (read-message)]
    [else (string->jsexpr line)]))

;; ── Tool definitions ─────────────────────────────────────────

(define (make-add-status-tool)
  (case (unbox server-mode)
    [("label")
     (hasheq 'name "add_status"
             'description "Add a new status to the domain. Group must be 'active', 'terminal', or 'blocked'."
             'inputSchema (hasheq 'type "object"
                                  'properties (hasheq
                                               'name (hasheq 'type "string"
                                                             'description "Status name (e.g. 'suspended', 'escalated')")
                                               'group (hasheq 'type "string"
                                                              'enum '("active" "terminal" "blocked")
                                                              'description "Status group: 'active', 'terminal', or 'blocked'"))
                                  'required '("name" "group")))]
    [("validated")
     (hasheq 'name "add_status"
             'description "Add a new status. You must specify the group AND declare semantic properties. The system validates that your group choice is consistent with the declared properties. If there is a contradiction, the system rejects and explains why."
             'inputSchema (hasheq 'type "object"
                                  'properties (hasheq
                                               'name (hasheq 'type "string"
                                                             'description "Status name")
                                               'group (hasheq 'type "string"
                                                              'enum '("active" "terminal" "blocked")
                                                              'description "Proposed group")
                                               'counts_as_work (hasheq 'type "boolean"
                                                                       'description "Does this status count as active workload? (true for statuses where work is happening)")
                                               'terminal (hasheq 'type "boolean"
                                                                  'description "Is this a final/closed state that tickets don't come back from?"))
                                  'required '("name" "group" "counts_as_work" "terminal")))]
    [("properties")
     (hasheq 'name "add_status"
             'description "Add a new status. Declare its semantic properties — the system derives the correct structural group automatically. Do NOT choose a group yourself. Just describe what the status means."
             'inputSchema (hasheq 'type "object"
                                  'properties (hasheq
                                               'name (hasheq 'type "string"
                                                             'description "Status name")
                                               'counts_as_work (hasheq 'type "boolean"
                                                                       'description "Does this status count as active workload? (true for statuses where work is happening)")
                                               'terminal (hasheq 'type "boolean"
                                                                  'description "Is this a final/closed state that tickets don't come back from?"))
                                  'required '("name" "counts_as_work" "terminal")))]))

(define tool-defs
  (list
   (hasheq 'name "list_statuses"
           'description "List all statuses with their groups (active/terminal). Shows the current state machine."
           'inputSchema (hasheq 'type "object" 'properties (hasheq)))

   (hasheq 'name "list_transitions"
           'description "List all valid status transitions. Shows which statuses can transition to which."
           'inputSchema (hasheq 'type "object" 'properties (hasheq)))

   (hasheq 'name "list_roles"
           'description "List all defined roles."
           'inputSchema (hasheq 'type "object" 'properties (hasheq)))

   (hasheq 'name "list_permissions"
           'description "List all permission rules (action → required roles)."
           'inputSchema (hasheq 'type "object" 'properties (hasheq)))

   (hasheq 'name "list_effects"
           'description "List all effect declarations (trigger, kind, condition)."
           'inputSchema (hasheq 'type "object" 'properties (hasheq)))

   (make-add-status-tool)

   (hasheq 'name "add_transition"
           'description "Add a transition rule between two statuses. Both statuses must already exist."
           'inputSchema (hasheq 'type "object"
                                'properties (hasheq
                                             'from (hasheq 'type "string" 'description "Source status name")
                                             'to (hasheq 'type "string" 'description "Target status name"))
                                'required '("from" "to")))

   (hasheq 'name "add_role"
           'description "Add a new role to the domain."
           'inputSchema (hasheq 'type "object"
                                'properties (hasheq
                                             'name (hasheq 'type "string" 'description "Role name"))
                                'required '("name")))

   (hasheq 'name "add_permission"
           'description "Add a permission rule: action requires a specific role."
           'inputSchema (hasheq 'type "object"
                                'properties (hasheq
                                             'action (hasheq 'type "string" 'description "Action name (e.g. 'archive', 'manage')")
                                             'role (hasheq 'type "string" 'description "Required role name"))
                                'required '("action" "role")))

   (hasheq 'name "add_effect"
           'description "Add an effect declaration. Trigger: when it fires. Kind: what happens. Condition: constraints."
           'inputSchema (hasheq 'type "object"
                                'properties (hasheq
                                             'trigger (hasheq 'type "string" 'description "When it fires (e.g. 'transition', 'create')")
                                             'kind (hasheq 'type "string" 'description "What happens (e.g. 'notification', 'analytics')")
                                             'condition (hasheq 'type "string" 'description "Constraint (e.g. 'not-terminal', 'always')"))
                                'required '("trigger" "kind" "condition")))

   (hasheq 'name "check_obligations"
           'description "Check for structural obligation violations in a module. Returns issues that must be addressed."
           'inputSchema (hasheq 'type "object"
                                'properties (hasheq
                                             'module (hasheq 'type "string"
                                                             'description "Module to check (e.g. 'notifications', 'permissions', 'analytics')"))
                                'required '("module")))

   (hasheq 'name "project_module"
           'description "Project a Python module from the current claim graph. Returns the generated Python code."
           'inputSchema (hasheq 'type "object"
                                'properties (hasheq
                                             'module (hasheq 'type "string"
                                                             'description "Module to project: 'workflow', 'permissions', 'notifications', 'analytics'"))
                                'required '("module")))

   (hasheq 'name "project_all_to_disk"
           'description "Project all modules (workflow, permissions, notifications, analytics) to the output directory as Python files. Call this LAST, after all changes are made."
           'inputSchema (hasheq 'type "object" 'properties (hasheq)))

   (hasheq 'name "query_domain"
           'description "Query derived facts: terminal statuses, active statuses, all statuses, or transition validity."
           'inputSchema (hasheq 'type "object"
                                'properties (hasheq
                                             'query (hasheq 'type "string"
                                                            'description "Query type: 'terminal', 'active', 'all', 'can_transition'")
                                             'from_status (hasheq 'type "string"
                                                                  'description "For can_transition: current status name")
                                             'to_status (hasheq 'type "string"
                                                                'description "For can_transition: target status name"))
                                'required '("query")))))

;; ── Tool handlers ────────────────────────────────────────────

(define (format-status-list statuses group)
  (for/list ([s (in-list statuses)])
    (hasheq 'name s 'group group)))

(define (handle-tool name arguments)
  (case name
    [("list_statuses")
     (define terms (terminal-statuses))
     (define acts (active-statuses))
     (define blk (blocked-statuses))
     (define result (hasheq 'terminal terms
                            'active acts
                            'total (+ (length terms) (length acts) (length blk))))
     (jsexpr->string
      (if (null? blk) result (hash-set result 'blocked blk)))]

    [("list_transitions")
     (define transitions (current-claims-where #:p transition-from))
     (define result '())
     (for ([t (in-list transitions)])
       (define t-ent (list-ref t 2))
       (define from-ent (list-ref t 3))
       (define to-ent (lookup t-ent transition-to))
       (define from-name (lookup from-ent status-name))
       (define to-name (and to-ent (lookup to-ent status-name)))
       (when (and from-name to-name)
         (set! result (cons (hasheq 'from from-name 'to to-name) result))))
     (jsexpr->string result)]

    [("list_roles")
     (define roles-cs (current-claims-where #:p role-name))
     (define names
       (for/list ([c (in-list roles-cs)])
         (resolve-value (list-ref c 3))))
     (jsexpr->string names)]

    [("list_permissions")
     (define perms (current-claims-where #:p permission-action))
     (define result '())
     (for ([p (in-list perms)])
       (define p-ent (list-ref p 2))
       (define action (resolve-value (list-ref p 3)))
       (define role-ent (lookup p-ent permission-requires-role))
       (define role (and role-ent (lookup role-ent role-name)))
       (when (and action role)
         (set! result (cons (hasheq 'action action 'role role) result))))
     (jsexpr->string result)]

    [("list_effects")
     (define effects (current-claims-where #:p effect-trigger))
     (define result '())
     (for ([e (in-list effects)])
       (define eff-ent (list-ref e 2))
       (define trigger (resolve-value (list-ref e 3)))
       (define kind (lookup eff-ent effect-kind))
       (define cond-val (lookup eff-ent effect-condition))
       (when (and trigger kind cond-val)
         (set! result (cons (hasheq 'trigger trigger 'kind kind 'condition cond-val) result))))
     (jsexpr->string result)]

    [("add_status")
     (define name-arg (hash-ref arguments 'name))
     (case (unbox server-mode)
       [("label")
        (define group-arg (hash-ref arguments 'group))
        (void (define-status! name-arg group-arg))
        (format "Status '~a' added (group: ~a). Terminal: ~a. Active: ~a. Blocked: ~a."
                name-arg group-arg (terminal-statuses) (active-statuses) (blocked-statuses))]
       [("validated")
        (define group-arg (hash-ref arguments 'group))
        (define props (hash "counts_as_work" (hash-ref arguments 'counts_as_work)
                            "terminal" (hash-ref arguments 'terminal)))
        (void (define-status-validated! name-arg group-arg props))
        (format "Status '~a' added (group: ~a, validated against properties). Terminal: ~a. Active: ~a. Blocked: ~a."
                name-arg group-arg (terminal-statuses) (active-statuses) (blocked-statuses))]
       [("properties")
        (define props (hash "counts_as_work" (hash-ref arguments 'counts_as_work)
                            "terminal" (hash-ref arguments 'terminal)))
        (define group (derive-group props))
        (unless group
          (error 'add_status "no group matches properties counts_as_work=~a, terminal=~a"
                 (hash-ref arguments 'counts_as_work) (hash-ref arguments 'terminal)))
        (void (define-status-from-properties! name-arg props))
        (format "Status '~a' added. Derived group: ~a (from counts_as_work=~a, terminal=~a). Terminal: ~a. Active: ~a. Blocked: ~a."
                name-arg group
                (hash-ref arguments 'counts_as_work) (hash-ref arguments 'terminal)
                (terminal-statuses) (active-statuses) (blocked-statuses))])]

    [("add_transition")
     (define from-arg (hash-ref arguments 'from))
     (define to-arg (hash-ref arguments 'to))
     (void (define-transition! from-arg to-arg))
     (format "Transition ~a → ~a added." from-arg to-arg)]

    [("add_role")
     (define name-arg (hash-ref arguments 'name))
     (void (define-role! name-arg))
     (format "Role '~a' added." name-arg)]

    [("add_permission")
     (define action-arg (hash-ref arguments 'action))
     (define role-arg (hash-ref arguments 'role))
     (void (define-permission! action-arg role-arg))
     (format "Permission: '~a' requires role '~a'." action-arg role-arg)]

    [("add_effect")
     (define trigger-arg (hash-ref arguments 'trigger))
     (define kind-arg (hash-ref arguments 'kind))
     (define cond-arg (hash-ref arguments 'condition))
     (void (define-effect! trigger-arg kind-arg cond-arg))
     (format "Effect added: ~a/~a (condition: ~a)." trigger-arg kind-arg cond-arg)]

    [("check_obligations")
     (define module-arg (hash-ref arguments 'module))
     (define obligs (obligations-for module-arg))
     (if (null? obligs)
         (format "No obligation violations for '~a'." module-arg)
         (string-join
          (for/list ([o (in-list obligs)])
            (format "OBLIGATION: ~a (terminal statuses: ~a)" (first o) (second o)))
          "\n"))]

    [("project_module")
     (define module-arg (hash-ref arguments 'module))
     (case module-arg
       [("workflow") (project-workflow-py)]
       [("permissions") (project-permissions-py)]
       [("notifications") (project-notifications-py)]
       [("analytics") (project-analytics-py)]
       [else (error 'project_module "Unknown module: ~a" module-arg)])]

    [("project_all_to_disk")
     (define dir (or (unbox output-dir) (error 'project_all_to_disk "no --output-dir set")))
     (project-all! dir)
     (format "Projected 4 modules to ~a: workflow.py, permissions.py, notifications.py, analytics.py" dir)]

    [("query_domain")
     (define query-arg (hash-ref arguments 'query))
     (case query-arg
       [("terminal") (jsexpr->string (terminal-statuses))]
       [("active") (jsexpr->string (active-statuses))]
       [("all") (jsexpr->string (all-statuses))]
       [("can_transition")
        (define from-name (hash-ref arguments 'from_status ""))
        (define to-name (hash-ref arguments 'to_status ""))
        (define from-ent (hash-ref status-entities from-name #f))
        (unless from-ent (error 'query_domain "unknown status: ~a" from-name))
        (define t (create-ticket! "query-check"))
        (void (unlink! t ticket-status (lookup t ticket-status)))
        (void (link! t ticket-status from-ent))
        (define result (can-transition? t to-name))
        (format "~a → ~a: ~a" from-name to-name (if result "valid" "invalid"))]
       [else (error 'query_domain "Unknown query: ~a" query-arg)])]

    [else (error 'handle-tool "Unknown tool: ~a" name)]))

;; ── JSON-RPC dispatcher ─────────────────────────────────────

(define (make-response msg)
  (define method (hash-ref msg 'method #f))
  (define id (hash-ref msg 'id #f))
  (define params (hash-ref msg 'params (hasheq)))

  (case method
    [("initialize")
     (hasheq 'jsonrpc "2.0"
             'id id
             'result (hasheq
                      'protocolVersion "2024-11-05"
                      'capabilities (hasheq 'tools (hasheq))
                      'serverInfo (hasheq 'name "claimdesk-mcp"
                                          'version "1.0.0")))]

    [("notifications/initialized") #f]

    [("tools/list")
     (hasheq 'jsonrpc "2.0"
             'id id
             'result (hasheq 'tools tool-defs))]

    [("tools/call")
     (define tool-name (hash-ref params 'name))
     (define arguments (hash-ref params 'arguments (hasheq)))
     (define-values (result is-error)
       (with-handlers ([exn:fail? (lambda (e) (values (exn-message e) #t))])
         (values (handle-tool tool-name arguments) #f)))
     (define text (if (string? result) result (format "~a" result)))
     (hasheq 'jsonrpc "2.0"
             'id id
             'result
             (let ([content (list (hasheq 'type "text" 'text text))])
               (if is-error
                   (hasheq 'content content 'isError #t)
                   (hasheq 'content content))))]

    [else
     (and id
          (hasheq 'jsonrpc "2.0"
                  'id id
                  'error (hasheq 'code -32601
                                 'message (format "Unknown method: ~a" method))))]))

;; ── Main ─────────────────────────────────────────────────────

(setup-claimdesk!)
(eprintf "claimdesk-mcp: ready (mode: ~a)\n" (unbox server-mode))

(let loop ()
  (define msg (read-message))
  (when msg
    (with-handlers ([exn:fail? (lambda (e)
                      (eprintf "claimdesk-mcp error: ~a\n" (exn-message e)))])
      (define response (make-response msg))
      (when response (send-response response)))
    (loop)))

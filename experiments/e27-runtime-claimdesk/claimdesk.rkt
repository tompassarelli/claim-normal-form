#lang racket

;; E27: ClaimDesk as graph-native executable claims.
;;
;; The domain model IS the claim graph. Not parsed from Python.
;; Statuses, transitions, permissions, tickets — all claims.
;; Datalog derives: terminal membership, valid transitions, obligations.
;; Projection emits runnable Python from the graph.

(require "../../cnf-lib/private/kernel.rkt"
         "../../cnf-lib/private/datalog.rkt"
         "../../cnf-lib/private/schema.rkt")

(provide setup-claimdesk!
         ;; Domain predicates (re-exported for MCP tools)
         status-name status-group
         transition-from transition-to
         role-name permission-action permission-requires-role
         ticket-status ticket-assignee
         user-name user-role
         effect-trigger effect-kind effect-condition
         ;; Entity registries
         status-entities role-entities
         ;; Domain API
         define-status! define-transition! define-role!
         define-permission! define-effect!
         define-status-from-properties! define-status-validated!
         group-model derive-group validate-group-properties
         create-ticket! transition-ticket!
         ;; Queries
         terminal-statuses active-statuses blocked-statuses all-statuses
         can-transition? check-permission
         obligations-for
         ;; Projection
         project-workflow-py project-permissions-py
         project-notifications-py project-analytics-py
         project-all!)

;; ══════════════════════════════════════════════════════════════
;; Predicates — the vocabulary of the domain
;; ══════════════════════════════════════════════════════════════

(define-predicates
  ;; Status model
  status-name        ; entity → string ("open", "closed", ...)
  status-group       ; entity → string ("active", "terminal")

  ;; Transition rules
  transition-from    ; entity → status-entity
  transition-to      ; entity → status-entity

  ;; Roles & permissions
  role-name          ; entity → string ("agent", "admin")
  permission-action  ; entity → string ("manage", "archive", "reassign")
  permission-requires-role ; entity → role-entity

  ;; Tickets
  ticket-status      ; entity → status-entity
  ticket-assignee    ; entity → user-entity

  ;; Users
  user-name          ; entity → string
  user-role          ; entity → role-entity

  ;; Effects (notifications, analytics hooks)
  effect-trigger     ; entity → string ("transition", "create", ...)
  effect-kind        ; entity → string ("notification", "analytics", ...)
  effect-condition   ; entity → string ("not-terminal", "always", ...)

  ;; Obligations
  obligation-module  ; entity → string
  obligation-reason  ; entity → string
  obligation-severity ; entity → string
  )


;; ══════════════════════════════════════════════════════════════
;; Domain construction — building the model as claims
;; ══════════════════════════════════════════════════════════════

(define status-entities (make-hash))  ; name → entity-id
(define role-entities (make-hash))

(define (define-status! name group)
  (define e (entity!))
  (assert! e status-name name)
  (assert! e status-group group)
  (hash-set! status-entities name e)
  e)

(define (define-transition! from-name to-name)
  (define e (entity!))
  (define from-ent (hash-ref status-entities from-name
                             (lambda () (error 'define-transition!
                                               "unknown status: ~a" from-name))))
  (define to-ent (hash-ref status-entities to-name
                           (lambda () (error 'define-transition!
                                             "unknown status: ~a" to-name))))
  (link! e transition-from from-ent)
  (link! e transition-to to-ent)
  e)

(define (define-role! name)
  (define e (entity!))
  (assert! e role-name name)
  (hash-set! role-entities name e)
  e)

(define (define-permission! action required-role-name)
  (define e (entity!))
  (assert! e permission-action action)
  (define role-ent (hash-ref role-entities required-role-name
                             (lambda () (error 'define-permission!
                                               "unknown role: ~a" required-role-name))))
  (link! e permission-requires-role role-ent)
  e)

(define (define-effect! trigger kind condition)
  (define e (entity!))
  (assert! e effect-trigger trigger)
  (assert! e effect-kind kind)
  (assert! e effect-condition condition)
  e)


;; ══════════════════════════════════════════════════════════════
;; Group model — semantic properties that define each group
;; ══════════════════════════════════════════════════════════════

(define group-model
  (hash "active"   (hash "counts_as_work" #t "terminal" #f)
        "terminal" (hash "counts_as_work" #f "terminal" #t)
        "blocked"  (hash "counts_as_work" #f "terminal" #f)))

(define (derive-group props)
  (for/or ([(group-name group-props) (in-hash group-model)])
    (and (for/and ([(k v) (in-hash group-props)])
           (equal? (hash-ref props k 'missing) v))
         group-name)))

(define (validate-group-properties group props)
  (define expected (hash-ref group-model group #f))
  (unless expected
    (error 'validate-group-properties "unknown group: ~a" group))
  (for ([(k v) (in-hash props)])
    (define expected-v (hash-ref expected k #f))
    (when (and expected-v (not (equal? v expected-v)))
      (error 'validate-group-properties
             "contradiction: group '~a' requires ~a=~a but you declared ~a=~a"
             group k expected-v k v))))

(define (define-status-from-properties! name props)
  (define group (derive-group props))
  (unless group
    (error 'define-status-from-properties!
           "no group matches properties ~a (valid combinations: active=counts_as_work+not-terminal, terminal=not-counts_as_work+terminal, blocked=not-counts_as_work+not-terminal)"
           props))
  (define e (define-status! name group))
  e)

(define (define-status-validated! name group props)
  (validate-group-properties group props)
  (define-status! name group))


;; ══════════════════════════════════════════════════════════════
;; Ticket operations — executable behavior via claims
;; ══════════════════════════════════════════════════════════════

(define (create-ticket! title)
  (define e (entity!))
  (define open-ent (hash-ref status-entities "open"))
  (link! e ticket-status open-ent)
  (assert! e (named! "ticket-title") title)
  e)

(define (transition-ticket! ticket-ent to-status-name)
  (define to-ent (hash-ref status-entities to-status-name
                           (lambda () (error 'transition-ticket!
                                             "unknown status: ~a" to-status-name))))
  ;; Check: is this transition valid?
  (unless (can-transition? ticket-ent to-status-name)
    (error 'transition-ticket!
           "invalid transition to ~a" to-status-name))
  ;; Supersede old status link, claim new
  (define old-status (lookup ticket-ent ticket-status))
  (when old-status
    (unlink! ticket-ent ticket-status old-status))
  (link! ticket-ent ticket-status to-ent)
  to-ent)


;; ══════════════════════════════════════════════════════════════
;; Queries — reading derived facts from the graph
;; ══════════════════════════════════════════════════════════════

(define (all-statuses)
  (define cs (current-claims-where #:p status-name))
  (for/list ([c (in-list cs)])
    (resolve-value (list-ref c 3))))

(define (terminal-statuses)
  (define terminal-val (value! "terminal"))
  (define cs (current-claims-where #:p status-group #:r terminal-val))
  (for/list ([c (in-list cs)])
    (define ent (list-ref c 2))
    (lookup ent status-name)))

(define (active-statuses)
  (define active-val (value! "active"))
  (define cs (current-claims-where #:p status-group #:r active-val))
  (for/list ([c (in-list cs)])
    (define ent (list-ref c 2))
    (lookup ent status-name)))

(define (blocked-statuses)
  (define blocked-val (value! "blocked"))
  (define cs (current-claims-where #:p status-group #:r blocked-val))
  (for/list ([c (in-list cs)])
    (define ent (list-ref c 2))
    (lookup ent status-name)))

(define (can-transition? ticket-ent to-status-name)
  (define current-status-ent (lookup ticket-ent ticket-status))
  (unless current-status-ent
    (error 'can-transition? "ticket has no status"))
  (define to-ent (hash-ref status-entities to-status-name #f))
  (and to-ent
       (let ([transitions (current-claims-where #:p transition-from #:r current-status-ent)])
         (for/or ([t (in-list transitions)])
           (define t-ent (list-ref t 2))
           (define dest (lookup t-ent transition-to))
           (equal? dest to-ent)))))

(define (check-permission user-ent action-name)
  (define user-role-ent (lookup user-ent user-role))
  (define perms (current-claims-where #:p permission-action))
  (for/or ([p (in-list perms)])
    (define p-ent (list-ref p 2))
    (define p-action (resolve-value (list-ref p 3)))
    (and (equal? p-action action-name)
         (let ([required-role (lookup p-ent permission-requires-role)])
           (equal? required-role user-role-ent)))))


;; ══════════════════════════════════════════════════════════════
;; Obligation checker — graph-native, not string analysis
;; ══════════════════════════════════════════════════════════════

(define (obligations-for module-name)
  (define obligations '())
  (define has-blocked (not (null? (blocked-statuses))))

  (when (equal? module-name "workflow")
    (when has-blocked
      (define all (all-statuses))
      (define act (active-statuses))
      (define term (terminal-statuses))
      (define blk (blocked-statuses))
      (define covered (append act term blk))
      (define uncovered (filter (lambda (s) (not (member s covered))) all))
      (unless (null? uncovered)
        (set! obligations
              (cons (list "statuses exist without a group assignment"
                          uncovered)
                    obligations)))))

  (when (equal? module-name "notifications")
    (define effects (current-claims-where #:p effect-kind))
    (define notification-effects
      (filter (lambda (c)
                (equal? (resolve-value (list-ref c 3)) "notification"))
              effects))
    (define has-terminal-gate
      (for/or ([e (in-list notification-effects)])
        (define eff-ent (list-ref e 2))
        (define cond-val (lookup eff-ent effect-condition))
        (equal? cond-val "not-terminal")))
    (unless has-terminal-gate
      (set! obligations
            (cons (list "notifications must suppress for terminal statuses"
                        (terminal-statuses))
                  obligations)))
    (when has-blocked
      (define has-blocked-notify
        (for/or ([e (in-list notification-effects)])
          (define eff-ent (list-ref e 2))
          (define cond-val (lookup eff-ent effect-condition))
          (or (equal? cond-val "on-blocked")
              (equal? cond-val "blocked"))))
      (unless has-blocked-notify
        (set! obligations
              (cons (list "notifications should handle blocked status transitions"
                          (blocked-statuses))
                    obligations)))))

  (when (equal? module-name "analytics")
    (when has-blocked
      (define effects (current-claims-where #:p effect-kind))
      (define analytics-effects
        (filter (lambda (c)
                  (equal? (resolve-value (list-ref c 3)) "analytics"))
                effects))
      (define has-blocked-tag
        (for/or ([e (in-list analytics-effects)])
          (define eff-ent (list-ref e 2))
          (define cond-val (lookup eff-ent effect-condition))
          (or (equal? cond-val "tag-blocked")
              (equal? cond-val "blocked"))))
      (unless has-blocked-tag
        (set! obligations
              (cons (list "analytics must tag blocked status transitions separately from active"
                          (blocked-statuses))
                    obligations)))))

  (when (equal? module-name "permissions")
    (define perms-cs (current-claims-where #:p permission-action))
    (define actions (for/list ([p (in-list perms-cs)])
                      (resolve-value (list-ref p 3))))
    (unless (member "archive" actions)
      (set! obligations
            (cons (list "permissions must gate archive action on admin role"
                        (terminal-statuses))
                  obligations)))
    (when has-blocked
      (unless (member "suspend" actions)
        (set! obligations
              (cons (list "permissions must define suspend action for blocked statuses"
                          (blocked-statuses))
                    obligations)))
      (unless (member "resume" actions)
        (set! obligations
              (cons (list "permissions must define resume action for blocked statuses"
                          (blocked-statuses))
                    obligations)))))

  obligations)


;; ══════════════════════════════════════════════════════════════
;; Projection — emit Python from claims
;; ══════════════════════════════════════════════════════════════

(define (project-workflow-py)
  (define terms (terminal-statuses))
  (define acts (active-statuses))
  (define blk (blocked-statuses))
  (define all (all-statuses))

  (define transitions (current-claims-where #:p transition-from))
  (define trans-map (make-hash))
  (for ([t (in-list transitions)])
    (define t-ent (list-ref t 2))
    (define from-ent (list-ref t 3))
    (define to-ent (lookup t-ent transition-to))
    (define from-name (lookup from-ent status-name))
    (define to-name (lookup to-ent status-name))
    (when (and from-name to-name)
      (hash-update! trans-map from-name
                    (lambda (lst) (cons to-name lst))
                    '())))

  (define (format-set lst)
    (string-join (map (lambda (s) (format "~s" s)) lst) ", "))

  (string-append
   "# Auto-generated from CNF claim graph\n"
   "# DO NOT EDIT — edit the graph, re-project\n\n"
   (format "TERMINAL_STATUSES = {~a}\n" (format-set terms))
   (format "ACTIVE_STATUSES = {~a}\n" (format-set acts))
   (if (null? blk)
       ""
       (format "BLOCKED_STATUSES = {~a}\n" (format-set blk)))
   (format "ALL_STATUSES = {~a}\n\n" (format-set all))
   "VALID_TRANSITIONS = {\n"
   (string-join
    (for/list ([(from tos) (in-hash trans-map)])
      (format "    ~s: {~a},"
              from
              (string-join (map (lambda (s) (format "~s" s)) tos) ", ")))
    "\n")
   "\n}\n\n"
   "def is_active(status):\n"
   "    return status in ACTIVE_STATUSES\n\n"
   "def is_terminal(status):\n"
   "    return status in TERMINAL_STATUSES\n"
   (if (null? blk)
       ""
       "\ndef is_blocked(status):\n    return status in BLOCKED_STATUSES\n")))

(define (project-permissions-py)
  (define perms (current-claims-where #:p permission-action))
  (define rules (make-hash))
  (for ([p (in-list perms)])
    (define p-ent (list-ref p 2))
    (define action (resolve-value (list-ref p 3)))
    (define required-role-ent (lookup p-ent permission-requires-role))
    (define required-role (and required-role-ent
                               (lookup required-role-ent role-name)))
    (when (and action required-role)
      (hash-update! rules action
                    (lambda (lst) (cons required-role lst))
                    '())))

  (string-append
   "# Auto-generated from CNF claim graph\n"
   "# DO NOT EDIT — edit the graph, re-project\n\n"
   "from workflow import TERMINAL_STATUSES\n\n"
   "PERMISSION_RULES = {\n"
   (string-join
    (for/list ([(action roles) (in-hash rules)])
      (format "    ~s: {~a},"
              action
              (string-join (map (lambda (r) (format "~s" r)) roles) ", ")))
    "\n")
   "\n}\n\n"
   "def check_permission(user, action):\n"
   "    allowed_roles = PERMISSION_RULES.get(action, set())\n"
   "    return user.role in allowed_roles\n"))

(define (project-notifications-py)
  (define effects (current-claims-where #:p effect-kind))
  (define notif-effects
    (filter (lambda (c) (equal? (resolve-value (list-ref c 3)) "notification"))
            effects))
  (define has-terminal-suppress
    (for/or ([e (in-list notif-effects)])
      (define eff-ent (list-ref e 2))
      (equal? (lookup eff-ent effect-condition) "not-terminal")))

  (string-append
   "# Auto-generated from CNF claim graph\n"
   "# DO NOT EDIT — edit the graph, re-project\n\n"
   "from workflow import TERMINAL_STATUSES\n\n"
   "subscribers = {}\n\n"
   "def subscribe(ticket_id, email):\n"
   "    subscribers.setdefault(ticket_id, []).append(email)\n\n"
   "def notify_transition(ticket_id, old_status, new_status):\n"
   (if has-terminal-suppress
       "    if new_status in TERMINAL_STATUSES:\n        return []\n"
       "")
   "    emails = subscribers.get(ticket_id, [])\n"
   "    return [f\"Notification to {e}: {old_status} -> {new_status}\" for e in emails]\n"))

(define (project-analytics-py)
  (define blk (blocked-statuses))
  (define has-blocked (not (null? blk)))

  (define effects (current-claims-where #:p effect-kind))
  (define analytics-effects
    (filter (lambda (c) (equal? (resolve-value (list-ref c 3)) "analytics"))
            effects))
  (define has-terminal-tagging
    (for/or ([e (in-list analytics-effects)])
      (define eff-ent (list-ref e 2))
      (equal? (lookup eff-ent effect-condition) "always")))
  (define has-blocked-tagging
    (for/or ([e (in-list analytics-effects)])
      (define eff-ent (list-ref e 2))
      (define cond-val (lookup eff-ent effect-condition))
      (or (equal? cond-val "tag-blocked")
          (equal? cond-val "blocked"))))

  (string-append
   "# Auto-generated from CNF claim graph\n"
   "# DO NOT EDIT — edit the graph, re-project\n\n"
   "from workflow import TERMINAL_STATUSES, ACTIVE_STATUSES"
   (if has-blocked ", BLOCKED_STATUSES" "")
   "\n\nevents = []\n\n"
   "def track_transition(ticket_id, old_status, new_status):\n"
   "    event = {\n"
   "        \"ticket\": ticket_id,\n"
   "        \"from\": old_status,\n"
   "        \"to\": new_status,\n"
   (if has-terminal-tagging
       "        \"is_terminal\": new_status in TERMINAL_STATUSES,\n"
       "")
   (if (and has-blocked has-blocked-tagging)
       "        \"is_blocked\": new_status in BLOCKED_STATUSES,\n"
       "")
   "    }\n"
   "    events.append(event)\n"
   "    return event\n\n"
   "def active_ticket_count(statuses):\n"
   "    return sum(1 for s in statuses if s in ACTIVE_STATUSES)\n"))

(define (project-all! output-dir)
  (define (write-module name content)
    (define path (build-path output-dir (string-append name ".py")))
    (call-with-output-file path
      (lambda (out) (display content out))
      #:exists 'replace))
  (write-module "workflow" (project-workflow-py))
  (write-module "permissions" (project-permissions-py))
  (write-module "notifications" (project-notifications-py))
  (write-module "analytics" (project-analytics-py))
  (printf "Projected 4 modules to ~a\n" output-dir))


;; ══════════════════════════════════════════════════════════════
;; Setup — build the base ClaimDesk domain
;; ══════════════════════════════════════════════════════════════

(define (setup-claimdesk!)
  (setup-schema!)
  (hash-clear! status-entities)
  (hash-clear! role-entities)

  ;; Statuses
  (define-status! "open" "active")
  (define-status! "in_progress" "active")
  (define-status! "on_hold" "active")
  (define-status! "closed" "terminal")
  (define-status! "resolved" "terminal")
  (define-status! "archived" "terminal")

  ;; Transitions
  (define-transition! "open" "in_progress")
  (define-transition! "open" "closed")
  (define-transition! "in_progress" "on_hold")
  (define-transition! "in_progress" "closed")
  (define-transition! "in_progress" "resolved")
  (define-transition! "on_hold" "in_progress")
  (define-transition! "on_hold" "closed")
  (define-transition! "closed" "archived")
  (define-transition! "resolved" "archived")

  ;; Roles
  (define-role! "agent")
  (define-role! "admin")

  ;; Permissions
  (define-permission! "archive" "admin")
  (define-permission! "manage" "agent")
  (define-permission! "manage" "admin")

  ;; Effects
  (define-effect! "transition" "notification" "not-terminal")
  (define-effect! "transition" "analytics" "always")

  (printf "ClaimDesk domain: ~a statuses, ~a terminal, ~a active\n"
          (length (all-statuses))
          (length (terminal-statuses))
          (length (active-statuses))))

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

(provide setup-claimdesk! setup-claimdesk-e32!
         ;; Domain predicates (re-exported for MCP tools)
         status-name status-group
         transition-from transition-to
         role-name permission-action permission-requires-role
         ticket-status ticket-assignee
         user-name user-role
         effect-trigger effect-kind effect-condition
         ;; Priority predicates
         priority-name priority-response-target
         priority-required-role priority-notification-mode
         priority-auto-escalate priority-escalates-to
         ticket-priority
         ;; Entity registries
         status-entities role-entities priority-entities
         ;; Domain API
         define-status! define-transition! define-role!
         define-permission! define-effect! define-priority!
         define-status-from-properties! define-status-validated!
         group-model derive-group validate-group-properties
         create-ticket! transition-ticket!
         ;; Queries
         terminal-statuses active-statuses blocked-statuses
         escalated-statuses statuses-for-group
         all-statuses get-used-groups
         all-priorities priority-config
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
  effect-condition   ; entity → string — group name or group-derived condition

  ;; Priority model
  priority-name              ; entity → string ("low", "normal", "high", "critical")
  priority-response-target   ; entity → number (hours)
  priority-required-role     ; entity → string ("any", "agent", "senior", "admin")
  priority-notification-mode ; entity → string ("normal", "immediate_email", "urgent_page")
  priority-auto-escalate     ; entity → boolean
  priority-escalates-to      ; entity → string (group name)
  ticket-priority            ; entity → priority-entity

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

(define priority-entities (make-hash))

(define (define-priority! name response-target required-role
                          notification-mode auto-escalate
                          [escalates-to #f])
  (define e (entity!))
  (assert! e priority-name name)
  (assert! e priority-response-target response-target)
  (assert! e priority-required-role required-role)
  (assert! e priority-notification-mode notification-mode)
  (assert! e priority-auto-escalate auto-escalate)
  (when (and auto-escalate escalates-to)
    (assert! e priority-escalates-to escalates-to))
  (hash-set! priority-entities name e)
  e)


;; ══════════════════════════════════════════════════════════════
;; Group model — semantic properties that define each group
;; ══════════════════════════════════════════════════════════════

;; Each group has a property signature and a list of required permission actions.
;; derive-group uses most-specific match: the group whose property set is the
;; largest subset that matches all declared properties.

(define group-model
  (hash "active"    (hash "properties" (hash "counts_as_work" #t "terminal" #f)
                          "actions" '())
        "terminal"  (hash "properties" (hash "counts_as_work" #f "terminal" #t)
                          "actions" '("archive"))
        "blocked"   (hash "properties" (hash "counts_as_work" #f "terminal" #f)
                          "actions" '("suspend" "resume"))
        "escalated" (hash "properties" (hash "counts_as_work" #t "terminal" #f "priority" "high")
                          "actions" '("escalate" "de_escalate"))))

(define (group-properties group-name)
  (hash-ref (hash-ref group-model group-name) "properties"))

(define (group-actions group-name)
  (hash-ref (hash-ref group-model group-name) "actions"))

(define (derive-group props)
  (define matches
    (for/list ([(gn ginfo) (in-hash group-model)]
               #:when (let ([gprops (hash-ref ginfo "properties")])
                        (for/and ([(k v) (in-hash gprops)])
                          (equal? (hash-ref props k 'missing) v))))
      (cons gn (hash-count (hash-ref ginfo "properties")))))
  (and (not (null? matches))
       (car (argmax cdr matches))))

(define (validate-group-properties group props)
  (define expected (hash-ref group-model group #f))
  (unless expected
    (error 'validate-group-properties "unknown group: ~a" group))
  (define expected-props (hash-ref expected "properties"))
  (for ([(k v) (in-hash props)])
    (define expected-v (hash-ref expected-props k #f))
    (when (and expected-v (not (equal? v expected-v)))
      (error 'validate-group-properties
             "contradiction: group '~a' requires ~a=~a but you declared ~a=~a"
             group k expected-v k v))))

(define (define-status-from-properties! name props)
  (define group (derive-group props))
  (unless group
    (define known
      (string-join
       (for/list ([(gn ginfo) (in-hash group-model)])
         (define gprops (hash-ref ginfo "properties"))
         (format "~a=~a" gn
                 (string-join
                  (for/list ([(k v) (in-hash gprops)])
                    (format "~a:~a" k v))
                  "+")))
       ", "))
    (error 'define-status-from-properties!
           "no group matches properties ~a (known groups: ~a)"
           props known))
  (define-status! name group))

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
  (unless (can-transition? ticket-ent to-status-name)
    (error 'transition-ticket!
           "invalid transition to ~a" to-status-name))
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

(define (statuses-for-group group-name)
  (define gval (value! group-name))
  (define cs (current-claims-where #:p status-group #:r gval))
  (for/list ([c (in-list cs)])
    (define ent (list-ref c 2))
    (lookup ent status-name)))

(define (terminal-statuses) (statuses-for-group "terminal"))
(define (active-statuses)   (statuses-for-group "active"))
(define (blocked-statuses)  (statuses-for-group "blocked"))
(define (escalated-statuses) (statuses-for-group "escalated"))

(define (get-used-groups)
  (define cs (current-claims-where #:p status-group))
  (remove-duplicates
   (for/list ([c (in-list cs)])
     (resolve-value (list-ref c 3)))))

(define (all-priorities)
  (define cs (current-claims-where #:p priority-name))
  (for/list ([c (in-list cs)])
    (resolve-value (list-ref c 3))))

(define (priority-config name)
  (define ent (hash-ref priority-entities name #f))
  (and ent
       (hash "name" name
             "response_target" (lookup ent priority-response-target)
             "required_role" (lookup ent priority-required-role)
             "notification_mode" (lookup ent priority-notification-mode)
             "auto_escalate" (lookup ent priority-auto-escalate)
             "escalates_to" (lookup ent priority-escalates-to))))

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
;; Effect coverage — does an effect reference a given group?
;; ══════════════════════════════════════════════════════════════

(define (effect-covers-group? eff-entity group-name)
  (define cond-val (lookup eff-entity effect-condition))
  (or (equal? cond-val group-name)
      (equal? cond-val (string-append "tag-" group-name))
      (equal? cond-val (string-append "on-" group-name))
      (equal? cond-val (string-append "not-" group-name))))

(define (has-effect-coverage? kind group-name)
  (define effects (current-claims-where #:p effect-kind))
  (define kind-effects
    (filter (lambda (c) (equal? (resolve-value (list-ref c 3)) kind))
            effects))
  (for/or ([e (in-list kind-effects)])
    (effect-covers-group? (list-ref e 2) group-name)))


;; ══════════════════════════════════════════════════════════════
;; Obligation checker — group-driven
;; ══════════════════════════════════════════════════════════════

(define (obligations-for module-name)
  (define used-groups (get-used-groups))
  (define non-active-groups
    (filter (lambda (g) (and (not (equal? g "active"))
                             (not (null? (statuses-for-group g)))))
            (hash-keys group-model)))
  (define obligations '())

  (define (add-obligation! reason context)
    (set! obligations (cons (list reason context) obligations)))

  (when (equal? module-name "workflow")
    (define all (all-statuses))
    (define covered
      (apply append
             (for/list ([g (in-list used-groups)])
               (statuses-for-group g))))
    (define uncovered (filter (lambda (s) (not (member s covered))) all))
    (unless (null? uncovered)
      (add-obligation! "statuses exist without a group assignment" uncovered))
    ;; Cross-entity: priority auto-escalation targets
    (for ([pname (in-list (all-priorities))])
      (define pent (hash-ref priority-entities pname))
      (when (lookup pent priority-auto-escalate)
        (define esc-to (lookup pent priority-escalates-to))
        (cond
          [(not esc-to)
           (add-obligation!
            (format "priority '~a' has auto_escalate but no escalates_to target" pname)
            (list pname))]
          [(null? (statuses-for-group esc-to))
           (add-obligation!
            (format "priority '~a' escalates to group '~a' but that group has no statuses" pname esc-to)
            (list pname esc-to))]))))

  (when (equal? module-name "notifications")
    (define effects (current-claims-where #:p effect-kind))
    (define notification-effects
      (filter (lambda (c) (equal? (resolve-value (list-ref c 3)) "notification"))
              effects))
    ;; Terminal group: must have suppression
    (when (member "terminal" used-groups)
      (define has-terminal-gate
        (for/or ([e (in-list notification-effects)])
          (effect-covers-group? (list-ref e 2) "terminal")))
      (unless has-terminal-gate
        (add-obligation! "notifications must suppress for terminal statuses"
                         (terminal-statuses))))
    ;; Non-active, non-terminal groups: must have notification handling
    (for ([g (in-list non-active-groups)]
          #:when (not (equal? g "terminal")))
      (unless (has-effect-coverage? "notification" g)
        (add-obligation!
         (format "notifications should handle ~a status transitions" g)
         (statuses-for-group g))))
    ;; Cross-entity: priorities with non-normal notification modes
    (define prios (all-priorities))
    (when (not (null? prios))
      (define non-normal
        (filter (lambda (pname)
                  (define pent (hash-ref priority-entities pname))
                  (define mode (lookup pent priority-notification-mode))
                  (and mode (not (equal? mode "normal"))))
                prios))
      (unless (null? non-normal)
        (define has-priority-notif
          (for/or ([e (in-list notification-effects)])
            (define cond-val (lookup (list-ref e 2) effect-condition))
            (and cond-val (string-contains? cond-val "priority"))))
        (unless has-priority-notif
          (add-obligation!
           (format "priorities ~a have non-normal notification modes but no priority notification effect exists" non-normal)
           non-normal)))))

  (when (equal? module-name "analytics")
    ;; Non-standard groups (not active, not terminal) need specific analytics effects.
    ;; Terminal tagging is always emitted by the projector.
    (for ([g (in-list non-active-groups)]
          #:when (not (equal? g "terminal")))
      (unless (has-effect-coverage? "analytics" g)
        (add-obligation!
         (format "analytics must tag ~a status transitions separately" g)
         (statuses-for-group g))))
    ;; Cross-entity: priorities need SLA tracking
    (define prios (all-priorities))
    (when (not (null? prios))
      (define has-priority-analytics
        (let ([effects (current-claims-where #:p effect-kind)])
          (for/or ([e (in-list effects)])
            (and (equal? (resolve-value (list-ref e 3)) "analytics")
                 (let ([cond-val (lookup (list-ref e 2) effect-condition)])
                   (and cond-val (string-contains? cond-val "priority")))))))
      (unless has-priority-analytics
        (add-obligation!
         "priorities exist but no analytics effect tracks priority/SLA data"
         prios))))

  (when (equal? module-name "permissions")
    (define perms-cs (current-claims-where #:p permission-action))
    (define actions (for/list ([p (in-list perms-cs)])
                      (resolve-value (list-ref p 3))))
    ;; Group-specific required actions
    (for ([g (in-list non-active-groups)]
          #:when (hash-has-key? group-model g))
      (for ([action (in-list (group-actions g))])
        (unless (member action actions)
          (add-obligation!
           (format "permissions must define ~a action for ~a statuses" action g)
           (statuses-for-group g)))))
    ;; Cross-entity: restricted priorities need permission gates
    (for ([pname (in-list (all-priorities))])
      (define pent (hash-ref priority-entities pname))
      (define req-role (lookup pent priority-required-role))
      (when (and req-role (not (equal? req-role "any")))
        (define has-gate
          (for/or ([a (in-list actions)])
            (or (equal? a (string-append "set_" pname))
                (equal? a (string-append "set_priority_" pname))
                (and (string-contains? a "priority")
                     (string-contains? a pname)))))
        (unless has-gate
          (add-obligation!
           (format "priority '~a' requires role '~a' but no permission gates setting it (expected 'set_~a' or similar)"
                   pname req-role pname)
           (list pname))))))

  obligations)


;; ══════════════════════════════════════════════════════════════
;; Projection — emit Python from claims (group-driven)
;; ══════════════════════════════════════════════════════════════

(define (format-set lst)
  (string-join (map (lambda (s) (format "~s" s)) lst) ", "))

(define (project-workflow-py)
  (define terms (terminal-statuses))
  (define acts (active-statuses))
  (define all (all-statuses))
  (define used (get-used-groups))

  ;; Non-standard groups with statuses (sorted for deterministic output)
  (define extra-groups
    (sort
     (filter (lambda (g) (and (not (member g '("active" "terminal")))
                              (not (null? (statuses-for-group g)))))
             used)
     string<?))

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

  (string-append
   "# Auto-generated from CNF claim graph\n"
   "# DO NOT EDIT — edit the graph, re-project\n\n"
   (format "TERMINAL_STATUSES = {~a}\n" (format-set terms))
   (format "ACTIVE_STATUSES = {~a}\n" (format-set acts))
   ;; Emit status sets for non-standard groups
   (apply string-append
          (for/list ([g (in-list extra-groups)])
            (format "~a_STATUSES = {~a}\n"
                    (string-upcase g)
                    (format-set (statuses-for-group g)))))
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
   ;; Emit helpers for non-standard groups
   (apply string-append
          (for/list ([g (in-list extra-groups)])
            (format "\ndef is_~a(status):\n    return status in ~a_STATUSES\n"
                    g (string-upcase g))))
   ;; Priority section (from graph relations)
   (let ([prios (sort (all-priorities) string<?)])
     (if (null? prios)
         ""
         (string-append
          "\nPRIORITY_LEVELS = {\n"
          (string-join
           (for/list ([pname (in-list prios)])
             (define pent (hash-ref priority-entities pname))
             (define rt (lookup pent priority-response-target))
             (define auto-esc (lookup pent priority-auto-escalate))
             (define esc-to (lookup pent priority-escalates-to))
             (define req-role (lookup pent priority-required-role))
             (define notif-mode (lookup pent priority-notification-mode))
             (define parts
               (append
                (list (format "\"response_target\": ~a" rt))
                (if (and auto-esc (not (equal? auto-esc #f)))
                    (append
                     (list "\"auto_escalate\": True")
                     (if esc-to (list (format "\"escalates_to\": ~s" esc-to)) '()))
                    '())
                (if (and req-role (not (equal? req-role "any")))
                    (list (format "\"required_role\": ~s" req-role))
                    '())
                (if (and notif-mode (not (equal? notif-mode "normal")))
                    (list (format "\"notification_mode\": ~s" notif-mode))
                    '())))
             (format "    ~s: {~a}," pname (string-join parts ", ")))
           "\n")
          "\n}\n\n"
          "def get_response_target(priority):\n"
          "    config = PRIORITY_LEVELS.get(priority, PRIORITY_LEVELS.get(\"normal\", {}))\n"
          "    return config.get(\"response_target\")\n")))))

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
   "    return user.role in allowed_roles\n"
   ;; Priority role requirements (from graph relations)
   (let ([restricted
          (sort
           (filter (lambda (pname)
                     (define pent (hash-ref priority-entities pname))
                     (define req (lookup pent priority-required-role))
                     (and req (not (equal? req "any"))))
                   (all-priorities))
           string<?)])
     (if (null? restricted)
         ""
         (let ([role-hierarchy '("agent" "senior" "admin")])
           (string-append
            "\nROLE_HIERARCHY = [\"agent\", \"senior\", \"admin\"]\n\n"
            "PRIORITY_ROLE_REQUIREMENTS = {\n"
            (string-join
             (for/list ([pname (in-list restricted)])
               (define pent (hash-ref priority-entities pname))
               (define min-role (lookup pent priority-required-role))
               (define min-idx
                 (or (index-of role-hierarchy min-role) 0))
               (define allowed
                 (drop role-hierarchy min-idx))
               (format "    ~s: {~a},"
                       pname
                       (string-join (map (lambda (r) (format "~s" r)) allowed) ", ")))
             "\n")
            "\n}\n\n"
            "def can_set_priority(user, priority):\n"
            "    required = PRIORITY_ROLE_REQUIREMENTS.get(priority)\n"
            "    if required is None:\n"
            "        return True\n"
            "    return user.role in required\n"))))))

(define (project-notifications-py)
  (define used (get-used-groups))
  (define effects (current-claims-where #:p effect-kind))
  (define notif-effects
    (filter (lambda (c) (equal? (resolve-value (list-ref c 3)) "notification"))
            effects))

  (define has-terminal-suppress
    (for/or ([e (in-list notif-effects)])
      (effect-covers-group? (list-ref e 2) "terminal")))

  ;; Non-standard, non-terminal groups with notification effects
  (define extra-groups
    (sort
     (filter (lambda (g)
               (and (not (member g '("active" "terminal")))
                    (not (null? (statuses-for-group g)))
                    (has-effect-coverage? "notification" g)))
             used)
     string<?))

  ;; Build imports
  (define imports
    (append '("TERMINAL_STATUSES")
            (for/list ([g (in-list extra-groups)])
              (format "~a_STATUSES" (string-upcase g)))))

  (string-append
   "# Auto-generated from CNF claim graph\n"
   "# DO NOT EDIT — edit the graph, re-project\n\n"
   (format "from workflow import ~a\n\n" (string-join imports ", "))
   "subscribers = {}\n\n"
   "def subscribe(ticket_id, email):\n"
   "    subscribers.setdefault(ticket_id, []).append(email)\n\n"
   "def notify_transition(ticket_id, old_status, new_status):\n"
   (if has-terminal-suppress
       "    if new_status in TERMINAL_STATUSES:\n        return []\n"
       "")
   ;; Escalated/blocked/etc get special handling
   (apply string-append
          (for/list ([g (in-list extra-groups)])
            (format "    if new_status in ~a_STATUSES:\n        emails = subscribers.get(ticket_id, [])\n        return [f\"~a notification to {e}: {old_status} -> {new_status}\" for e in emails]\n"
                    (string-upcase g)
                    (string-titlecase g))))
   "    emails = subscribers.get(ticket_id, [])\n"
   "    return [f\"Notification to {e}: {old_status} -> {new_status}\" for e in emails]\n"
   ;; Priority notification routing (from graph relations)
   (let ([non-normal
          (sort
           (filter (lambda (pname)
                     (define pent (hash-ref priority-entities pname))
                     (define mode (lookup pent priority-notification-mode))
                     (and mode (not (equal? mode "normal"))))
                   (all-priorities))
           string<?)])
     (if (null? non-normal)
         ""
         (string-append
          "\nPRIORITY_NOTIFICATION_MODES = {\n"
          (string-join
           (for/list ([pname (in-list non-normal)])
             (define pent (hash-ref priority-entities pname))
             (define mode (lookup pent priority-notification-mode))
             (format "    ~s: ~s," pname mode))
           "\n")
          "\n}\n\n"
          "def get_priority_notification_mode(priority):\n"
          "    return PRIORITY_NOTIFICATION_MODES.get(priority, \"normal\")\n")))))

(define (project-analytics-py)
  (define used (get-used-groups))

  ;; Non-standard groups with analytics effects (for is_{group} tags)
  (define extra-tagged
    (sort
     (filter (lambda (g)
               (and (not (member g '("active" "terminal")))
                    (not (null? (statuses-for-group g)))
                    (has-effect-coverage? "analytics" g)))
             used)
     string<?))

  ;; Non-active groups with counts_as_work=true (for active_ticket_count)
  (define extra-work
    (sort
     (filter (lambda (g)
               (and (not (equal? g "active"))
                    (hash-has-key? group-model g)
                    (hash-ref (hash-ref (hash-ref group-model g) "properties")
                              "counts_as_work" #f)
                    (not (null? (statuses-for-group g)))))
             used)
     string<?))

  ;; Build imports: union of tagged + work groups
  (define extra-imports
    (sort (remove-duplicates (append extra-tagged extra-work)) string<?))
  (define imports
    (append '("TERMINAL_STATUSES" "ACTIVE_STATUSES")
            (for/list ([g (in-list extra-imports)])
              (format "~a_STATUSES" (string-upcase g)))))

  (string-append
   "# Auto-generated from CNF claim graph\n"
   "# DO NOT EDIT — edit the graph, re-project\n\n"
   (format "from workflow import ~a\n\n" (string-join imports ", "))
   "events = []\n\n"
   "def track_transition(ticket_id, old_status, new_status):\n"
   "    event = {\n"
   "        \"ticket\": ticket_id,\n"
   "        \"from\": old_status,\n"
   "        \"to\": new_status,\n"
   ;; Terminal tagging always present
   "        \"is_terminal\": new_status in TERMINAL_STATUSES,\n"
   ;; Tag for each extra group with analytics effects
   (apply string-append
          (for/list ([g (in-list extra-tagged)])
            (format "        \"is_~a\": new_status in ~a_STATUSES,\n"
                    g (string-upcase g))))
   "    }\n"
   "    events.append(event)\n"
   "    return event\n\n"
   ;; active_ticket_count includes all counts_as_work groups
   (let ([work-groups
          (sort
           (filter (lambda (g)
                     (and (hash-has-key? group-model g)
                          (hash-ref (hash-ref (hash-ref group-model g) "properties")
                                    "counts_as_work" #f)
                          (not (null? (statuses-for-group g)))))
                   used)
           string<?)])
     (if (<= (length work-groups) 1)
         (string-append
          "def active_ticket_count(statuses):\n"
          "    return sum(1 for s in statuses if s in ACTIVE_STATUSES)\n")
         (string-append
          "def active_ticket_count(statuses):\n"
          (format "    work_statuses = ~a\n"
                  (string-join (for/list ([g work-groups])
                                 (format "~a_STATUSES" (string-upcase g)))
                               " | "))
          "    return sum(1 for s in statuses if s in work_statuses)\n")))
   ;; Priority SLA tracking (from graph relations)
   (let ([prios (sort (all-priorities) string<?)])
     (if (null? prios)
         ""
         (string-append
          "\nPRIORITY_SLA_TARGETS = {\n"
          (string-join
           (for/list ([pname (in-list prios)])
             (define pent (hash-ref priority-entities pname))
             (define rt (lookup pent priority-response-target))
             (format "    ~s: ~a," pname rt))
           "\n")
          "\n}\n\n"
          "def track_priority_assignment(ticket_id, priority):\n"
          "    event = {\n"
          "        \"ticket\": ticket_id,\n"
          "        \"priority\": priority,\n"
          "        \"response_target\": PRIORITY_SLA_TARGETS.get(priority),\n"
          "        \"is_critical\": priority == \"critical\",\n"
          "    }\n"
          "    events.append(event)\n"
          "    return event\n\n"
          "def sla_compliance(priority, elapsed_hours):\n"
          "    target = PRIORITY_SLA_TARGETS.get(priority)\n"
          "    if target is None:\n"
          "        return True\n"
          "    return elapsed_hours <= target\n")))))

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

(define (setup-claimdesk-e32!)
  (setup-schema!)
  (hash-clear! status-entities)
  (hash-clear! role-entities)
  (hash-clear! priority-entities)

  ;; Statuses (including escalated — the auto-escalation target)
  (define-status! "open" "active")
  (define-status! "in_progress" "active")
  (define-status! "on_hold" "active")
  (define-status! "closed" "terminal")
  (define-status! "resolved" "terminal")
  (define-status! "archived" "terminal")
  (define-status! "escalated" "escalated")

  ;; Transitions (including escalation paths)
  (define-transition! "open" "in_progress")
  (define-transition! "open" "closed")
  (define-transition! "in_progress" "on_hold")
  (define-transition! "in_progress" "closed")
  (define-transition! "in_progress" "resolved")
  (define-transition! "in_progress" "escalated")
  (define-transition! "on_hold" "in_progress")
  (define-transition! "on_hold" "closed")
  (define-transition! "closed" "archived")
  (define-transition! "resolved" "archived")
  (define-transition! "escalated" "in_progress")
  (define-transition! "escalated" "closed")

  ;; Roles (including senior for priority gating)
  (define-role! "agent")
  (define-role! "senior")
  (define-role! "admin")

  ;; Permissions
  (define-permission! "archive" "admin")
  (define-permission! "manage" "agent")
  (define-permission! "manage" "admin")
  (define-permission! "manage" "senior")
  (define-permission! "escalate" "admin")
  (define-permission! "de_escalate" "admin")

  ;; Effects
  (define-effect! "transition" "notification" "not-terminal")
  (define-effect! "transition" "analytics" "always")
  (define-effect! "transition" "notification" "escalated")
  (define-effect! "transition" "analytics" "escalated")

  (printf "ClaimDesk E32 domain: ~a statuses, ~a groups, ~a roles\n"
          (length (all-statuses))
          (length (get-used-groups))
          (length (hash-keys role-entities))))

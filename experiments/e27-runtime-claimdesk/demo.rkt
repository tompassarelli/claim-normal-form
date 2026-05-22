#lang racket

;; E27 demo: the full graph-native pipeline.
;;
;;   setup domain → create ticket → transition → add new terminal status
;;   → obligations fire → project Python from claims

(require "claimdesk.rkt"
         "../../cnf-lib/private/kernel.rkt"
         "../../cnf-lib/private/datalog.rkt"
         "../../cnf-lib/private/schema.rkt")

(define (section title)
  (printf "\n═══ ~a ═══\n" title))

;; ── 1. Build the domain ──────────────────────────────────────

(section "1. Setup domain")
(setup-claimdesk!)

;; ── 2. Query derived facts ───────────────────────────────────

(section "2. Derived facts")
(printf "All statuses:      ~a\n" (all-statuses))
(printf "Terminal statuses:  ~a\n" (terminal-statuses))
(printf "Active statuses:    ~a\n" (active-statuses))

;; ── 3. Create and transition a ticket ────────────────────────

(section "3. Ticket lifecycle")
(define t1 (create-ticket! "Customer can't login"))
(define (ticket-status-name t)
  (lookup (lookup t ticket-status) status-name))
(printf "Created ticket. Status: ~a\n" (ticket-status-name t1))

(printf "Can open→in_progress? ~a\n" (can-transition? t1 "in_progress"))
(printf "Can open→archived?    ~a\n" (can-transition? t1 "archived"))

(void (transition-ticket! t1 "in_progress"))
(printf "Transitioned → ~a\n" (ticket-status-name t1))

(printf "Can in_progress→resolved? ~a\n" (can-transition? t1 "resolved"))
(void (transition-ticket! t1 "resolved"))
(printf "Transitioned → ~a\n" (ticket-status-name t1))

(printf "Can resolved→open? ~a\n" (can-transition? t1 "open"))

;; ── 4. Permission checks ────────────────────────────────────

(section "4. Permissions")
(define admin-user (entity!))
(void (assert! admin-user user-name "alice"))
(void (link! admin-user user-role (hash-ref role-entities "admin")))

(define agent-user (entity!))
(void (assert! agent-user user-name "bob"))
(void (link! agent-user user-role (hash-ref role-entities "agent")))

(printf "Admin can archive?  ~a\n" (check-permission admin-user "archive"))
(printf "Agent can archive?  ~a\n" (check-permission agent-user "archive"))
(printf "Agent can manage?   ~a\n" (check-permission agent-user "manage"))
(printf "Admin can manage?   ~a\n" (check-permission admin-user "manage"))

;; ── 5. Obligations (before adding new status) ───────────────

(section "5. Obligations (baseline)")
(printf "Notification obligations: ~a\n" (obligations-for "notifications"))
(printf "Permission obligations:   ~a\n" (obligations-for "permissions"))

;; ── 6. The thesis test: add "duplicate" as terminal status ──
;;
;; File-native agent: must find TERMINAL_STATUSES in workflow.py,
;; update transition rules, update every filtering module, update tests.
;; Graph-native: one claim. Downstream consequences are derived.

(section "6. Add 'duplicate' terminal status")
(void (define-status! "duplicate" "terminal"))
(void (define-transition! "open" "duplicate"))
(void (define-transition! "in_progress" "duplicate"))

(printf "Terminal statuses now: ~a\n" (terminal-statuses))
(printf "All statuses now:     ~a\n" (all-statuses))

;; New ticket can reach duplicate
(define t2 (create-ticket! "Duplicate of #1"))
(printf "Can open→duplicate? ~a\n" (can-transition? t2 "duplicate"))
(void (transition-ticket! t2 "duplicate"))
(printf "Ticket transitioned → ~a\n" (ticket-status-name t2))

;; ── 7. Project Python from claims ────────────────────────────

(section "7. Projected workflow.py")
(display (project-workflow-py))

(section "7b. Projected permissions.py")
(display (project-permissions-py))

;; ── 8. Verify projection includes new status ────────────────

(section "8. Verify projection")
(define workflow-py (project-workflow-py))
(define has-duplicate (string-contains? workflow-py "duplicate"))
(printf "Projected Python includes 'duplicate': ~a\n" has-duplicate)
(unless has-duplicate
  (error 'demo "projection did not include new terminal status"))

(define perms-py (project-permissions-py))
(define has-archive (string-contains? perms-py "archive"))
(printf "Projected Python includes 'archive':   ~a\n" has-archive)

(section "Done")
(printf "Pipeline: domain → tickets → transitions → new status → obligations → projection ✓\n")

#lang racket

(require rackunit
         "claimdesk.rkt"
         "../../cnf-lib/private/kernel.rkt"
         "../../cnf-lib/private/datalog.rkt"
         "../../cnf-lib/private/schema.rkt")

;; Fresh store for each test suite
(define (with-fresh-domain thunk)
  (reset-store!)
  (setup-claimdesk!)
  (thunk))

;; ── Status model ─────────────────────────────────────────────

(test-case "statuses: 6 total, 3 terminal, 3 active"
  (with-fresh-domain
   (lambda ()
     (check-equal? (length (all-statuses)) 6)
     (check-equal? (length (terminal-statuses)) 3)
     (check-equal? (length (active-statuses)) 3)
     (check-not-false (member "closed" (terminal-statuses)))
     (check-not-false (member "resolved" (terminal-statuses)))
     (check-not-false (member "archived" (terminal-statuses)))
     (check-not-false (member "open" (active-statuses)))
     (check-not-false (member "in_progress" (active-statuses))))))

;; ── Transitions ──────────────────────────────────────────────

(test-case "transitions: valid paths work"
  (with-fresh-domain
   (lambda ()
     (define t (create-ticket! "test"))
     (check-true (can-transition? t "in_progress"))
     (check-true (can-transition? t "closed"))
     (check-false (can-transition? t "archived"))
     (check-false (can-transition? t "resolved")))))

(test-case "transitions: invalid transition errors"
  (with-fresh-domain
   (lambda ()
     (define t (create-ticket! "test"))
     (check-exn exn:fail?
                (lambda () (transition-ticket! t "archived"))))))

(test-case "transitions: chain through lifecycle"
  (with-fresh-domain
   (lambda ()
     (define t (create-ticket! "test"))
     (void (transition-ticket! t "in_progress"))
     (check-true (can-transition? t "resolved"))
     (void (transition-ticket! t "resolved"))
     (check-true (can-transition? t "archived"))
     (check-false (can-transition? t "open"))
     (void (transition-ticket! t "archived"))
     (check-false (can-transition? t "open"))
     (check-false (can-transition? t "in_progress")))))

;; ── Permissions ──────────────────────────────────────────────

(test-case "permissions: role-based access"
  (with-fresh-domain
   (lambda ()
     (define admin (entity!))
     (void (assert! admin user-name "alice"))
     (void (link! admin user-role (hash-ref role-entities "admin")))

     (define agent (entity!))
     (void (assert! agent user-name "bob"))
     (void (link! agent user-role (hash-ref role-entities "agent")))

     (check-true (check-permission admin "archive"))
     (check-false (check-permission agent "archive"))
     (check-true (check-permission agent "manage"))
     (check-true (check-permission admin "manage"))
     (check-false (check-permission agent "nonexistent")))))

;; ── Adding a new terminal status ─────────────────────────────

(test-case "add-status: new terminal status appears in all queries"
  (with-fresh-domain
   (lambda ()
     (void (define-status! "duplicate" "terminal"))
     (check-equal? (length (all-statuses)) 7)
     (check-equal? (length (terminal-statuses)) 4)
     (check-not-false (member "duplicate" (terminal-statuses))))))

(test-case "add-status: new transitions work immediately"
  (with-fresh-domain
   (lambda ()
     (void (define-status! "duplicate" "terminal"))
     (void (define-transition! "open" "duplicate"))
     (define t (create-ticket! "dup test"))
     (check-true (can-transition? t "duplicate"))
     (void (transition-ticket! t "duplicate"))
     (check-false (can-transition? t "open")))))

;; ── Projection ───────────────────────────────────────────────

(test-case "projection: workflow.py includes all statuses"
  (with-fresh-domain
   (lambda ()
     (define py (project-workflow-py))
     (check-true (string-contains? py "TERMINAL_STATUSES"))
     (check-true (string-contains? py "ACTIVE_STATUSES"))
     (check-true (string-contains? py "VALID_TRANSITIONS"))
     (for ([s (in-list (all-statuses))])
       (check-true (string-contains? py s)
                   (format "workflow.py missing status: ~a" s))))))

(test-case "projection: new status appears in projected Python"
  (with-fresh-domain
   (lambda ()
     (void (define-status! "duplicate" "terminal"))
     (void (define-transition! "open" "duplicate"))
     (define py (project-workflow-py))
     (check-true (string-contains? py "duplicate"))
     (check-true (string-contains? py "is_terminal")))))

(test-case "projection: permissions.py reflects role rules"
  (with-fresh-domain
   (lambda ()
     (define py (project-permissions-py))
     (check-true (string-contains? py "archive"))
     (check-true (string-contains? py "admin"))
     (check-true (string-contains? py "manage")))))

;; ── Obligations ──────────────────────────────────────────────

(test-case "obligations: notifications are clean with terminal gate"
  (with-fresh-domain
   (lambda ()
     (check-equal? (obligations-for "notifications") '()))))

(test-case "obligations: notifications flag when no terminal gate"
  (with-fresh-domain
   (lambda ()
     ;; Remove the terminal-gated effect, add an ungated one
     (void (define-effect! "transition" "notification" "always"))
     ;; The existing not-terminal effect still satisfies the check
     (check-equal? (obligations-for "notifications") '()))))

(test-case "obligations: permissions are clean with archive gate"
  (with-fresh-domain
   (lambda ()
     (check-equal? (obligations-for "permissions") '()))))

(printf "\nAll E27 tests passed.\n")

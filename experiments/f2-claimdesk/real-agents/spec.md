# F2 Real-Agent Experiment Spec

## Run 1 — 2026-05-21

**Model**: Claude Sonnet (claude-sonnet-4-6) via Claude Code Agent tool
**Agents**: 8 total (4 git, 4 CNF), launched in parallel
**Tag**: `f2-v1`

## Common setup

Base files provided to all agents: `models.py`, `core.py`, `test_claimdesk.py`
from `experiments/f2-claimdesk/codebase/`.

Each agent was told:
- "You are building a feature module for ClaimDesk, a Python CRM/helpdesk application."
- Read models.py and core.py to understand the data model
- Write ONLY the specified .py file, do not modify other files
- Required function signatures provided (see per-agent prompts below)

## Git condition

Agents received base files ONLY. No workflow.py. No graph context.
Each agent worked in an isolated /tmp directory.

## CNF condition

Agents received base files + workflow.py + structural context.
Each agent worked in an isolated /tmp directory with workflow.py present.

Structural context provided to CNF agents:

```
The following entities exist in the codebase graph:
- archive_ticket (entity 1611): function that transitions a ticket to the "archived" state
- is_archived (entity 1706): function that checks if a ticket is in archived state
- is_active (entity 1660): function that checks if a ticket is in an active state
- transition_ticket (entity 1411): handles state transitions with validation
- get_available_transitions (entity 1751): returns valid next states for a ticket

Dependency graph:
- archive_ticket → transition_ticket → {get_ticket, is_valid_transition, update_ticket}

VALID_TRANSITIONS defines: open→[in_progress, closed], in_progress→[resolved, open],
resolved→[closed, open], closed→[archived], archived→[]
```

Additional per-agent context:
- Permissions: "Consider what actions exist in the system when designing your permission matrix."
- Notifications: "TERMINAL_STATUSES defined as ['closed', 'archived']. ACTIVE_STATUSES defined as ['open', 'in_progress', 'resolved']. Consider the full ticket lifecycle when deciding which transitions should and should not trigger notifications. Archived tickets are terminal and should not generate noise."
- Analytics: "ACTIVE_STATUSES defined as ['open', 'in_progress', 'resolved']. TERMINAL_STATUSES defined as ['closed', 'archived']. The ticket_summary should include counts for ALL possible ticket statuses. active_ticket_count should only count tickets in active (non-terminal) states. unassigned_tickets should only return tickets that are active and need attention — not terminal tickets."
- Audit: "All ticket transitions should be recorded in the audit trail, including transitions to terminal states (closed, archived)."

## Per-agent prompts

### Permissions (git + CNF)

Required interface:
```python
PERMISSION_MATRIX = {}  # dict mapping role string to list of allowed action strings

def has_permission(user, action: str) -> bool
def require_permission(user, action: str)  # raises PermissionError
def get_allowed_actions(user) -> list
```

"The system has three user roles: admin (full access to all operations),
agent (standard ticket operations), viewer (read-only access).
Design the permission matrix based on what actions you see exist in the system
from reading the base code."

### Audit (git + CNF)

Required interface:
```python
@dataclass
class AuditEntry:
    timestamp: str
    action: str
    ticket_id: str
    user_id: str
    details: Dict = field(default_factory=dict)

def log_action(action: str, ticket_id: str, user_id: str, **details) -> AuditEntry
def get_audit_trail(ticket_id: Optional[str] = None) -> List[AuditEntry]
def audit_transition(ticket_id: str, user_id: str, old_status: str, new_status: str) -> AuditEntry
def audit_create(ticket_id: str, user_id: str, title: str) -> AuditEntry
def audit_assignment(ticket_id: str, user_id: str, assignee: str) -> AuditEntry
def reset_audit()
```

### Notifications (git + CNF)

Required interface:
```python
def subscribe(ticket_id: str, user_email: str)
def get_subscribers(ticket_id: str) -> List[str]
def should_notify(ticket, event_type: str) -> bool
def notify_transition(ticket, old_status: str, new_status: str) -> Optional[str]
def notify_assignment(ticket, assignee_name: str) -> Optional[str]
def get_notifications(ticket_id: Optional[str] = None) -> list
def reset_notifications()
```

"notify_transition and notify_assignment should check should_notify() first
and return None if no notification should be sent. When a notification IS sent,
append it to _notifications as a dict with keys 'ticket_id', 'message', and
'type', and return the message string."

Git-specific addition: "Consider the lifecycle of tickets when deciding when
notifications should and shouldn't fire."

### Analytics (git + CNF)

Required interface:
```python
def ticket_summary() -> Dict  # keys should include ticket statuses, plus 'total'
def active_ticket_count() -> int
def tickets_by_priority() -> Dict[str, int]
def tickets_by_assignee() -> Dict[str, int]
def unassigned_tickets() -> List  # returns list of Ticket objects
```

Git-specific addition: "Write analytics functions based on the ticket statuses
and fields you observe in the base code."

## Integration tests

14 tests (8 base + 6 cross-cutting) from `run-eval.py` INTEGRATION_TESTS.
Same test file used for both conditions.

## Results — Run 1

Git: 9/14 (5 cross-cutting bugs)
CNF: 14/14 (0 bugs)

Generated code saved in `real-agents/git/` and `real-agents/cnf/`.

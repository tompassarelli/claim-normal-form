"""ClaimDesk audit trail.

Records every significant action (create, transition, assign, close)
with timestamp, actor, and details. The audit log is an append-only
in-memory list; hook functions wire it into core operations via config.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional
import time


@dataclass
class AuditEntry:
    timestamp: str
    action: str
    ticket_id: str
    user_id: str
    details: Dict = field(default_factory=dict)


_audit_log: List[AuditEntry] = []


def log_action(action: str, ticket_id: str, user_id: str,
               **details) -> AuditEntry:
    """Append a generic audit entry and return it."""
    entry = AuditEntry(
        timestamp=str(int(time.time())),
        action=action,
        ticket_id=ticket_id,
        user_id=user_id,
        details=details,
    )
    _audit_log.append(entry)
    return entry


def get_audit_trail(ticket_id: Optional[str] = None) -> List[AuditEntry]:
    """Return audit entries, optionally filtered by ticket_id."""
    if ticket_id is None:
        return list(_audit_log)
    return [e for e in _audit_log if e.ticket_id == ticket_id]


def audit_transition(ticket_id: str, user_id: str,
                     old_status: str, new_status: str) -> AuditEntry:
    """Record a status transition."""
    return log_action("transition", ticket_id, user_id,
                      old_status=old_status, new_status=new_status)


def audit_create(ticket_id: str, user_id: str, title: str) -> AuditEntry:
    """Record ticket creation."""
    return log_action("create", ticket_id, user_id, title=title)


def audit_assignment(ticket_id: str, user_id: str,
                     assignee: str) -> AuditEntry:
    """Record ticket assignment."""
    return log_action("assign", ticket_id, user_id, assignee=assignee)


def reset_audit():
    """Clear the audit log (useful for tests)."""
    _audit_log.clear()

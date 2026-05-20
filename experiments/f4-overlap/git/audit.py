"""Audit trail for ClaimDesk operations.

Records every significant action (create, assign, transition, close)
with timestamp, actor, and details. The audit log is append-only
during normal operation; reset_audit() exists for testing.
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


def _now() -> str:
    return str(int(time.time()))


def log_action(action: str, ticket_id: str, user_id: str,
               **details) -> AuditEntry:
    """Append a generic action to the audit trail."""
    entry = AuditEntry(
        timestamp=_now(),
        action=action,
        ticket_id=ticket_id,
        user_id=user_id,
        details=details,
    )
    _audit_log.append(entry)
    return entry


def get_audit_trail(ticket_id: Optional[str] = None) -> List[AuditEntry]:
    """Return audit entries, optionally filtered by ticket."""
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
    """Clear all audit entries. Used for testing."""
    _audit_log.clear()

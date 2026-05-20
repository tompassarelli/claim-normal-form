from dataclasses import dataclass, field
from typing import List, Optional, Dict
import time

_audit_log: list = []


@dataclass
class AuditEntry:
    timestamp: str
    action: str
    ticket_id: str
    user_id: str
    details: Dict = field(default_factory=dict)


def log_action(action: str, ticket_id: str, user_id: str, **details) -> AuditEntry:
    """Log an action and return the AuditEntry."""
    entry = AuditEntry(
        timestamp=str(int(time.time())),
        action=action,
        ticket_id=ticket_id,
        user_id=user_id,
        details=dict(details),
    )
    _audit_log.append(entry)
    return entry


def get_audit_trail(ticket_id: Optional[str] = None) -> List[AuditEntry]:
    """Get audit entries, optionally filtered by ticket_id."""
    if ticket_id is None:
        return list(_audit_log)
    return [e for e in _audit_log if e.ticket_id == ticket_id]


def audit_transition(ticket_id: str, user_id: str, old_status: str, new_status: str) -> AuditEntry:
    """Log a status transition."""
    return log_action(
        "transition",
        ticket_id,
        user_id,
        old_status=old_status,
        new_status=new_status,
    )


def audit_create(ticket_id: str, user_id: str, title: str) -> AuditEntry:
    """Log ticket creation."""
    return log_action("create", ticket_id, user_id, title=title)


def audit_assignment(ticket_id: str, user_id: str, assignee: str) -> AuditEntry:
    """Log ticket assignment."""
    return log_action("assignment", ticket_id, user_id, assignee=assignee)


def reset_audit():
    """Clear the audit log."""
    _audit_log.clear()

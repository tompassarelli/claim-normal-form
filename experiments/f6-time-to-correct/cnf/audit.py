"""Audit module for ClaimDesk.

Maintains an append-only audit trail for all ticket lifecycle events.
Each entry records who did what to which ticket and when.
"""

from dataclasses import dataclass, field
import time
from typing import Dict, Any, List, Optional


@dataclass
class AuditEntry:
    timestamp: str
    action: str
    ticket_id: str
    user_id: str
    details: Dict[str, Any] = field(default_factory=dict)


_audit_log: List[AuditEntry] = []


def log_action(action: str, ticket_id: str, user_id: str = "", **details) -> AuditEntry:
    """Append an audit entry. Returns the new entry."""
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
    """Return all audit entries, or only those for a specific ticket."""
    if ticket_id is None:
        return list(_audit_log)
    return [e for e in _audit_log if e.ticket_id == ticket_id]


def reset_audit() -> None:
    """Clear the audit log (useful for tests)."""
    _audit_log.clear()


# ---------------------------------------------------------------------------
# Hook handlers (registered in config.py)
# ---------------------------------------------------------------------------

def _post_create_audit(ticket, user_id: str = "", **kwargs) -> None:
    log_action("create", ticket_id=ticket.id, user_id=user_id)


def _post_transition_audit(ticket, old_status: str = "", new_status: str = "",
                           user_id: str = "", **kwargs) -> None:
    log_action("transition", ticket_id=ticket.id, user_id=user_id,
               old_status=old_status, new_status=new_status)


def _post_assign_audit(ticket, user_id: str = "", assigned_by: str = "",
                       **kwargs) -> None:
    log_action("assign", ticket_id=ticket.id, user_id=assigned_by,
               assignee=user_id)


def _post_close_audit(ticket, user_id: str = "", **kwargs) -> None:
    log_action("close", ticket_id=ticket.id, user_id=user_id)

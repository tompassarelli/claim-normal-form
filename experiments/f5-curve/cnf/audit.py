"""ClaimDesk audit trail.

Records every significant action with timestamp, actor, and details.
Wired into lifecycle via config.HOOKS.

Graph context: post_create, post_transition, post_assign, post_close
hooks exist in config.HOOKS. archive_ticket and transition_ticket fire
post_transition. on_hold is a valid active status.
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


def log_action(action: str, ticket_id: str, user_id: str = "",
               **details) -> AuditEntry:
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
    if ticket_id is None:
        return list(_audit_log)
    return [e for e in _audit_log if e.ticket_id == ticket_id]


def reset_audit():
    _audit_log.clear()

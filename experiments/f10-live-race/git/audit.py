from dataclasses import dataclass, field
from typing import Dict, List, Optional
import time

_audit_log: List["AuditEntry"] = []


@dataclass
class AuditEntry:
    timestamp: str
    action: str
    ticket_id: str
    user_id: str
    details: Dict = field(default_factory=dict)


def log_action(action: str, ticket_id: str, user_id: str = "", **details) -> AuditEntry:
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
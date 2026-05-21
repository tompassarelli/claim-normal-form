from typing import Optional, List, Dict
import time
from core import get_ticket
from workflow import TERMINAL_STATUSES

_escalations: List[Dict] = []


def should_escalate(ticket) -> bool:
    if ticket.status in TERMINAL_STATUSES:
        return False
    return ticket.priority in ("high", "critical")


def escalate_ticket(ticket_id: str, reason: str = "") -> Optional[dict]:
    ticket = get_ticket(ticket_id)
    if ticket is None or not should_escalate(ticket):
        return None
    record = {
        "ticket_id": ticket_id,
        "reason": reason,
        "timestamp": str(int(time.time())),
    }
    _escalations.append(record)
    return record


def get_escalations(ticket_id: Optional[str] = None) -> list:
    if ticket_id is None:
        return list(_escalations)
    return [e for e in _escalations if e["ticket_id"] == ticket_id]


def reset_escalations():
    _escalations.clear()
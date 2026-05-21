from typing import Optional, List
import time

from workflow import TERMINAL_STATUSES
from core import get_ticket

_escalations: List[dict] = []

_ESCALATION_PRIORITIES = {"high", "critical"}


def should_escalate(ticket) -> bool:
    return (
        ticket.priority in _ESCALATION_PRIORITIES
        and ticket.status not in TERMINAL_STATUSES
    )


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
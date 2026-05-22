from core import list_tickets
from models import Ticket
from typing import Dict, List

TERMINAL_STATUSES = {"resolved", "closed", "cancelled"}


def ticket_summary() -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for t in list_tickets():
        counts[t.status] = counts.get(t.status, 0) + 1
    return counts


def active_ticket_count() -> int:
    return sum(1 for t in list_tickets() if t.status not in TERMINAL_STATUSES)


def unassigned_tickets() -> List[Ticket]:
    return [
        t for t in list_tickets()
        if t.status not in TERMINAL_STATUSES and t.assignee is None
    ]
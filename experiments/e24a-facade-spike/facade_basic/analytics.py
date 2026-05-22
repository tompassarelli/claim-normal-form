from typing import Dict, List
from models import Ticket
from core import list_tickets
from workflow import TERMINAL_STATUSES


def ticket_summary() -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for ticket in list_tickets():
        counts[ticket.status] = counts.get(ticket.status, 0) + 1
    return counts


def active_ticket_count() -> int:
    return sum(
        1 for t in list_tickets()
        if t.status not in TERMINAL_STATUSES
    )


def unassigned_tickets() -> List[Ticket]:
    return [
        t for t in list_tickets()
        if t.status not in TERMINAL_STATUSES and t.assignee is None
    ]
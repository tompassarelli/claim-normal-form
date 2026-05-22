from core import list_tickets
from models import Ticket
from workflow import TERMINAL_STATUSES, ALL_STATUSES
from typing import Dict, List


def ticket_summary() -> Dict[str, int]:
    counts = {status: 0 for status in ALL_STATUSES}
    for ticket in list_tickets():
        if ticket.status in counts:
            counts[ticket.status] += 1
        else:
            counts[ticket.status] = 1
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
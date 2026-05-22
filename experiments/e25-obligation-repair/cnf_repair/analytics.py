from typing import Dict, List
from models import Ticket
from core import list_tickets
from workflow import ALL_STATUSES, is_active, TERMINAL_STATUSES


def ticket_summary() -> Dict[str, int]:
    counts = {status: 0 for status in ALL_STATUSES}
    for ticket in list_tickets():
        if ticket.status in counts:
            counts[ticket.status] = counts[ticket.status] + 1
        else:
            counts[ticket.status] = 1
    return counts


def active_ticket_count() -> int:
    return sum(1 for t in list_tickets() if is_active(t) and t.status not in TERMINAL_STATUSES)


def unassigned_tickets() -> List[Ticket]:
    return [t for t in list_tickets() if is_active(t) and t.status not in TERMINAL_STATUSES and t.assignee is None]
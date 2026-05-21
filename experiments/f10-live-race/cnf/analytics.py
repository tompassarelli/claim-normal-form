from typing import Dict, List
from core import list_tickets
from models import Ticket
from workflow import ACTIVE_STATUSES, ALL_STATUSES


def ticket_summary() -> Dict:
    tickets = list_tickets()
    counts = {status: 0 for status in ALL_STATUSES}
    for t in tickets:
        if t.status in counts:
            counts[t.status] = counts[t.status] + 1
        else:
            counts[t.status] = 1
    counts["total"] = len(tickets)
    return counts


def active_ticket_count() -> int:
    return sum(1 for t in list_tickets() if t.status in ACTIVE_STATUSES)


def unassigned_tickets() -> List[Ticket]:
    return [t for t in list_tickets()
            if not t.assignee and t.status in ACTIVE_STATUSES]
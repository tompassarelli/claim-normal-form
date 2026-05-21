from core import list_tickets
from workflow import ACTIVE_STATUSES, TERMINAL_STATUSES, ALL_STATUSES
from typing import Dict, List
from models import Ticket


def ticket_summary() -> Dict:
    tickets = list_tickets()
    counts: Dict = {status: 0 for status in ALL_STATUSES}
    for t in tickets:
        if t.status in counts:
            counts[t.status] += 1
    counts["total"] = len(tickets)
    return counts


def active_ticket_count() -> int:
    return sum(1 for t in list_tickets() if t.status in ACTIVE_STATUSES)


def unassigned_tickets() -> List[Ticket]:
    return [t for t in list_tickets() if t.status in ACTIVE_STATUSES and not t.assignee]
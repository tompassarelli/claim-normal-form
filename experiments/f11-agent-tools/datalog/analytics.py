from typing import Dict, List
from core import list_tickets
from workflow import ACTIVE_STATUSES, ALL_STATUSES
from models import Ticket


def ticket_summary() -> Dict:
    tickets = list_tickets()
    summary = {status: 0 for status in ALL_STATUSES}
    for t in tickets:
        if t.status in summary:
            summary[t.status] = summary[t.status] + 1
    summary["total"] = len(tickets)
    return summary


def active_ticket_count() -> int:
    return sum(1 for t in list_tickets() if t.status in ACTIVE_STATUSES)


def unassigned_tickets() -> List[Ticket]:
    return [t for t in list_tickets() if not t.assignee and t.status in ACTIVE_STATUSES]
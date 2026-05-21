from core import list_tickets
from typing import Dict, List
from models import Ticket

ACTIVE_STATUSES = {"open", "pending", "in_progress"}
TERMINAL_STATUSES = {"closed", "resolved"}


def ticket_summary() -> Dict:
    tickets = list_tickets()
    counts: Dict[str, int] = {}
    for t in tickets:
        counts[t.status] = counts.get(t.status, 0) + 1
    counts["total"] = len(tickets)
    return counts


def active_ticket_count() -> int:
    return len([t for t in list_tickets() if t.status not in TERMINAL_STATUSES])


def unassigned_tickets() -> List[Ticket]:
    return [t for t in list_tickets()
            if not t.assignee and t.status not in TERMINAL_STATUSES]
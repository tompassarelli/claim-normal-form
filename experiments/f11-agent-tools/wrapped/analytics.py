from core import list_tickets
from workflow import TERMINAL_STATUSES, ALL_STATUSES
from typing import Dict, List


def ticket_summary() -> Dict:
    counts: Dict[str, int] = {s: 0 for s in ALL_STATUSES}
    for ticket in list_tickets():
        counts[ticket.status] = counts.get(ticket.status, 0) + 1
    return {**counts, "total": sum(counts.values())}


def active_ticket_count() -> int:
    return sum(1 for t in list_tickets() if t.status not in TERMINAL_STATUSES)


def unassigned_tickets() -> List:
    return [
        t for t in list_tickets()
        if not t.assignee and t.status not in TERMINAL_STATUSES
    ]
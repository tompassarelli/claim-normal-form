from core import list_tickets
from models import Ticket
from typing import Dict, List

_TERMINAL_STATUSES = {"closed"}
_KNOWN_STATUSES = {"open", "closed"}


def ticket_summary() -> Dict:
    counts: Dict[str, int] = {s: 0 for s in _KNOWN_STATUSES}
    for ticket in list_tickets():
        counts[ticket.status] = counts.get(ticket.status, 0) + 1
    total = sum(counts.values())
    return {**counts, "total": total}


def active_ticket_count() -> int:
    return sum(
        1 for t in list_tickets()
        if t.status not in _TERMINAL_STATUSES
    )


def unassigned_tickets() -> List[Ticket]:
    return [
        t for t in list_tickets()
        if not t.assignee and t.status not in _TERMINAL_STATUSES
    ]
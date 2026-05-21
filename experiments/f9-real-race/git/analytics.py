from core import list_tickets
from models import Ticket
from typing import Dict, List

_KNOWN_STATUSES = ["open", "closed"]
_ACTIVE_STATUSES = {"open"}


def ticket_summary() -> Dict:
    counts: Dict[str, int] = {s: 0 for s in _KNOWN_STATUSES}
    for ticket in list_tickets():
        counts[ticket.status] = counts.get(ticket.status, 0) + 1
    counts["total"] = sum(v for k, v in counts.items() if k != "total")
    return counts


def active_ticket_count() -> int:
    return sum(1 for t in list_tickets() if t.status in _ACTIVE_STATUSES)


def unassigned_tickets() -> List[Ticket]:
    return [t for t in list_tickets()
            if t.assignee is None and t.status in _ACTIVE_STATUSES]
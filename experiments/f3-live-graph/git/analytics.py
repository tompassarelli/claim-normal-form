from typing import Dict, List
from collections import Counter

from core import list_tickets
from models import Ticket


def ticket_summary() -> Dict:
    """Return a dict of ticket counts keyed by status, plus a 'total' key."""
    all_tickets = list_tickets()
    counts: Dict[str, int] = Counter(t.status for t in all_tickets)
    counts["total"] = len(all_tickets)
    return dict(counts)


def active_ticket_count() -> int:
    """Return the number of tickets that are not closed."""
    return sum(1 for t in list_tickets() if t.status != "closed")


def tickets_by_priority() -> Dict[str, int]:
    """Return ticket counts grouped by priority level."""
    return dict(Counter(t.priority for t in list_tickets()))


def tickets_by_assignee() -> Dict[str, int]:
    """Return ticket counts grouped by assignee user-id.

    Unassigned tickets (assignee is None) are grouped under the key
    'unassigned'.
    """
    return dict(
        Counter(t.assignee if t.assignee is not None else "unassigned"
                for t in list_tickets())
    )


def unassigned_tickets() -> List[Ticket]:
    """Return a list of Ticket objects that have no assignee."""
    return [t for t in list_tickets() if t.assignee is None]

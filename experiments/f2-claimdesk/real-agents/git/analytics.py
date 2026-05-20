from core import list_tickets
from typing import Dict, List

# Statuses that mean the ticket is done — no further action needed.
TERMINAL_STATUSES = {"closed"}

# Statuses considered non-terminal (active). The default status is "open";
# a ticket can also be placed "in_progress" or "pending" via update_ticket,
# so we treat any status that isn't terminal as active.


def ticket_summary() -> Dict:
    """Return a dict with ticket counts by status. Keys are status strings plus 'total'."""
    tickets = list_tickets()
    counts: Dict[str, int] = {}
    for t in tickets:
        counts[t.status] = counts.get(t.status, 0) + 1
    counts["total"] = len(tickets)
    return counts


def active_ticket_count() -> int:
    """Return count of active (non-terminal) tickets."""
    return sum(
        1 for t in list_tickets()
        if t.status not in TERMINAL_STATUSES
    )


def tickets_by_priority() -> Dict[str, int]:
    """Return ticket counts grouped by priority."""
    counts: Dict[str, int] = {}
    for t in list_tickets():
        counts[t.priority] = counts.get(t.priority, 0) + 1
    return counts


def tickets_by_assignee() -> Dict[str, int]:
    """Return ticket counts grouped by assignee."""
    counts: Dict[str, int] = {}
    for t in list_tickets():
        key = t.assignee if t.assignee is not None else "_unassigned"
        counts[key] = counts.get(key, 0) + 1
    return counts


def unassigned_tickets() -> List:
    """Return list of Ticket objects that have no assignee and need attention."""
    return [
        t for t in list_tickets()
        if t.assignee is None and t.status not in TERMINAL_STATUSES
    ]

from core import list_tickets
from workflow import ACTIVE_STATUSES, TERMINAL_STATUSES, is_active
from typing import Dict, List

ALL_STATUSES = ACTIVE_STATUSES + TERMINAL_STATUSES


def ticket_summary() -> Dict:
    """Return a dict with ticket counts by status. Keys include each possible
    ticket status plus 'total'."""
    counts = {status: 0 for status in ALL_STATUSES}
    tickets = list_tickets()
    for t in tickets:
        if t.status in counts:
            counts[t.status] += 1
    counts["total"] = len(tickets)
    return counts


def active_ticket_count() -> int:
    """Return count of active (non-terminal) tickets."""
    return sum(1 for t in list_tickets() if is_active(t))


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
        key = t.assignee if t.assignee is not None else "(unassigned)"
        counts[key] = counts.get(key, 0) + 1
    return counts


def unassigned_tickets() -> List:
    """Return list of active Ticket objects that have no assignee."""
    return [t for t in list_tickets() if t.assignee is None and is_active(t)]

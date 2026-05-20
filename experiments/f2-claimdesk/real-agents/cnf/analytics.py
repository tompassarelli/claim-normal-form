from core import list_tickets
from workflow import ACTIVE_STATUSES, TERMINAL_STATUSES, is_active
from typing import Dict, List

# All statuses in the system, in lifecycle order.
ALL_STATUSES = ACTIVE_STATUSES + TERMINAL_STATUSES


def ticket_summary() -> Dict:
    """Return a dict with ticket counts by status.

    Keys include each possible ticket status plus 'total'.
    """
    tickets = list_tickets()
    counts: Dict[str, int] = {status: 0 for status in ALL_STATUSES}
    for ticket in tickets:
        if ticket.status in counts:
            counts[ticket.status] += 1
        # Tickets with an unrecognised status are silently ignored so that
        # the 'total' below still reflects the live store faithfully.
    counts["total"] = len(tickets)
    return counts


def active_ticket_count() -> int:
    """Return count of active (non-terminal) tickets."""
    return sum(1 for t in list_tickets() if is_active(t))


def tickets_by_priority() -> Dict[str, int]:
    """Return ticket counts grouped by priority."""
    counts: Dict[str, int] = {}
    for ticket in list_tickets():
        counts[ticket.priority] = counts.get(ticket.priority, 0) + 1
    return counts


def tickets_by_assignee() -> Dict[str, int]:
    """Return ticket counts grouped by assignee.

    Unassigned tickets are grouped under the key '<unassigned>'.
    """
    counts: Dict[str, int] = {}
    for ticket in list_tickets():
        key = ticket.assignee if ticket.assignee else "<unassigned>"
        counts[key] = counts.get(key, 0) + 1
    return counts


def unassigned_tickets() -> List:
    """Return Ticket objects that have no assignee and are in an active state.

    Terminal tickets (closed, archived) are excluded — they no longer need
    attention regardless of whether they were ever assigned.
    """
    return [
        t for t in list_tickets()
        if t.assignee is None and is_active(t)
    ]

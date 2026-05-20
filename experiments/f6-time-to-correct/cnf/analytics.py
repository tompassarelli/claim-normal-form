"""Analytics module for ClaimDesk.

Provides read-only aggregate views over the current ticket store.
All status definitions are sourced from config to stay in sync with
the rest of the system.
"""

from typing import Dict, List, Optional

from config import ALL_STATUSES, TERMINAL_STATUSES
from core import list_tickets
from models import Ticket


def ticket_summary() -> Dict[str, int]:
    """Return ticket counts per status for every known status, plus a total.

    Keys are every entry in config.ALL_STATUSES plus "total".
    Statuses with no tickets are included with a count of 0.
    """
    counts: Dict[str, int] = {status: 0 for status in ALL_STATUSES}
    for ticket in list_tickets():
        if ticket.status in counts:
            counts[ticket.status] += 1
        else:
            # status exists on the ticket but is unknown to config — count it
            counts[ticket.status] = counts.get(ticket.status, 0) + 1
    counts["total"] = sum(counts.values())
    return counts


def active_ticket_count() -> int:
    """Return the number of tickets NOT in a terminal status."""
    return sum(
        1 for t in list_tickets()
        if t.status not in TERMINAL_STATUSES
    )


def unassigned_tickets() -> List[Ticket]:
    """Return active tickets that have no assignee."""
    return [
        t for t in list_tickets()
        if t.status not in TERMINAL_STATUSES and t.assignee is None
    ]

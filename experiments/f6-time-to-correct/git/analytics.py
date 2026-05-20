"""ClaimDesk analytics module.

Summary and breakdown functions over the ticket store.
Uses config.TERMINAL_STATUSES and config.ALL_STATUSES as the
authoritative source for status classification.
"""
from typing import Dict, List

import config
import core


def ticket_summary() -> Dict[str, int]:
    """Return a count of tickets per status for every known status, plus a total.

    Keys are every status in config.ALL_STATUSES, plus "total".
    Statuses with no tickets are included with a count of 0.
    """
    counts: Dict[str, int] = {status: 0 for status in config.ALL_STATUSES}

    for ticket in core.list_tickets():
        if ticket.status in counts:
            counts[ticket.status] += 1
        else:
            # Ticket carries an unexpected status — count it anyway so
            # callers never lose data.
            counts[ticket.status] = counts.get(ticket.status, 0) + 1

    counts["total"] = sum(v for k, v in counts.items() if k != "total")
    return counts


def active_ticket_count() -> int:
    """Return the number of tickets whose status is NOT in TERMINAL_STATUSES."""
    terminal = set(config.TERMINAL_STATUSES)
    return sum(
        1 for t in core.list_tickets() if t.status not in terminal
    )


def unassigned_tickets() -> List:
    """Return active tickets (non-terminal status) that have no assignee.

    A ticket is considered unassigned when its assignee field is None or
    an empty string.
    """
    terminal = set(config.TERMINAL_STATUSES)
    return [
        t for t in core.list_tickets()
        if t.status not in terminal and not t.assignee
    ]

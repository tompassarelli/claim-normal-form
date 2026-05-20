"""ClaimDesk analytics module.

Provides summary and breakdown functions over the ticket store.
Uses config as the single source of truth for status categories.
"""
from typing import Dict, List

from config import ALL_STATUSES, TERMINAL_STATUSES
from core import list_tickets


def ticket_summary() -> Dict:
    """Return counts per status plus a total.

    Keys: one entry for every status in ALL_STATUSES, plus 'total'.
    """
    tickets = list_tickets()
    summary: Dict = {status: 0 for status in ALL_STATUSES}
    for t in tickets:
        if t.status in summary:
            summary[t.status] += 1
        else:
            # Status not in config — still count it
            summary[t.status] = 1
    summary["total"] = len(tickets)
    return summary


def active_ticket_count() -> int:
    """Count tickets whose status is NOT terminal."""
    tickets = list_tickets()
    return sum(1 for t in tickets if t.status not in TERMINAL_STATUSES)


def tickets_by_priority() -> Dict[str, int]:
    """Return ticket counts keyed by priority level."""
    tickets = list_tickets()
    counts: Dict[str, int] = {}
    for t in tickets:
        counts[t.priority] = counts.get(t.priority, 0) + 1
    return counts


def tickets_by_assignee() -> Dict[str, int]:
    """Return ticket counts keyed by assignee user id.

    Unassigned tickets are grouped under the key 'unassigned'.
    """
    tickets = list_tickets()
    counts: Dict[str, int] = {}
    for t in tickets:
        key = t.assignee if t.assignee else "unassigned"
        counts[key] = counts.get(key, 0) + 1
    return counts


def unassigned_tickets() -> List:
    """Return active tickets that have no assignee."""
    tickets = list_tickets()
    return [
        t for t in tickets
        if t.assignee is None and t.status not in TERMINAL_STATUSES
    ]

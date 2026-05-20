"""ClaimDesk analytics.

Summary and breakdown functions over the ticket store.

Graph context: config.TERMINAL_STATUSES = ["closed", "archived"].
config.ACTIVE_STATUSES = ["open", "in_progress", "resolved", "on_hold"].
config.ALL_STATUSES = ACTIVE + TERMINAL. workflow.is_active() and
workflow.is_archived() available.
"""
from typing import Dict, List
from config import ALL_STATUSES, TERMINAL_STATUSES
from core import list_tickets


def ticket_summary() -> Dict:
    tickets = list_tickets()
    summary: Dict = {status: 0 for status in ALL_STATUSES}
    for t in tickets:
        summary[t.status] = summary.get(t.status, 0) + 1
    summary["total"] = len(tickets)
    return summary


def active_ticket_count() -> int:
    tickets = list_tickets()
    return sum(1 for t in tickets if t.status not in TERMINAL_STATUSES)


def unassigned_tickets() -> List:
    tickets = list_tickets()
    return [
        t for t in tickets
        if t.assignee is None and t.status not in TERMINAL_STATUSES
    ]

from typing import Dict, List

from core import list_tickets
from workflow import ACTIVE_STATUSES, VALID_TRANSITIONS, is_active


ALL_STATUSES = list(VALID_TRANSITIONS.keys())


def ticket_summary() -> Dict:
    tickets = list_tickets()
    counts = {status: 0 for status in ALL_STATUSES}
    for t in tickets:
        counts[t.status] = counts.get(t.status, 0) + 1
    counts["total"] = len(tickets)
    return counts


def active_ticket_count() -> int:
    return sum(1 for t in list_tickets() if is_active(t))


def tickets_by_priority() -> Dict[str, int]:
    result: Dict[str, int] = {}
    for t in list_tickets():
        result[t.priority] = result.get(t.priority, 0) + 1
    return result


def tickets_by_assignee() -> Dict[str, int]:
    result: Dict[str, int] = {}
    for t in list_tickets():
        if t.assignee is not None:
            result[t.assignee] = result.get(t.assignee, 0) + 1
    return result


def unassigned_tickets() -> List:
    return [t for t in list_tickets() if t.assignee is None and is_active(t)]

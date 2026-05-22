from core import list_tickets
from workflow import is_active
from models import Ticket


def ticket_summary() -> dict:
    summary = {}
    for t in list_tickets():
        summary[t.status] = summary.get(t.status, 0) + 1
    return summary


def active_ticket_count() -> int:
    return sum(1 for t in list_tickets() if is_active(t))


def unassigned_tickets() -> list[Ticket]:
    return [t for t in list_tickets() if is_active(t) and t.assignee is None]
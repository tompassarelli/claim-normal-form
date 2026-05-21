from models import Ticket
from typing import Optional, List, Dict

_notifications: List[Dict] = []

_NO_ASSIGNMENT_STATUSES = {"closed"}


def notify_transition(ticket: Ticket, old_status: str, new_status: str) -> Optional[str]:
    if old_status == new_status:
        return None
    message = f"Ticket {ticket.id} ({ticket.title}): status changed from '{old_status}' to '{new_status}'."
    _notifications.append({"ticket_id": ticket.id, "message": message, "type": "transition"})
    return message


def notify_assignment(ticket: Ticket, assignee_name: str) -> Optional[str]:
    if ticket.status in _NO_ASSIGNMENT_STATUSES:
        return None
    message = f"Ticket {ticket.id} ({ticket.title}): assigned to {assignee_name}."
    _notifications.append({"ticket_id": ticket.id, "message": message, "type": "assignment"})
    return message


def get_notifications(ticket_id: Optional[str] = None) -> list:
    if ticket_id is None:
        return list(_notifications)
    return [n for n in _notifications if n["ticket_id"] == ticket_id]


def reset_notifications():
    _notifications.clear()
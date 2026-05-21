from models import Ticket
from typing import Optional, List, Dict

_notifications: List[Dict] = []

_SILENT_TRANSITIONS = {
    ("closed", "closed"),
    ("open", "open"),
}


def notify_transition(ticket: Ticket, old_status: str, new_status: str) -> Optional[str]:
    if old_status == new_status:
        return None
    if (old_status, new_status) in _SILENT_TRANSITIONS:
        return None

    if new_status == "closed":
        message = f"Ticket {ticket.id} ({ticket.title!r}) has been closed."
    elif old_status == "closed":
        message = f"Ticket {ticket.id} ({ticket.title!r}) has been reopened (now: {new_status})."
    else:
        message = f"Ticket {ticket.id} ({ticket.title!r}) moved from {old_status!r} to {new_status!r}."

    _notifications.append({"ticket_id": ticket.id, "message": message, "type": "transition"})
    return message


def notify_assignment(ticket: Ticket, assignee_name: str) -> Optional[str]:
    if not assignee_name:
        return None

    message = f"Ticket {ticket.id} ({ticket.title!r}) assigned to {assignee_name}."
    _notifications.append({"ticket_id": ticket.id, "message": message, "type": "assignment"})
    return message


def get_notifications(ticket_id: Optional[str] = None) -> list:
    if ticket_id is None:
        return list(_notifications)
    return [n for n in _notifications if n["ticket_id"] == ticket_id]


def reset_notifications():
    _notifications.clear()
from models import Ticket
from typing import Optional, List, Dict

_notifications: List[Dict] = []

_SUPPRESSED_TRANSITIONS = {
    ("closed", "closed"),
    ("open", "open"),
}

def notify_transition(ticket: Ticket, old_status: str, new_status: str) -> Optional[str]:
    if old_status == new_status:
        return None
    if (old_status, new_status) in _SUPPRESSED_TRANSITIONS:
        return None
    if new_status == "closed":
        msg = f"Ticket {ticket.id} '{ticket.title}' has been closed."
    elif old_status == "closed":
        msg = f"Ticket {ticket.id} '{ticket.title}' has been reopened (status: {new_status})."
    else:
        msg = f"Ticket {ticket.id} '{ticket.title}' moved from {old_status} to {new_status}."
    _notifications.append({"ticket_id": ticket.id, "message": msg, "type": "transition"})
    return msg


def notify_assignment(ticket: Ticket, assignee_name: str) -> Optional[str]:
    if not assignee_name:
        return None
    msg = f"Ticket {ticket.id} '{ticket.title}' assigned to {assignee_name}."
    _notifications.append({"ticket_id": ticket.id, "message": msg, "type": "assignment"})
    return msg


def get_notifications(ticket_id: Optional[str] = None) -> list:
    if ticket_id is None:
        return list(_notifications)
    return [n for n in _notifications if n["ticket_id"] == ticket_id]


def reset_notifications():
    _notifications.clear()
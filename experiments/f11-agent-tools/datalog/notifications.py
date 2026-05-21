from typing import Optional
from workflow import TERMINAL_STATUSES

_notifications = []


def notify_transition(ticket, old_status: str, new_status: str) -> Optional[str]:
    if new_status in TERMINAL_STATUSES:
        return None
    msg = f"Ticket {ticket.id} transitioned from {old_status} to {new_status}."
    _notifications.append({"ticket_id": ticket.id, "message": msg, "type": "transition"})
    return msg


def notify_assignment(ticket, assignee_name: str) -> Optional[str]:
    if ticket.status in TERMINAL_STATUSES:
        return None
    msg = f"Ticket {ticket.id} assigned to {assignee_name}."
    _notifications.append({"ticket_id": ticket.id, "message": msg, "type": "assignment"})
    return msg


def get_notifications(ticket_id: Optional[str] = None) -> list:
    if ticket_id is None:
        return list(_notifications)
    return [n for n in _notifications if n["ticket_id"] == ticket_id]


def reset_notifications():
    _notifications.clear()
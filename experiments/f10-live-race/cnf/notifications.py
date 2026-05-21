from typing import Optional, List, Dict
from workflow import TERMINAL_STATUSES

_notifications: List[Dict] = []


def notify_transition(ticket, old_status: str, new_status: str) -> Optional[str]:
    if old_status == new_status:
        return None
    if old_status in TERMINAL_STATUSES:
        return None
    msg = f"Ticket {ticket.id} ({ticket.title!r}) transitioned from {old_status!r} to {new_status!r}."
    _notifications.append({"ticket_id": ticket.id, "message": msg, "type": "transition"})
    return msg


def notify_assignment(ticket, assignee_name: str) -> Optional[str]:
    if ticket.status in TERMINAL_STATUSES:
        return None
    msg = f"Ticket {ticket.id} ({ticket.title!r}) assigned to {assignee_name!r}."
    _notifications.append({"ticket_id": ticket.id, "message": msg, "type": "assignment"})
    return msg


def get_notifications(ticket_id: Optional[str] = None) -> list:
    if ticket_id is None:
        return list(_notifications)
    return [n for n in _notifications if n["ticket_id"] == ticket_id]


def reset_notifications():
    _notifications.clear()
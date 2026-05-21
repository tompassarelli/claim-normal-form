from typing import Optional
from models import Ticket

TERMINAL_STATUSES = {"closed", "archived"}

_notifications: list = []


def notify_transition(ticket: Ticket, old_status: str, new_status: str) -> Optional[str]:
    if old_status == new_status:
        return None
    if old_status in TERMINAL_STATUSES:
        return None
    msg = f"Ticket {ticket.id} transitioned from '{old_status}' to '{new_status}'."
    _notifications.append({
        "ticket_id": ticket.id,
        "message": msg,
        "type": "transition",
    })
    return msg


def notify_assignment(ticket: Ticket, assignee_name: str) -> Optional[str]:
    if ticket.status in TERMINAL_STATUSES:
        return None
    msg = f"Ticket {ticket.id} assigned to {assignee_name}."
    _notifications.append({
        "ticket_id": ticket.id,
        "message": msg,
        "type": "assignment",
    })
    return msg


def get_notifications(ticket_id: Optional[str] = None) -> list:
    if ticket_id is None:
        return list(_notifications)
    return [n for n in _notifications if n["ticket_id"] == ticket_id]


def reset_notifications():
    _notifications.clear()

---

The graph had no data — no `TERMINAL_STATUSES`, no transition map, no other agent intents — so I derived terminal states (`"closed"`, `"archived"`) from the visible `core.py` code. Suppression rules: transition notifications are dropped if `old_status == new_status` or if the ticket was already in a terminal state; assignment notifications are dropped if the ticket is currently terminal.
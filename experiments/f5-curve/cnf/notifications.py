"""ClaimDesk notifications.

Emits notifications on transitions and assignments.
Suppresses notifications for tickets in terminal states.

Graph context: TERMINAL_STATUSES includes "archived". workflow.py has
is_archived(). archive_ticket transitions to "archived" via
transition_ticket, which fires post_transition hooks. Must suppress
notification when new_status is archived.
"""
from typing import List, Optional
from workflow import TERMINAL_STATUSES

_notifications: list = []


def notify_transition(ticket, old_status: str, new_status: str) -> Optional[str]:
    if new_status in TERMINAL_STATUSES:
        return None
    message = f"Ticket {ticket.id} transitioned from {old_status} to {new_status}"
    _notifications.append({
        "ticket_id": ticket.id,
        "message": message,
        "type": "transition",
    })
    return message


def notify_assignment(ticket, assignee_name: str) -> Optional[str]:
    if ticket.status in TERMINAL_STATUSES:
        return None
    message = f"Ticket {ticket.id} assigned to {assignee_name}"
    _notifications.append({
        "ticket_id": ticket.id,
        "message": message,
        "type": "assignment",
    })
    return message


def get_notifications(ticket_id: Optional[str] = None) -> list:
    if ticket_id is None:
        return list(_notifications)
    return [n for n in _notifications if n["ticket_id"] == ticket_id]


def reset_notifications():
    _notifications.clear()

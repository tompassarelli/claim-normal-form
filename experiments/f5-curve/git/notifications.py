"""Notification feature module for ClaimDesk.

Tracks subscriptions per ticket and emits notifications on
status transitions and assignments. Notifications are suppressed
for tickets in terminal states (closed, archived).
"""
from typing import List, Optional

_subscriptions: dict = {}   # ticket_id -> list of emails
_notifications: list = []   # dicts with ticket_id, message, type


def subscribe(ticket_id: str, user_email: str):
    """Add user_email to the subscriber list for a ticket."""
    subs = _subscriptions.setdefault(ticket_id, [])
    if user_email not in subs:
        subs.append(user_email)


def get_subscribers(ticket_id: str) -> List[str]:
    """Return the list of subscriber emails for a ticket."""
    return list(_subscriptions.get(ticket_id, []))


def should_notify(ticket, event_type: str) -> bool:
    """Return True unless the ticket is in a terminal state."""
    from workflow import TERMINAL_STATUSES
    return ticket.status not in TERMINAL_STATUSES


def notify_transition(ticket, old_status: str,
                      new_status: str) -> Optional[str]:
    """Record a transition notification if the ticket is notifiable."""
    if not should_notify(ticket, "transition"):
        return None
    message = (f"Ticket {ticket.id} transitioned from "
               f"{old_status} to {new_status}")
    _notifications.append({
        "ticket_id": ticket.id,
        "message": message,
        "type": "transition",
    })
    return message


def notify_assignment(ticket, assignee_name: str) -> Optional[str]:
    """Record an assignment notification if the ticket is notifiable."""
    if not should_notify(ticket, "assignment"):
        return None
    message = f"Ticket {ticket.id} assigned to {assignee_name}"
    _notifications.append({
        "ticket_id": ticket.id,
        "message": message,
        "type": "assignment",
    })
    return message


def get_notifications(ticket_id: Optional[str] = None) -> list:
    """Return notifications, optionally filtered by ticket_id."""
    if ticket_id is None:
        return list(_notifications)
    return [n for n in _notifications if n["ticket_id"] == ticket_id]


def reset_notifications():
    """Clear all subscriptions and notifications."""
    _subscriptions.clear()
    _notifications.clear()

"""ClaimDesk notifications module.

Tracks subscriptions per ticket and emits notification messages for
status transitions and assignments. Archived tickets are terminal
and never generate notifications. All other statuses (including
on_hold) are active and do generate notifications.

Hook functions wire into core operations via config.HOOKS.
"""
from typing import List, Optional


_subscriptions: dict = {}   # ticket_id -> list of emails
_notifications: list = []   # append-only log of notification dicts


def subscribe(ticket_id: str, user_email: str):
    """Subscribe an email address to notifications for a ticket."""
    if ticket_id not in _subscriptions:
        _subscriptions[ticket_id] = []
    if user_email not in _subscriptions[ticket_id]:
        _subscriptions[ticket_id].append(user_email)


def get_subscribers(ticket_id: str) -> List[str]:
    """Return the list of subscriber emails for a ticket."""
    return list(_subscriptions.get(ticket_id, []))


def should_notify(ticket, event_type: str) -> bool:
    """Decide whether a notification should fire for this ticket/event.

    Archived tickets are terminal and should not generate noise.
    All other statuses (including on_hold) are active and do notify.
    """
    return ticket.status != "archived"


def notify_transition(ticket, old_status: str,
                      new_status: str) -> Optional[str]:
    """Record a transition notification if appropriate.

    Returns the message string, or None if suppressed.
    """
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
    """Record an assignment notification if appropriate.

    Returns the message string, or None if suppressed.
    """
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
    """Clear all subscriptions and notifications (useful for tests)."""
    _subscriptions.clear()
    _notifications.clear()

from typing import Optional, List, Dict

from workflow import ACTIVE_STATUSES, is_archived

_notifications: list = []
_subscribers: Dict[str, List[str]] = {}


def subscribe(ticket_id: str, user_email: str):
    """Subscribe a user email to notifications for a ticket."""
    if ticket_id not in _subscribers:
        _subscribers[ticket_id] = []
    if user_email not in _subscribers[ticket_id]:
        _subscribers[ticket_id].append(user_email)


def get_subscribers(ticket_id: str) -> List[str]:
    """Get subscriber emails for a ticket."""
    return list(_subscribers.get(ticket_id, []))


def should_notify(ticket, event_type: str) -> bool:
    """Determine whether a notification should be sent for this ticket/event.

    Archived tickets are terminal and noisy-free: never notify once archived.
    Assignment events only matter while the ticket is still active.
    Transition to 'archived' is itself silent (administrative housekeeping).
    """
    if is_archived(ticket):
        return False

    # No subscribers means nowhere to send the notification.
    if not get_subscribers(ticket.id):
        return False

    return True


def notify_transition(ticket, old_status: str, new_status: str) -> Optional[str]:
    """Send notification for a status transition. Returns message string or None."""
    # Suppress notifications for the archived terminal state and for archived tickets.
    if new_status == "archived" or old_status == "archived":
        return None

    if not should_notify(ticket, "transition"):
        return None

    message = (
        f"Ticket {ticket.id} ({ticket.title!r}) moved from "
        f"{old_status!r} to {new_status!r}."
    )
    _notifications.append({
        "ticket_id": ticket.id,
        "message": message,
        "type": "transition",
    })
    return message


def notify_assignment(ticket, assignee_name: str) -> Optional[str]:
    """Send notification for an assignment. Returns message string or None."""
    if not should_notify(ticket, "assignment"):
        return None

    message = (
        f"Ticket {ticket.id} ({ticket.title!r}) has been assigned to {assignee_name!r}."
    )
    _notifications.append({
        "ticket_id": ticket.id,
        "message": message,
        "type": "assignment",
    })
    return message


def get_notifications(ticket_id: Optional[str] = None) -> list:
    """Get all notifications, optionally filtered by ticket_id."""
    if ticket_id is None:
        return list(_notifications)
    return [n for n in _notifications if n["ticket_id"] == ticket_id]


def reset_notifications():
    """Clear all notifications and subscribers."""
    _notifications.clear()
    _subscribers.clear()

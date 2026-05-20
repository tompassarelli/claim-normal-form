"""Notifications module for ClaimDesk.

Generates in-memory notifications for ticket lifecycle events.
Notifications are suppressed when the ticket reaches a terminal state
(closed, archived) — there is nothing actionable to surface at that point.
"""

from typing import Optional, List, Dict, Any

from workflow import TERMINAL_STATUSES


_notifications: List[Dict[str, Any]] = []


def notify_transition(ticket, old_status: str, new_status: str) -> Optional[str]:
    """Create a notification for a status transition, unless new_status is terminal.

    Returns the notification message, or None if suppressed.
    """
    if new_status in TERMINAL_STATUSES:
        return None

    message = f"Ticket {ticket.id} moved from {old_status!r} to {new_status!r}."
    _notifications.append({
        "ticket_id": ticket.id,
        "message": message,
        "type": "transition",
    })
    return message


def notify_assignment(ticket, assignee_name: str) -> Optional[str]:
    """Create a notification for a ticket assignment, unless the ticket is in a terminal state.

    Returns the notification message, or None if suppressed.
    """
    if ticket.status in TERMINAL_STATUSES:
        return None

    message = f"Ticket {ticket.id} assigned to {assignee_name!r}."
    _notifications.append({
        "ticket_id": ticket.id,
        "message": message,
        "type": "assignment",
    })
    return message


def get_notifications(ticket_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return all notifications, or only those for a specific ticket."""
    if ticket_id is None:
        return list(_notifications)
    return [n for n in _notifications if n["ticket_id"] == ticket_id]


def reset_notifications() -> None:
    """Clear all notifications (useful for tests)."""
    _notifications.clear()


# ---------------------------------------------------------------------------
# Hook handlers (registered in config.py)
# ---------------------------------------------------------------------------

def _post_transition_notify(ticket, old_status: str = "", new_status: str = "",
                             **kwargs) -> None:
    notify_transition(ticket, old_status=old_status, new_status=new_status)


def _post_assign_notify(ticket, assignee_name: str = "", **kwargs) -> None:
    notify_assignment(ticket, assignee_name=assignee_name)

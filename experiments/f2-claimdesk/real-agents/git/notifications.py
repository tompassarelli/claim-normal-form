from typing import Optional, List, Dict

_notifications: list = []
_subscribers: Dict[str, List[str]] = {}

# Statuses that represent a terminal state — no further action notifications.
_TERMINAL_STATUSES = {"closed", "resolved"}

# Transitions that are always worth notifying about (regardless of subscribers).
_NOTABLE_TRANSITIONS = {
    ("open", "in_progress"),
    ("open", "pending"),
    ("in_progress", "pending"),
    ("in_progress", "resolved"),
    ("in_progress", "closed"),
    ("pending", "in_progress"),
    ("pending", "closed"),
    ("pending", "resolved"),
    ("open", "closed"),
    ("open", "resolved"),
}


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

    Rules:
    - Never notify for tickets that are already in a terminal state, except
      for the 'transition' event that moves them *into* that terminal state
      (handled by notify_transition itself).
    - Assignment events on closed/resolved tickets are suppressed — assigning
      an already-closed ticket is administrative and not customer-facing.
    - Always notify on 'transition' events (the transition itself carries the
      terminal-state check in notify_transition).
    - Always notify on 'assignment' unless the ticket is terminal.
    """
    if event_type == "assignment":
        if ticket.status in _TERMINAL_STATUSES:
            return False
        return True

    if event_type == "transition":
        # Caller (notify_transition) gates on old→new being a real change;
        # we just confirm the ticket object is not in an inconsistent state.
        return True

    # Unknown event types are suppressed.
    return False


def notify_transition(ticket, old_status: str, new_status: str) -> Optional[str]:
    """Send notification for a status transition. Returns message or None."""
    # No-op transition.
    if old_status == new_status:
        return None

    if not should_notify(ticket, "transition"):
        return None

    # Suppress re-opening noise: if the ticket was already terminal before
    # this call and the new status is also terminal, skip.
    # (e.g. "closed" → "resolved" is administrative, not customer-visible.)
    if old_status in _TERMINAL_STATUSES and new_status in _TERMINAL_STATUSES:
        return None

    message = (
        f"Ticket {ticket.id} ({ticket.title!r}) moved from "
        f"'{old_status}' to '{new_status}'."
    )

    _notifications.append({
        "ticket_id": ticket.id,
        "message": message,
        "type": "transition",
    })
    return message


def notify_assignment(ticket, assignee_name: str) -> Optional[str]:
    """Send notification for an assignment. Returns message or None."""
    if not should_notify(ticket, "assignment"):
        return None

    message = (
        f"Ticket {ticket.id} ({ticket.title!r}) assigned to {assignee_name}."
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

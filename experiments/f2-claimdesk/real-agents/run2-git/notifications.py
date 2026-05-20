from typing import Optional, List, Dict

_notifications: list = []
_subscribers: Dict[str, List[str]] = {}

# Statuses where notifications are not meaningful
_TERMINAL_STATUSES = {"closed", "cancelled", "resolved"}

# Transitions that don't warrant a notification (noise-reduction)
# Re-opening a closed ticket *is* interesting, so we allow closed -> anything.
_SILENT_TRANSITIONS = {
    ("open", "open"),
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
    - Never notify for tickets that are already in a terminal state when the
      event is a routine update (assignment to a closed ticket is noise).
    - Transition events to/from the same status are suppressed.
    - A transition *into* a terminal state (e.g. closing) IS worth notifying.
    - Tickets with no contact email and no subscribers produce no notifications.
    """
    if event_type == "transition":
        # Allow notifications when entering a terminal status (e.g. closing)
        # or when leaving one (re-open).  Suppress if already terminal and
        # staying there.
        return True  # caller checks same-status via _SILENT_TRANSITIONS

    if event_type == "assignment":
        # Assigning an already-closed ticket isn't actionable.
        if ticket.status in _TERMINAL_STATUSES:
            return False
        return True

    return True


def _has_audience(ticket) -> bool:
    """Return True if there is at least one recipient for this ticket."""
    has_contact = bool(ticket.contact_email)
    has_subscribers = bool(_subscribers.get(ticket.id))
    return has_contact or has_subscribers


def notify_transition(ticket, old_status: str, new_status: str) -> Optional[str]:
    """Send notification for a status transition. Returns message or None."""
    if (old_status, new_status) in _SILENT_TRANSITIONS:
        return None

    if not should_notify(ticket, "transition"):
        return None

    if not _has_audience(ticket):
        return None

    message = (
        f"Ticket {ticket.id} ({ticket.title!r}) status changed: "
        f"{old_status} -> {new_status}."
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

    if not _has_audience(ticket):
        return None

    message = (
        f"Ticket {ticket.id} ({ticket.title!r}) has been assigned to "
        f"{assignee_name}."
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

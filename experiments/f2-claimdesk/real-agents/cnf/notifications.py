from typing import Optional, List, Dict

from workflow import TERMINAL_STATUSES

# ---------------------------------------------------------------------------
# Module state
# ---------------------------------------------------------------------------

_notifications: list = []
_subscribers: Dict[str, List[str]] = {}

# ---------------------------------------------------------------------------
# Subscription management
# ---------------------------------------------------------------------------

def subscribe(ticket_id: str, user_email: str) -> None:
    """Subscribe a user email to notifications for a ticket."""
    if ticket_id not in _subscribers:
        _subscribers[ticket_id] = []
    if user_email not in _subscribers[ticket_id]:
        _subscribers[ticket_id].append(user_email)


def get_subscribers(ticket_id: str) -> List[str]:
    """Get subscriber emails for a ticket."""
    return list(_subscribers.get(ticket_id, []))

# ---------------------------------------------------------------------------
# Notification policy
# ---------------------------------------------------------------------------

# Transitions that are purely internal housekeeping and should not surface
# as customer-facing noise.  Archiving a closed ticket is a storage concern,
# not a status customers care about.
_SILENT_TARGET_STATUSES = {"archived"}


def should_notify(ticket, event_type: str) -> bool:
    """Determine whether a notification should be sent for this ticket/event.

    Rules:
    - Never notify for an archived ticket (terminal, no audience cares).
    - Never notify when the target status is "archived" (handled by
      event_type == "transition" callers passing new_status separately,
      but we also guard here via ticket.status after the fact).
    - Always notify for meaningful lifecycle transitions and assignments
      while the ticket is active or moving to a customer-visible terminal
      state (closed).
    """
    if ticket.status in _SILENT_TARGET_STATUSES:
        return False
    return True


# ---------------------------------------------------------------------------
# Notification dispatch
# ---------------------------------------------------------------------------

def notify_transition(ticket, old_status: str, new_status: str) -> Optional[str]:
    """Send notification for a status transition.

    Returns the message string when a notification is recorded, or None if
    the transition is silent (e.g. archiving).
    """
    # Suppress notifications targeting the archived state — it is a
    # housekeeping action, not a customer-visible event.
    if new_status in _SILENT_TARGET_STATUSES:
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
    """Send notification for an assignment.

    Returns the message string when a notification is recorded, or None if
    the ticket is in a state where assignment noise is unwanted.
    """
    if not should_notify(ticket, "assignment"):
        return None

    message = (
        f"Ticket {ticket.id} ({ticket.title!r}) has been assigned to "
        f"{assignee_name!r}."
    )

    _notifications.append({
        "ticket_id": ticket.id,
        "message": message,
        "type": "assignment",
    })
    return message

# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------

def get_notifications(ticket_id: Optional[str] = None) -> list:
    """Get all notifications, optionally filtered by ticket_id."""
    if ticket_id is None:
        return list(_notifications)
    return [n for n in _notifications if n["ticket_id"] == ticket_id]


def reset_notifications() -> None:
    """Clear all notifications and subscribers."""
    _notifications.clear()
    _subscribers.clear()

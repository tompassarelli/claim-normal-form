from typing import Optional, List, Dict

_notifications: list = []
_subscribers: Dict[str, List[str]] = {}

# Statuses where a ticket is considered terminal — no further notifications
# are useful because the work is done.
_TERMINAL_STATUSES = {"closed"}

# Statuses where a ticket is effectively inactive; transitions *into* these
# are worth notifying about, but further churn while stuck there is not.
_INACTIVE_STATUSES = {"closed", "resolved"}


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

    Rules driven by ticket lifecycle:
    - Never notify on closed tickets (work is done, no audience).
    - Assignment notifications only fire when the ticket is active (open /
      in-progress); assigning a resolved/closed ticket is an admin action
      that doesn't need to alert anyone.
    - Transition notifications fire unless the ticket is already closed
      before the transition would be recorded (caller passes the *new*
      status via notify_transition, so we check old status there instead;
      here we just guard against the ticket itself being terminal already
      outside of a transition context).
    """
    if ticket.status in _TERMINAL_STATUSES and event_type != "transition":
        return False

    if event_type == "assignment":
        # Don't spam subscribers when inactive/closed tickets are touched
        if ticket.status in _INACTIVE_STATUSES:
            return False
        # Only meaningful if there is actually someone to notify
        if not ticket.contact_email and not get_subscribers(ticket.id):
            return False

    if event_type == "transition":
        # Always worth recording a transition (caller already filtered
        # no-op same→same transitions by virtue of calling this only when
        # status actually changes).  The one exception: if neither the
        # contact nor any subscriber exists, nobody to notify.
        if not ticket.contact_email and not get_subscribers(ticket.id):
            return False

    return True


def notify_transition(ticket, old_status: str, new_status: str) -> Optional[str]:
    """Send notification for a status transition. Returns message or None."""
    # If transitioning *away from* an already-closed ticket treat it as
    # reopening — that is worth a notification regardless of current status.
    # For all other cases, apply the standard should_notify check.
    if old_status != "closed" and not should_notify(ticket, "transition"):
        return None

    message = (
        f"Ticket {ticket.id} ({ticket.title!r}) status changed "
        f"from '{old_status}' to '{new_status}'."
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
        f"Ticket {ticket.id} ({ticket.title!r}) has been assigned to "
        f"'{assignee_name}'."
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

"""ClaimDesk notification feature.

Tracks subscriptions per ticket and generates notifications
for status transitions and assignments.
"""
from typing import List, Optional

_subscriptions: dict = {}  # ticket_id -> set of emails
_notifications: list = []  # list of notification dicts


def subscribe(ticket_id: str, user_email: str):
    """Subscribe an email to notifications for a ticket."""
    if ticket_id not in _subscriptions:
        _subscriptions[ticket_id] = set()
    _subscriptions[ticket_id].add(user_email)


def get_subscribers(ticket_id: str) -> List[str]:
    """Return sorted list of subscriber emails for a ticket."""
    return sorted(_subscriptions.get(ticket_id, set()))


def should_notify(ticket, event_type: str) -> bool:
    """Decide whether a notification should be sent.

    No notifications for tickets in terminal states (closed, archived)
    unless the event is the transition INTO that terminal state.
    Tickets with no subscribers get no notifications.
    """
    from workflow import TERMINAL_STATUSES

    # No subscribers means no notification
    if not get_subscribers(ticket.id):
        return False

    # If the ticket is already in a terminal state, don't notify.
    # (The transition INTO the terminal state is handled before the
    # status is updated on the ticket object, so that transition
    # still fires.)
    if ticket.status in TERMINAL_STATUSES:
        return False

    return True


def notify_transition(ticket, old_status: str, new_status: str) -> Optional[str]:
    """Generate a notification for a status transition.

    Returns the message string if sent, None otherwise.
    """
    if not should_notify(ticket, "transition"):
        return None

    message = (
        f"Ticket {ticket.id} ({ticket.title}): "
        f"status changed from {old_status} to {new_status}"
    )
    _notifications.append({
        "ticket_id": ticket.id,
        "message": message,
        "type": "transition",
    })
    return message


def notify_assignment(ticket, assignee_name: str) -> Optional[str]:
    """Generate a notification for a ticket assignment.

    Returns the message string if sent, None otherwise.
    """
    if not should_notify(ticket, "assignment"):
        return None

    message = (
        f"Ticket {ticket.id} ({ticket.title}): "
        f"assigned to {assignee_name}"
    )
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


# --- Hook functions wired into config.HOOKS ---

def _on_post_transition(**kwargs):
    """Hook for post_transition: notify subscribers of status changes.

    The ticket's status is already updated to new_status by the time
    this hook fires.  We need should_notify to evaluate against the
    OLD status (the state the ticket was in when the event originated)
    so that transitions INTO a terminal state still notify.  We
    temporarily restore old_status for the check, then put it back.
    """
    ticket = kwargs.get("ticket")
    old_status = kwargs.get("old_status", "unknown")
    new_status = kwargs.get("new_status", ticket.status if ticket else "unknown")
    if ticket:
        # Swap status to old for the should_notify check
        saved = ticket.status
        ticket.status = old_status
        result = notify_transition(ticket, old_status, new_status)
        ticket.status = saved


def _on_post_assign(**kwargs):
    """Hook for post_assign: notify subscribers of assignments."""
    ticket = kwargs.get("ticket")
    user_id = kwargs.get("user_id", "")
    if ticket:
        # Try to resolve user_id to a name via core
        from core import get_user
        user = get_user(user_id)
        assignee_name = user.name if user else user_id
        notify_assignment(ticket, assignee_name)

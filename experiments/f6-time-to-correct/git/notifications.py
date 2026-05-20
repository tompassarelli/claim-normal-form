"""Notifications module for ClaimDesk.

Generates in-process notification records for ticket transitions and
assignments. Suppresses notifications when the ticket is already in a
terminal state at the time the event fires.
"""

from typing import List, Optional

# Internal store: list of notification dicts
_notifications: List[dict] = []


def _is_terminal(ticket) -> bool:
    """Return True if ticket's current status is terminal."""
    from config import TERMINAL_STATUSES
    return ticket.status in TERMINAL_STATUSES


def notify_transition(ticket, old_status: str, new_status: str) -> None:
    """Record a status-transition notification.

    Suppressed when the ticket's current status is terminal (i.e. the
    ticket has already landed in a terminal state — we don't want noise
    for bookkeeping moves inside the graveyard).
    """
    if _is_terminal(ticket):
        return
    _notifications.append({
        "type": "transition",
        "ticket_id": ticket.id,
        "old_status": old_status,
        "new_status": new_status,
        "message": (
            f"Ticket {ticket.id} transitioned from '{old_status}' "
            f"to '{new_status}'."
        ),
    })


def notify_assignment(ticket, assignee_name: str) -> None:
    """Record an assignment notification.

    Suppressed when the ticket's current status is terminal.
    """
    if _is_terminal(ticket):
        return
    _notifications.append({
        "type": "assignment",
        "ticket_id": ticket.id,
        "assignee": assignee_name,
        "message": f"Ticket {ticket.id} assigned to {assignee_name}.",
    })


def get_notifications(ticket_id: Optional[str] = None) -> List[dict]:
    """Return all notifications, optionally filtered by ticket_id."""
    if ticket_id is None:
        return list(_notifications)
    return [n for n in _notifications if n["ticket_id"] == ticket_id]


def reset_notifications() -> None:
    """Clear all stored notifications (useful between tests / resets)."""
    _notifications.clear()


# ---------------------------------------------------------------------------
# Hook adapters — these are the callables registered in config.HOOKS.
# They adapt the keyword arguments supplied by core._run_hooks to the
# cleaner signatures above.
# ---------------------------------------------------------------------------

def _hook_post_transition(ticket, old_status: str, new_status: str, **_):
    notify_transition(ticket, old_status, new_status)


def _hook_post_assign(ticket, user_id: str = "", assigned_by: str = "", **_):
    """Resolve user_id to a display name, falling back to the raw id."""
    from core import get_user
    user = get_user(user_id)
    assignee_name = user.name if user else user_id
    notify_assignment(ticket, assignee_name)

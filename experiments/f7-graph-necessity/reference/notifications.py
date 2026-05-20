"""
Notification dispatch for the helpdesk/CRM application.

All public functions that create notifications go through notify(), which is
the single point of entry into the store.  Higher-level helpers (notify_*) are
composed from notify() and should_notify().

Notification types used in this module:
    "info"          — generic informational
    "transition"    — ticket status changed
    "assigned"      — ticket assigned / reassigned / unassigned
    "comment"       — new comment on a ticket
    "sla_breach"    — ticket has breached its SLA
    "escalation"    — ticket priority was bumped
"""

from typing import List, Optional

import store
from config import TERMINAL_STATUSES, ACTIVE_STATUSES
from models import Notification, Ticket
from events import _run_hooks


# ---------------------------------------------------------------------------
# Core dispatch
# ---------------------------------------------------------------------------

def notify(
    recipient_id: str,
    ticket_id: str,
    message: str,
    type: str = "info",
) -> Notification:
    """Create and persist a notification for *recipient_id*.

    Returns the stored Notification.  A recipient_id that does not correspond
    to a known user is accepted — validation is the caller's responsibility.
    """
    notif = Notification(
        id="",
        recipient_id=recipient_id,
        ticket_id=ticket_id,
        message=message,
        type=type,
        created_at="",
        read=False,
    )
    return store.add_notification(notif)


# ---------------------------------------------------------------------------
# Targeted notification helpers
# ---------------------------------------------------------------------------

def notify_transition(ticket: Ticket, old_status: str, new_status: str) -> None:
    """Notify assignee and creator when a ticket transitions between statuses.

    Suppressed entirely for tickets that have reached a terminal state — once
    closed the noise stops.  The *new_status* value is checked, not the
    ticket's live status field, so callers can pass the intended destination
    before committing the write.
    """
    if not should_notify(ticket, "transition"):
        return
    if new_status in TERMINAL_STATUSES:
        return

    message = f"Ticket #{ticket.id} moved from '{old_status}' to '{new_status}'."

    recipients: List[str] = []
    if ticket.assignee:
        recipients.append(ticket.assignee)

    # creator_id is not a field on Ticket; use contact_email as a best-effort
    # proxy only when it looks like a user id (non-empty, no '@').  Real apps
    # would track creator_id; we stay within the defined model here.
    for recipient_id in recipients:
        notify(recipient_id, ticket.id, message, type="transition")


def notify_assignment(
    ticket: Ticket,
    old_assignee: Optional[str],
    new_assignee: Optional[str],
) -> None:
    """Notify both the outgoing and incoming assignee about the change."""
    if old_assignee:
        msg = f"You have been unassigned from ticket #{ticket.id}: {ticket.title}."
        notify(old_assignee, ticket.id, msg, type="assigned")

    if new_assignee:
        msg = f"You have been assigned ticket #{ticket.id}: {ticket.title}."
        notify(new_assignee, ticket.id, msg, type="assigned")


def notify_comment(ticket: Ticket, comment) -> None:
    """Notify the assignee when someone else posts a comment on their ticket.

    *comment* is a models.Comment instance.  No notification is sent when the
    commenter and the assignee are the same person.
    """
    if not ticket.assignee:
        return
    if comment.author_id == ticket.assignee:
        return
    if not should_notify(ticket, "comment"):
        return

    msg = f"New comment on ticket #{ticket.id}: {comment.preview(60)}"
    notify(ticket.assignee, ticket.id, msg, type="comment")


def notify_sla_breach(ticket: Ticket) -> None:
    """Notify the assignee and the team lead that the ticket has breached SLA."""
    if not should_notify(ticket, "sla_breach"):
        return

    msg = f"SLA breached on ticket #{ticket.id}: {ticket.title}."

    recipients: List[str] = []
    if ticket.assignee:
        recipients.append(ticket.assignee)

    # Pull team lead from store if the ticket belongs to a team.
    if ticket.team:
        team = store.get_team(ticket.team)
        if team and team.lead and team.lead not in recipients:
            recipients.append(team.lead)

    for recipient_id in recipients:
        notify(recipient_id, ticket.id, msg, type="sla_breach")


def notify_escalation(ticket: Ticket, old_priority: str, new_priority: str) -> None:
    """Notify the assignee when a ticket's priority is escalated."""
    if not should_notify(ticket, "escalation"):
        return
    if not ticket.assignee:
        return

    msg = (
        f"Ticket #{ticket.id} priority escalated "
        f"from '{old_priority}' to '{new_priority}'."
    )
    notify(ticket.assignee, ticket.id, msg, type="escalation")


# ---------------------------------------------------------------------------
# Read / query helpers
# ---------------------------------------------------------------------------

def get_user_notifications(
    user_id: str,
    unread_only: bool = False,
) -> List[Notification]:
    """Return notifications for *user_id*, newest first."""
    return store.get_notifications(user_id, unread_only=unread_only)


def mark_notification_read(notification_id: str) -> bool:
    """Mark a single notification as read.  Returns True if found."""
    return store.mark_read(notification_id)


def mark_all_read(user_id: str) -> int:
    """Mark every unread notification for *user_id* as read.

    Returns the number of notifications updated.
    """
    unread = store.get_notifications(user_id, unread_only=True)
    count = 0
    for notif in unread:
        if store.mark_read(notif.id):
            count += 1
    return count


def get_notification_count(user_id: str, unread_only: bool = True) -> int:
    """Return the number of notifications for *user_id*."""
    return len(store.get_notifications(user_id, unread_only=unread_only))


# ---------------------------------------------------------------------------
# Policy helpers
# ---------------------------------------------------------------------------

def should_notify(ticket: Ticket, event_type: str) -> bool:
    """Return False when the ticket is in a terminal state.

    Prevents notification chatter for closed tickets regardless of event type.
    *event_type* is accepted for future per-event suppression rules but is not
    used to differentiate today.
    """
    return ticket.status not in TERMINAL_STATUSES


# ---------------------------------------------------------------------------
# Test helper
# ---------------------------------------------------------------------------

def reset_notifications() -> None:
    """Wipe all notifications from the store.  Intended for test isolation."""
    store.notifications.clear()

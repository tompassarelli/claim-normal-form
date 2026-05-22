from typing import List, Dict
from core import get_ticket, get_user, list_users

_notifications: List[Dict] = []

# Archiving is internal housekeeping; interested parties don't need a ping.
_SILENT_TARGET_STATUSES = {"archived"}


def notify_transition(ticket_id: str, old_status: str, new_status: str) -> None:
    if new_status in _SILENT_TARGET_STATUSES:
        return

    ticket = get_ticket(ticket_id)
    if ticket is None:
        return

    recipients: set[str] = set()

    if ticket.contact_email:
        recipients.add(ticket.contact_email)

    if ticket.assignee:
        user = get_user(ticket.assignee)
        if user:
            recipients.add(user.email)

    for user in list_users():
        if user.role in ("admin", "manager"):
            recipients.add(user.email)

    for email in sorted(recipients):
        _notifications.append({
            "ticket_id": ticket_id,
            "old_status": old_status,
            "new_status": new_status,
            "recipient": email,
        })


def get_notifications() -> List[Dict]:
    return list(_notifications)


def reset_notifications() -> None:
    _notifications.clear()
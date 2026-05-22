from typing import List, Dict
import time

from core import get_ticket, get_user, list_users

_notifications: List[Dict] = []

SILENT_STATUSES = {"spam", "duplicate"}


def notify_transition(ticket_id: str, old_status: str, new_status: str) -> None:
    if new_status in SILENT_STATUSES:
        return

    ticket = get_ticket(ticket_id)
    if not ticket:
        return

    recipients: set[str] = set()

    if ticket.contact_email:
        recipients.add(ticket.contact_email)

    if ticket.assignee:
        user = get_user(ticket.assignee)
        if user and user.email:
            recipients.add(user.email)

    for manager in list_users(role="manager"):
        if manager.email:
            recipients.add(manager.email)

    if not recipients:
        return

    now = str(int(time.time()))
    for recipient in sorted(recipients):
        _notifications.append({
            "ticket_id": ticket_id,
            "old_status": old_status,
            "new_status": new_status,
            "recipient": recipient,
            "timestamp": now,
        })


def get_notifications() -> List[Dict]:
    return list(_notifications)


def reset_notifications() -> None:
    _notifications.clear()
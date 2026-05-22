from typing import List, Dict
from workflow import TERMINAL_STATUSES
from core import get_ticket, get_user, list_users

SILENT_STATUSES = {"archived"}

_notifications: List[Dict] = []


def _recipients(ticket_id: str) -> List[str]:
    ticket = get_ticket(ticket_id)
    if ticket is None:
        return []

    seen = set()
    emails = []

    def _add(email: str) -> None:
        if email and email not in seen:
            seen.add(email)
            emails.append(email)

    _add(ticket.contact_email)

    if ticket.assignee:
        user = get_user(ticket.assignee)
        if user:
            _add(user.email)

    for manager in list_users(role="manager"):
        _add(manager.email)

    return emails


def notify_transition(ticket_id: str, old_status: str, new_status: str) -> None:
    if old_status == new_status:
        return
    if old_status in SILENT_STATUSES or new_status in SILENT_STATUSES:
        return

    for email in _recipients(ticket_id):
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
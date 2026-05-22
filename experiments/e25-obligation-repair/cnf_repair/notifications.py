from workflow import TERMINAL_STATUSES
from typing import Optional

_subscriptions: dict[str, set[str]] = {}
_notifications: list[dict] = []

_SILENT_STATES = {"archived"}


def subscribe(ticket_id: str, user_email: str) -> None:
    _subscriptions.setdefault(ticket_id, set()).add(user_email)


def notify_transition(ticket_id: str, old_status: str, new_status: str) -> None:
    if old_status == new_status:
        return
    if new_status in _SILENT_STATES:
        return
    recipients = _subscriptions.get(ticket_id, set())
    for email in recipients:
        _notifications.append({
            "ticket_id": ticket_id,
            "email": email,
            "old_status": old_status,
            "new_status": new_status,
        })


def get_notifications(ticket_id: Optional[str] = None) -> list:
    if ticket_id is None:
        return list(_notifications)
    return [n for n in _notifications if n["ticket_id"] == ticket_id]


def reset_notifications() -> None:
    _subscriptions.clear()
    _notifications.clear()
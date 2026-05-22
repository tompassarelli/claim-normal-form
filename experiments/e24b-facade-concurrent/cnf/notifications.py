from typing import Dict, List

_subscriptions: Dict[str, List[str]] = {}
_notifications: List[dict] = []

# archived is internal housekeeping — not visible to subscribers
_SILENT_STATUSES = {"archived"}


def subscribe(ticket_id: str, user_email: str) -> None:
    _subscriptions.setdefault(ticket_id, [])
    if user_email not in _subscriptions[ticket_id]:
        _subscriptions[ticket_id].append(user_email)


def notify_transition(ticket_id: str, old_status: str, new_status: str) -> None:
    if new_status in _SILENT_STATUSES:
        return
    recipients = _subscriptions.get(ticket_id, [])
    for email in recipients:
        _notifications.append({
            "ticket_id": ticket_id,
            "old_status": old_status,
            "new_status": new_status,
            "email": email,
        })


def get_notifications(ticket_id: str = None) -> list:
    if ticket_id is None:
        return list(_notifications)
    return [n for n in _notifications if n["ticket_id"] == ticket_id]


def reset_notifications() -> None:
    _subscriptions.clear()
    _notifications.clear()
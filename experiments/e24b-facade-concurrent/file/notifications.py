from typing import Optional
from datetime import datetime, timezone
from workflow import TERMINAL_STATUSES

_subscriptions: dict[str, set[str]] = {}
_log: list[dict] = []

SILENT_STATUSES = {"archived"}


def subscribe(ticket_id: str, user_email: str) -> None:
    _subscriptions.setdefault(ticket_id, set()).add(user_email)


def notify_transition(ticket_id: str, old_status: str, new_status: str) -> None:
    if old_status == new_status:
        return
    if new_status in SILENT_STATUSES:
        return

    recipients = list(_subscriptions.get(ticket_id, set()))
    entry = {
        "ticket_id": ticket_id,
        "old_status": old_status,
        "new_status": new_status,
        "recipients": recipients,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    _log.append(entry)


def get_notifications(ticket_id: Optional[str] = None) -> list[dict]:
    if ticket_id is None:
        return list(_log)
    return [n for n in _log if n["ticket_id"] == ticket_id]


def reset_notifications() -> None:
    _subscriptions.clear()
    _log.clear()
from typing import Optional, List, Dict, Set
from workflow import TERMINAL_STATUSES

_subscriptions: Dict[str, Set[str]] = {}
_notifications: list = []


def subscribe(ticket_id: str, user_email: str):
    if ticket_id not in _subscriptions:
        _subscriptions[ticket_id] = set()
    _subscriptions[ticket_id].add(user_email)


def get_subscribers(ticket_id: str) -> List[str]:
    return sorted(_subscriptions.get(ticket_id, set()))


def should_notify(ticket, event_type: str) -> bool:
    """Decide whether an event on this ticket warrants a notification.

    Archived tickets are terminal and should never generate noise.
    Closing a ticket is still noteworthy — subscribers want to know
    when a ticket reaches resolution. Only archived status is silent.
    """
    if ticket.status == "archived":
        return False
    return True


def notify_transition(ticket, old_status: str, new_status: str) -> Optional[str]:
    # After the transition the ticket already carries new_status.
    # Suppress notifications for transitions *into* archived.
    if new_status == "archived":
        return None
    if not should_notify(ticket, "transition"):
        return None
    message = (
        f"Ticket {ticket.id} transitioned from {old_status} to {new_status}"
    )
    _notifications.append({
        "ticket_id": ticket.id,
        "message": message,
        "type": "transition",
    })
    return message


def notify_assignment(ticket, assignee_name: str) -> Optional[str]:
    if not should_notify(ticket, "assignment"):
        return None
    message = f"Ticket {ticket.id} assigned to {assignee_name}"
    _notifications.append({
        "ticket_id": ticket.id,
        "message": message,
        "type": "assignment",
    })
    return message


def get_notifications(ticket_id: Optional[str] = None) -> list:
    if ticket_id is None:
        return list(_notifications)
    return [n for n in _notifications if n["ticket_id"] == ticket_id]


def reset_notifications():
    _subscriptions.clear()
    _notifications.clear()

from workflow import TERMINAL_STATUSES, ACTIVE_STATUSES
from core import get_user, get_ticket


def can_manage(user_id: str, ticket_id: str) -> bool:
    user = get_user(user_id)
    if not user:
        return False
    if user.role == "admin":
        return True
    ticket = get_ticket(ticket_id)
    if not ticket:
        return False
    if ticket.status in TERMINAL_STATUSES:
        return False
    return ticket.assignee == user_id


def can_archive(user_id: str) -> bool:
    user = get_user(user_id)
    return bool(user and user.role == "admin")


def can_reassign(user_id: str, ticket_id: str) -> bool:
    user = get_user(user_id)
    if not user:
        return False
    if user.role == "admin":
        return True
    ticket = get_ticket(ticket_id)
    if not ticket:
        return False
    if ticket.status in TERMINAL_STATUSES:
        return False
    return ticket.assignee == user_id


def check_permission(user_id: str, ticket_id: str, action: str) -> bool:
    if action == "manage":
        return can_manage(user_id, ticket_id)
    if action == "archive":
        return can_archive(user_id)
    if action == "reassign":
        return can_reassign(user_id, ticket_id)
    return False
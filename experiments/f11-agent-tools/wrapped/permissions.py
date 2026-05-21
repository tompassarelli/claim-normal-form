from models import User
from typing import List

PERMISSION_MATRIX = {
    "admin": [
        "create_ticket",
        "get_ticket",
        "update_ticket",
        "assign_ticket",
        "close_ticket",
        "list_tickets",
        "register_user",
        "get_user",
        "list_users",
        "create_contact",
        "get_contact",
        "list_contacts",
    ],
    "agent": [
        "create_ticket",
        "get_ticket",
        "update_ticket",
        "assign_ticket",
        "close_ticket",
        "list_tickets",
        "get_user",
        "list_users",
        "create_contact",
        "get_contact",
        "list_contacts",
    ],
    "viewer": [
        "get_ticket",
        "list_tickets",
        "get_user",
        "list_users",
        "get_contact",
        "list_contacts",
    ],
}


def has_permission(user: User, action: str) -> bool:
    return action in PERMISSION_MATRIX.get(user.role, [])


def require_permission(user: User, action: str) -> None:
    if not has_permission(user, action):
        raise PermissionError(
            f"User '{user.id}' with role '{user.role}' is not permitted to perform '{action}'"
        )


def get_allowed_actions(user: User) -> List[str]:
    return list(PERMISSION_MATRIX.get(user.role, []))
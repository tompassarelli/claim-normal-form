from models import User
from typing import List

PERMISSION_MATRIX = {
    "admin": [
        "create_ticket",
        "read_ticket",
        "update_ticket",
        "assign_ticket",
        "close_ticket",
        "list_tickets",
        "register_user",
        "read_user",
        "list_users",
    ],
    "agent": [
        "create_ticket",
        "read_ticket",
        "update_ticket",
        "assign_ticket",
        "close_ticket",
        "list_tickets",
        "read_user",
        "list_users",
    ],
    "viewer": [
        "read_ticket",
        "list_tickets",
        "read_user",
        "list_users",
    ],
}


def has_permission(user: User, action: str) -> bool:
    return action in PERMISSION_MATRIX.get(user.role, [])


def require_permission(user: User, action: str) -> None:
    if not has_permission(user, action):
        raise PermissionError(
            f"User '{user.id}' with role '{user.role}' is not allowed to perform '{action}'"
        )


def get_allowed_actions(user: User) -> List[str]:
    return list(PERMISSION_MATRIX.get(user.role, []))
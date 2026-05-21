from models import User
from typing import List

PERMISSION_MATRIX = {
    "admin": ["create", "view", "update", "assign", "close", "archive", "transition"],
    "agent": ["create", "view", "update", "assign", "close", "transition"],
    "viewer": ["view"],
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
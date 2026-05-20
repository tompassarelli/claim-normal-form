"""ClaimDesk permissions module.

Role-based access control with three roles:
  admin  — all operations
  agent  — standard ticket operations
  viewer — read-only access
"""
from models import User
from typing import List


PERMISSION_MATRIX = {
    "admin": [
        "create",
        "view",
        "update",
        "assign",
        "close",
        "archive",
        "transition",
    ],
    "agent": [
        "create",
        "view",
        "update",
        "assign",
        "close",
        "transition",
    ],
    "viewer": [
        "view",
    ],
}


def has_permission(user: User, action: str) -> bool:
    """Check whether a user's role grants access to the given action."""
    allowed = PERMISSION_MATRIX.get(user.role, [])
    return action in allowed


def require_permission(user: User, action: str) -> None:
    """Raise PermissionError if the user lacks access to the action."""
    if not has_permission(user, action):
        raise PermissionError(
            f"User '{user.id}' (role={user.role}) lacks permission for '{action}'"
        )


def get_allowed_actions(user: User) -> List[str]:
    """Return the list of actions permitted for the user's role."""
    return list(PERMISSION_MATRIX.get(user.role, []))

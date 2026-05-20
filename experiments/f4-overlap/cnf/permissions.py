"""ClaimDesk permissions module.

Role-based access control. Three roles:
  admin  — all operations
  agent  — standard ticket operations (no archive)
  viewer — read-only
"""
from config import SYSTEM_ACTIONS

PERMISSION_MATRIX = {
    "admin": list(SYSTEM_ACTIONS),  # all actions, including archive
    "agent": ["create", "view", "update", "assign", "close", "transition"],
    "viewer": ["view"],
}


def has_permission(user, action: str) -> bool:
    """Check whether user's role grants the given action."""
    allowed = PERMISSION_MATRIX.get(user.role, [])
    return action in allowed


def require_permission(user, action: str):
    """Raise PermissionError if user lacks the given action."""
    if not has_permission(user, action):
        raise PermissionError(
            f"User '{user.id}' (role={user.role}) lacks permission: {action}"
        )


def get_allowed_actions(user) -> list:
    """Return the list of actions permitted for the user's role."""
    return list(PERMISSION_MATRIX.get(user.role, []))

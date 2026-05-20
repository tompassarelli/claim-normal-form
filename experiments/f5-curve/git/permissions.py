"""ClaimDesk permissions — role-based access control.

Three roles:
  admin  — all operations
  agent  — standard ticket ops (create, view, update, assign, close), no archive
  viewer — read-only (view)
"""
from config import SYSTEM_ACTIONS

PERMISSION_MATRIX = {
    "admin": list(SYSTEM_ACTIONS),
    "agent": ["create", "view", "update", "assign", "close"],
    "viewer": ["view"],
}


def has_permission(user, action: str) -> bool:
    """Return True if user's role grants the given action."""
    allowed = PERMISSION_MATRIX.get(user.role, [])
    return action in allowed


def require_permission(user, action: str):
    """Raise PermissionError if user's role does not grant the action."""
    if not has_permission(user, action):
        raise PermissionError(
            f"User '{user.name}' (role={user.role}) lacks permission for '{action}'"
        )


def get_allowed_actions(user) -> list:
    """Return the list of actions available to this user's role."""
    return list(PERMISSION_MATRIX.get(user.role, []))

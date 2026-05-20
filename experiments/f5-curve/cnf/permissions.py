"""ClaimDesk permissions module.

Role-based access control for system actions.
Three roles: admin (all ops), agent (standard ops, no archive), viewer (read-only).
"""

PERMISSION_MATRIX = {
    "admin": [
        "create", "view", "update", "assign", "close",
        "archive", "transition",
    ],
    "agent": [
        "create", "view", "update", "assign", "close",
        "transition",
    ],
    "viewer": [
        "view",
    ],
}


def has_permission(user, action: str) -> bool:
    """Check whether user's role grants the given action."""
    allowed = PERMISSION_MATRIX.get(user.role, [])
    return action in allowed


def require_permission(user, action: str):
    """Raise PermissionError if the user lacks the given action."""
    if not has_permission(user, action):
        raise PermissionError(
            f"User '{user.name}' (role={user.role}) "
            f"lacks permission for '{action}'"
        )


def get_allowed_actions(user) -> list:
    """Return the list of actions the user's role permits."""
    return list(PERMISSION_MATRIX.get(user.role, []))

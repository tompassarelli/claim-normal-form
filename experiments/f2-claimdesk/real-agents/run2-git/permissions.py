from models import User

# Actions derived from core.py operations, grouped by resource.
# Ticket ops: create, view, update, assign, close, list
# Contact ops: create_contact, view_contact
# User ops: view_user, list_users

PERMISSION_MATRIX = {
    "admin": [
        "create",
        "view",
        "update",
        "assign",
        "close",
        "list",
        "create_contact",
        "view_contact",
        "view_user",
        "list_users",
    ],
    "agent": [
        "create",
        "view",
        "update",
        "assign",
        "close",
        "list",
        "create_contact",
        "view_contact",
        "view_user",
    ],
    "viewer": [
        "view",
        "list",
        "view_contact",
        "view_user",
    ],
}


def has_permission(user: User, action: str) -> bool:
    """Check if user's role allows the given action."""
    allowed = PERMISSION_MATRIX.get(user.role, [])
    return action in allowed


def require_permission(user: User, action: str) -> None:
    """Raise PermissionError if user's role doesn't allow the action."""
    if not has_permission(user, action):
        raise PermissionError(
            f"User '{user.name}' with role '{user.role}' "
            f"is not permitted to perform action '{action}'."
        )


def get_allowed_actions(user: User) -> list:
    """Return all actions the user's role allows."""
    return list(PERMISSION_MATRIX.get(user.role, []))

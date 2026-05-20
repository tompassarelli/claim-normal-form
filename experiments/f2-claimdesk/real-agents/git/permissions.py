"""
Role-based access control for ClaimDesk.

Roles:
  admin   — full access to all operations
  agent   — standard ticket and contact operations
  viewer  — read-only access
"""

from models import User

# Actions derived from core.py operations:
#   Ticket operations: create, view, update, assign, close, list
#   Contact operations: create_contact, view_contact
#   User operations: manage_users (admin only)

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
        "manage_users",
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
    ],
    "viewer": [
        "view",
        "list",
        "view_contact",
    ],
}


def has_permission(user: User, action: str) -> bool:
    """Check if user's role allows the given action."""
    allowed = PERMISSION_MATRIX.get(user.role, [])
    return action in allowed


def require_permission(user: User, action: str):
    """Raise PermissionError if user's role doesn't allow the action."""
    if not has_permission(user, action):
        raise PermissionError(
            f"User '{user.name}' with role '{user.role}' "
            f"is not permitted to perform action '{action}'."
        )


def get_allowed_actions(user: User) -> list:
    """Return all actions the user's role allows."""
    return list(PERMISSION_MATRIX.get(user.role, []))

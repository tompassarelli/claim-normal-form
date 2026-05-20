"""
Role-based access control for ClaimDesk.

Roles
-----
admin   — full access to all operations
agent   — standard ticket and contact operations
viewer  — read-only access

Actions are derived from the operations in core.py:
  Tickets  : create_ticket, get_ticket, list_tickets, update_ticket,
             assign_ticket, close_ticket
  Contacts : create_contact, get_contact
  Users    : register_user, list_users
"""

PERMISSION_MATRIX: dict[str, list[str]] = {
    "admin": [
        "ticket:create",
        "ticket:view",
        "ticket:update",
        "ticket:assign",
        "ticket:close",
        "contact:create",
        "contact:view",
        "user:register",
        "user:view",
    ],
    "agent": [
        "ticket:create",
        "ticket:view",
        "ticket:update",
        "ticket:assign",
        "ticket:close",
        "contact:create",
        "contact:view",
        "user:view",
    ],
    "viewer": [
        "ticket:view",
        "contact:view",
        "user:view",
    ],
}


def has_permission(user, action: str) -> bool:
    """Check if user's role allows the given action."""
    allowed = PERMISSION_MATRIX.get(user.role, [])
    return action in allowed


def require_permission(user, action: str) -> None:
    """Raise PermissionError if user's role doesn't allow the action."""
    if not has_permission(user, action):
        raise PermissionError(
            f"Role '{user.role}' is not permitted to perform '{action}'"
        )


def get_allowed_actions(user) -> list:
    """Return all actions the user's role allows."""
    return list(PERMISSION_MATRIX.get(user.role, []))

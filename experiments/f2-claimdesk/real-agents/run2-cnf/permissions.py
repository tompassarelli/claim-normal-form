"""
Role-based access control for ClaimDesk.

Roles
-----
admin   — full access to all operations, including user management
agent   — standard ticket lifecycle operations; cannot archive or manage users
viewer  — read-only access

Action inventory (derived from core.py + workflow.py)
------------------------------------------------------
view         get_ticket, list_tickets, get_contact, get_user, list_users,
             is_active, is_archived, get_available_transitions
create       create_ticket, create_contact
update       update_ticket (field edits)
assign       assign_ticket
close        close_ticket / transition → closed
resolve      transition → resolved
reopen       transition → open (from in_progress or resolved)
transition   transition_ticket (general; covers in_progress, and the above)
archive      archive_ticket / transition → archived (closed → archived only)
manage_users register_user
"""

from models import User

PERMISSION_MATRIX: dict[str, list[str]] = {
    "admin": [
        "view",
        "create",
        "update",
        "assign",
        "close",
        "resolve",
        "reopen",
        "transition",
        "archive",
        "manage_users",
    ],
    "agent": [
        "view",
        "create",
        "update",
        "assign",
        "close",
        "resolve",
        "reopen",
        "transition",
    ],
    "viewer": [
        "view",
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
            f"User '{user.id}' with role '{user.role}' "
            f"is not permitted to perform action '{action}'."
        )


def get_allowed_actions(user: User) -> list:
    """Return all actions the user's role allows."""
    return list(PERMISSION_MATRIX.get(user.role, []))

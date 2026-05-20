"""
Role-based access control for ClaimDesk.

Roles
-----
admin   — full access to all operations
agent   — standard ticket and contact operations; cannot manage users
          or archive tickets (terminal/destructive state)
viewer  — read-only access

Actions are short lowercase strings that map 1-to-1 to operations in
core.py and workflow.py:

  create        — core.create_ticket
  view          — core.get_ticket, core.list_tickets
  update        — core.update_ticket
  assign        — core.assign_ticket
  close         — core.close_ticket
  transition    — workflow.transition_ticket, workflow.get_available_transitions
  archive       — workflow.archive_ticket
  manage_users  — core.register_user, core.list_users, core.get_user
  manage_contacts — core.create_contact, core.get_contact
"""

from models import User

PERMISSION_MATRIX: dict[str, list[str]] = {
    "admin": [
        "create",
        "view",
        "update",
        "assign",
        "close",
        "transition",
        "archive",
        "manage_users",
        "manage_contacts",
    ],
    "agent": [
        "create",
        "view",
        "update",
        "assign",
        "close",
        "transition",
        "manage_contacts",
    ],
    "viewer": [
        "view",
    ],
}


def has_permission(user: User, action: str) -> bool:
    """Return True if the user's role allows *action*, False otherwise."""
    allowed = PERMISSION_MATRIX.get(user.role, [])
    return action in allowed


def require_permission(user: User, action: str) -> None:
    """Raise PermissionError if the user's role does not allow *action*."""
    if not has_permission(user, action):
        raise PermissionError(
            f"User '{user.id}' with role '{user.role}' "
            f"is not permitted to perform action '{action}'."
        )


def get_allowed_actions(user: User) -> list[str]:
    """Return a copy of all actions the user's role permits."""
    return list(PERMISSION_MATRIX.get(user.role, []))

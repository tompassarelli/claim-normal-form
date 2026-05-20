"""Role-based permission system for ClaimDesk.

Three roles:
  admin  — full access to every operation
  agent  — standard ticket and contact operations
  viewer — read-only access
"""

from typing import List

# Every action recognised by the system.
ALL_ACTIONS = [
    "create",           # create_ticket
    "view",             # get_ticket, list_tickets, get_contact, get_user, list_users
    "update",           # update_ticket
    "assign",           # assign_ticket
    "close",            # close_ticket
    "transition",       # transition_ticket (workflow state-machine moves)
    "archive",          # archive_ticket
    "create_contact",   # create_contact
    "register_user",    # register_user
    "reset",            # reset_state (destructive — admin only)
]

PERMISSION_MATRIX = {
    "admin": list(ALL_ACTIONS),                         # everything
    "agent": [
        "create",
        "view",
        "update",
        "assign",
        "close",
        "transition",
        "archive",
        "create_contact",
    ],
    "viewer": [
        "view",
    ],
}


def has_permission(user, action: str) -> bool:
    """Return True if *user* (a User dataclass) is allowed to perform *action*."""
    allowed = PERMISSION_MATRIX.get(user.role, [])
    return action in allowed


def require_permission(user, action: str) -> None:
    """Raise ``PermissionError`` if *user* may not perform *action*."""
    if not has_permission(user, action):
        raise PermissionError(
            f"User '{user.id}' (role={user.role}) lacks permission for '{action}'"
        )


def get_allowed_actions(user) -> List[str]:
    """Return the list of action strings the given *user* may perform."""
    return list(PERMISSION_MATRIX.get(user.role, []))

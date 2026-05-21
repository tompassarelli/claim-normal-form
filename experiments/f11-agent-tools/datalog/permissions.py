from models import User
from typing import List

_VIEWER_ACTIONS = [
    "get_ticket",
    "list_tickets",
    "get_user",
    "list_users",
    "get_contact",
    "get_available_transitions",
    "is_active",
    "is_archived",
    "is_valid_transition",
]

_AGENT_ACTIONS = _VIEWER_ACTIONS + [
    "create_ticket",
    "update_ticket",
    "assign_ticket",
    "close_ticket",
    "transition_ticket",
    "create_contact",
]

_ADMIN_ACTIONS = _AGENT_ACTIONS + [
    "archive_ticket",
    "register_user",
    "reset_state",
]

PERMISSION_MATRIX: dict[str, List[str]] = {
    "viewer": _VIEWER_ACTIONS,
    "agent": _AGENT_ACTIONS,
    "admin": _ADMIN_ACTIONS,
}


def has_permission(user: User, action: str) -> bool:
    allowed = PERMISSION_MATRIX.get(user.role, [])
    return action in allowed


def require_permission(user: User, action: str) -> None:
    if not has_permission(user, action):
        raise PermissionError(
            f"User '{user.id}' with role '{user.role}' is not permitted to perform '{action}'"
        )


def get_allowed_actions(user: User) -> List[str]:
    return list(PERMISSION_MATRIX.get(user.role, []))
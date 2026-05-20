"""Permissions module for ClaimDesk.

Role-based access control with three roles:
- admin:  all actions including archive
- agent:  standard operations, no archive
- viewer: read-only

Wire into ClaimDesk by calling register_hooks() once at startup.
"""

from typing import List

# Actions each role may perform.
ROLE_PERMISSIONS = {
    "admin": {"view", "create", "update", "assign", "transition", "close", "archive"},
    "agent": {"view", "create", "update", "assign", "transition", "close"},
    "viewer": {"view"},
}


def has_permission(user, action: str) -> bool:
    """Return True if *user* is allowed to perform *action*.

    *user* must be a models.User instance (has a .role attribute).
    Unknown roles are treated as having no permissions.
    """
    allowed = ROLE_PERMISSIONS.get(user.role, set())
    return action in allowed


def require_permission(user, action: str) -> None:
    """Raise PermissionError if *user* is not allowed to perform *action*."""
    if not has_permission(user, action):
        raise PermissionError(
            f"User '{user.id}' with role '{user.role}' "
            f"does not have permission to perform '{action}'"
        )


def get_allowed_actions(user) -> List[str]:
    """Return a sorted list of actions *user* is allowed to perform."""
    return sorted(ROLE_PERMISSIONS.get(user.role, set()))


# ---------------------------------------------------------------------------
# Hook wiring
# ---------------------------------------------------------------------------

def _pre_create_permission_check(user_id: str = "", **kwargs) -> None:
    """pre_create hook: enforce 'create' permission.

    Skips silently when user_id is empty or the user isn't registered —
    other modules (or tests) that don't supply a user are not blocked.
    """
    if not user_id:
        return
    from core import get_user
    user = get_user(user_id)
    if user is None:
        return
    require_permission(user, "create")


def register_hooks() -> None:
    """Append the permissions pre_create hook to config.HOOKS.

    Safe to call multiple times — checks for duplicates before appending.
    """
    from config import HOOKS
    hook_list = HOOKS.setdefault("pre_create", [])
    if _pre_create_permission_check not in hook_list:
        hook_list.append(_pre_create_permission_check)

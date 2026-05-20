"""ClaimDesk permissions module — role-based access control.

Three roles with strictly nested permissions:
  viewer  — read-only
  agent   — standard operations (create, view, update, assign, close, transition)
  admin   — all actions including archive

Use has_permission / require_permission in application code.
Register check_create_permission as a pre_create hook via config.py.
"""

from typing import List

# Role → allowed actions. More-privileged roles get all lesser-role actions
# plus their own additions.
_ROLE_ACTIONS: dict[str, List[str]] = {
    "viewer": [
        "view",
    ],
    "agent": [
        "view",
        "create",
        "update",
        "assign",
        "close",
        "transition",
    ],
    "admin": [
        "view",
        "create",
        "update",
        "assign",
        "close",
        "transition",
        "archive",
    ],
}


def has_permission(user, action: str) -> bool:
    """Return True if *user* is allowed to perform *action*.

    Args:
        user: A User instance (must have a ``role`` attribute).
        action: The action string to check.
    """
    allowed = _ROLE_ACTIONS.get(user.role, [])
    return action in allowed


def require_permission(user, action: str) -> None:
    """Raise PermissionError if *user* is not allowed to perform *action*.

    Args:
        user: A User instance (must have a ``role`` attribute).
        action: The action string to enforce.

    Raises:
        PermissionError: When the user's role does not include *action*.
    """
    if not has_permission(user, action):
        raise PermissionError(
            f"User '{user.id}' (role='{user.role}') does not have "
            f"permission to perform action '{action}'."
        )


def get_allowed_actions(user) -> List[str]:
    """Return the list of actions permitted for *user*'s role.

    Args:
        user: A User instance (must have a ``role`` attribute).

    Returns:
        A list of action strings. Returns an empty list for unknown roles.
    """
    return list(_ROLE_ACTIONS.get(user.role, []))


# ---------------------------------------------------------------------------
# Hook implementation
# ---------------------------------------------------------------------------

def check_create_permission(user_id: str, **kwargs) -> None:
    """pre_create hook — enforces that the acting user may create tickets.

    Wired into config.HOOKS["pre_create"] from config.py.
    Silently skips the check when *user_id* is empty (system-initiated calls).
    """
    if not user_id:
        return
    from core import get_user
    user = get_user(user_id)
    if user is None:
        # Unknown user — cannot verify permission, skip check.
        return
    require_permission(user, "create")

"""Shared configuration for ClaimDesk.

This file is the single source of truth for system-wide constants.
Feature modules should EXTEND these lists when they add new capabilities.
"""

SYSTEM_ACTIONS = [
    "create",
    "view",
    "update",
    "assign",
    "close",
    "archive",
    "transition",
]

TERMINAL_STATUSES = ["closed", "archived"]
ACTIVE_STATUSES = ["open", "in_progress", "resolved"]

ALL_STATUSES = ACTIVE_STATUSES + TERMINAL_STATUSES

HOOKS = {
    "pre_create": [],
    "post_create": [],
    "pre_transition": [],
    "post_transition": [],
    "pre_assign": [],
    "post_assign": [],
    "pre_close": [],
    "post_close": [],
}


# --- Permission hook registration ---

def _check_create_permission(title, user_id, **kwargs):
    """Pre-create hook: log and validate that a user_id is present."""
    if not user_id:
        import sys
        print("permissions: pre_create called without user_id", file=sys.stderr)


HOOKS["pre_create"].append(_check_create_permission)

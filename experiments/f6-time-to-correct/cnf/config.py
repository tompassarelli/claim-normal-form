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
    "tag",
    "add_tag",
    "assign_team",
    "team",
]

TERMINAL_STATUSES = ["closed", "archived"]
ACTIVE_STATUSES = ["open", "in_progress", "resolved", "on_hold"]

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

# --- Permissions hooks ---
from permissions import _pre_create_permission_check
HOOKS["pre_create"].append(_pre_create_permission_check)

# --- Audit hooks ---
from audit import (
    _post_create_audit,
    _post_transition_audit,
    _post_assign_audit,
    _post_close_audit,
)
HOOKS["post_create"].append(_post_create_audit)
HOOKS["post_transition"].append(_post_transition_audit)
HOOKS["post_assign"].append(_post_assign_audit)
HOOKS["post_close"].append(_post_close_audit)

# --- Notifications hooks ---
from notifications import _post_transition_notify, _post_assign_notify
HOOKS["post_transition"].append(_post_transition_notify)
HOOKS["post_assign"].append(_post_assign_notify)

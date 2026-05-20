"""Shared configuration for ClaimDesk.

This file is the single source of truth for system-wide constants.
Feature modules should EXTEND these lists when they add new capabilities.

[Best-case manual merge of 8 independent agent config.py modifications]
"""

SYSTEM_ACTIONS = [
    "create",
    "view",
    "update",
    "assign",
    "close",
    "archive",
    "transition",
    "add_tag",
    "tag",
    "assign_team",
]

TERMINAL_STATUSES = ["closed", "archived"]
ACTIVE_STATUSES = ["open", "in_progress", "on_hold", "resolved"]

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

# --- Permissions hooks (from perms agent) ---
from permissions import check_create_permission
HOOKS["pre_create"].append(check_create_permission)

# --- Audit hooks (from audit agent) ---
from audit import register_audit_hooks
register_audit_hooks()

# --- Notification hooks (from notification agent) ---
from notifications import _hook_post_transition, _hook_post_assign
HOOKS["post_transition"].append(_hook_post_transition)
HOOKS["post_assign"].append(_hook_post_assign)

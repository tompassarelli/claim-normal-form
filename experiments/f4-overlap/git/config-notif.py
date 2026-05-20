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
    "subscribe",
    "notify",
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

# --- Feature module hook registration ---
# Imported here (after HOOKS is defined) to avoid circular imports.

from notifications import _on_post_transition, _on_post_assign

HOOKS["post_transition"].append(_on_post_transition)
HOOKS["post_assign"].append(_on_post_assign)

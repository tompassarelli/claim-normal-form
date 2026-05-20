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
    "transition",
    "archive",
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

# --- Audit hooks (appended after HOOKS is defined to avoid circular imports) ---
from audit import audit_create, audit_transition, audit_assignment


def _audit_post_create(**kwargs):
    ticket = kwargs["ticket"]
    user_id = kwargs.get("user_id", "")
    audit_create(ticket.id, user_id, ticket.title)


def _audit_post_transition(**kwargs):
    ticket = kwargs["ticket"]
    user_id = kwargs.get("user_id", "")
    old_status = kwargs.get("old_status", "")
    new_status = ticket.status
    audit_transition(ticket.id, user_id, old_status, new_status)


def _audit_post_assign(**kwargs):
    ticket = kwargs["ticket"]
    user_id = kwargs.get("user_id", "")
    audit_assignment(ticket.id, user_id, ticket.assignee)


def _audit_post_close(**kwargs):
    ticket = kwargs["ticket"]
    user_id = kwargs.get("user_id", "")
    audit_transition(ticket.id, user_id, "open", "closed")


HOOKS["post_create"].append(_audit_post_create)
HOOKS["post_transition"].append(_audit_post_transition)
HOOKS["post_assign"].append(_audit_post_assign)
HOOKS["post_close"].append(_audit_post_close)

"""Shared configuration for ClaimDesk.

This file is the single source of truth for system-wide constants.
Feature modules should EXTEND these lists when they add new capabilities.

NOTE: This is a BEST-CASE manual merge of three agents' independent
modifications. All merge conflicts resolved perfectly. Even so,
on_hold is missing because no git agent saw workflow v2.
"""

SYSTEM_ACTIONS = [
    "create",
    "view",
    "update",
    "assign",
    "close",
    "archive",
    "transition",
    "subscribe",
    "notify",
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


# --- Permission hooks (from git-perms agent) ---

def _check_create_permission(title, user_id, **kwargs):
    if not user_id:
        import sys
        print("permissions: pre_create called without user_id", file=sys.stderr)


HOOKS["pre_create"].append(_check_create_permission)


# --- Audit hooks (from git-audit agent) ---
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


# --- Notification hooks (from git-notif agent) ---
from notifications import _on_post_transition, _on_post_assign

HOOKS["post_transition"].append(_on_post_transition)
HOOKS["post_assign"].append(_on_post_assign)

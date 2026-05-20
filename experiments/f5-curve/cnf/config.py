"""Shared configuration for ClaimDesk.

This file is the single source of truth for system-wide constants.
Feature modules EXTEND these lists when they add new capabilities.
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


# --- Permissions hook (Agent 1) ---

def _check_create_permission(**kwargs):
    from permissions import require_permission
    from core import get_user
    user_id = kwargs.get("user_id", "")
    if user_id:
        user = get_user(user_id)
        if user:
            require_permission(user, "create")

HOOKS["pre_create"].append(_check_create_permission)


# --- Audit hooks (Agent 2) ---

def _audit_post_create(ticket, user_id="", **_kw):
    from audit import log_action
    log_action("create", ticket.id, user_id=user_id, title=ticket.title)

def _audit_post_transition(ticket, old_status="", new_status="", **_kw):
    from audit import log_action
    log_action("transition", ticket.id, old_status=old_status, new_status=new_status)

def _audit_post_assign(ticket, user_id="", assigned_by="", **_kw):
    from audit import log_action
    log_action("assign", ticket.id, user_id=assigned_by or user_id, assignee=user_id)

def _audit_post_close(ticket, user_id="", **_kw):
    from audit import log_action
    log_action("close", ticket.id, user_id=user_id)

HOOKS["post_create"].append(_audit_post_create)
HOOKS["post_transition"].append(_audit_post_transition)
HOOKS["post_assign"].append(_audit_post_assign)
HOOKS["post_close"].append(_audit_post_close)


# --- Notification hooks (Agent 3) ---

def _notif_post_transition(ticket, old_status="", new_status="", **_kw):
    from notifications import notify_transition
    notify_transition(ticket, old_status, new_status)

def _notif_post_assign(ticket, user_id="", **_kw):
    from notifications import notify_assignment
    notify_assignment(ticket, user_id)

HOOKS["post_transition"].append(_notif_post_transition)
HOOKS["post_assign"].append(_notif_post_assign)

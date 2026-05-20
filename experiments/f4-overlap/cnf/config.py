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


# --- Hook registrations (after HOOKS is defined to avoid circular imports) ---

def _check_create_permission(**kwargs):
    """Pre-create hook: verify the user has 'create' permission."""
    user_id = kwargs.get("user_id", "")
    if not user_id:
        return  # anonymous/system creates are allowed
    from core import get_user
    user = get_user(user_id)
    if user is None:
        return  # unknown user_id — let core decide
    from permissions import require_permission
    require_permission(user, "create")


HOOKS["pre_create"].append(_check_create_permission)


# --- Audit hook registrations ---

def _audit_post_create(**kwargs):
    """Post-create hook: log ticket creation."""
    from audit import audit_create
    ticket = kwargs["ticket"]
    user_id = kwargs.get("user_id", "")
    audit_create(ticket.id, user_id, ticket.title)


def _audit_post_transition(**kwargs):
    """Post-transition hook: log status change."""
    from audit import audit_transition
    ticket = kwargs["ticket"]
    old_status = kwargs["old_status"]
    new_status = kwargs["new_status"]
    # workflow.transition_ticket doesn't pass user_id; use assignee as fallback
    user_id = kwargs.get("user_id", ticket.assignee or "")
    audit_transition(ticket.id, user_id, old_status, new_status)


def _audit_post_assign(**kwargs):
    """Post-assign hook: log assignment."""
    from audit import audit_assignment
    ticket = kwargs["ticket"]
    user_id = kwargs["user_id"]
    assigned_by = kwargs.get("assigned_by", "")
    audit_assignment(ticket.id, assigned_by or user_id, user_id)


def _audit_post_close(**kwargs):
    """Post-close hook: log ticket closure."""
    from audit import log_action
    ticket = kwargs["ticket"]
    user_id = kwargs.get("user_id", "")
    log_action("close", ticket.id, user_id)


HOOKS["post_create"].append(_audit_post_create)
HOOKS["post_transition"].append(_audit_post_transition)
HOOKS["post_assign"].append(_audit_post_assign)
HOOKS["post_close"].append(_audit_post_close)


# --- Notification hook registrations ---

def _notify_post_transition(**kwargs):
    """Post-transition hook: emit notification for status changes."""
    from notifications import notify_transition
    ticket = kwargs["ticket"]
    old_status = kwargs["old_status"]
    new_status = kwargs["new_status"]
    notify_transition(ticket, old_status, new_status)


def _notify_post_assign(**kwargs):
    """Post-assign hook: emit notification for assignments."""
    from notifications import notify_assignment
    ticket = kwargs["ticket"]
    user_id = kwargs["user_id"]
    notify_assignment(ticket, user_id)


HOOKS["post_transition"].append(_notify_post_transition)
HOOKS["post_assign"].append(_notify_post_assign)

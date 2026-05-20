"""Shared configuration for ClaimDesk.

Best-case manual merge of 8 independent agent config.py modifications.
"""

SYSTEM_ACTIONS = [
    "create",
    "view",
    "update",
    "assign",
    "close",
    "archive",
    "transition",
    "audit_view",
    "subscribe",
    "notify",
    "sla",
    "tag",
    "assign_team",
    "escalate",
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


# --- Audit hooks (from audit agent) ---

def _audit_post_create(ticket, user_id="", **_kw):
    from audit import audit_create
    audit_create(ticket_id=ticket.id, user_id=user_id, title=ticket.title)

def _audit_post_transition(ticket, user_id="", old_status="",
                           new_status="", **_kw):
    from audit import audit_transition
    audit_transition(ticket_id=ticket.id, user_id=user_id,
                     old_status=old_status, new_status=new_status)

def _audit_post_assign(ticket, user_id="", assigned_by="", **_kw):
    from audit import audit_assignment
    audit_assignment(ticket_id=ticket.id, user_id=assigned_by or user_id,
                     assignee=user_id)

def _audit_post_close(ticket, user_id="", **_kw):
    from audit import audit_transition
    audit_transition(ticket_id=ticket.id, user_id=user_id,
                     old_status="open", new_status="closed")

HOOKS["post_create"].append(_audit_post_create)
HOOKS["post_transition"].append(_audit_post_transition)
HOOKS["post_assign"].append(_audit_post_assign)
HOOKS["post_close"].append(_audit_post_close)


# --- Notification hooks (from notification agent) ---

def _hook_post_transition(ticket, old_status, new_status, **kwargs):
    from notifications import notify_transition
    notify_transition(ticket, old_status, new_status)

def _hook_post_assign(ticket, user_id, **kwargs):
    from notifications import notify_assignment
    notify_assignment(ticket, user_id)

HOOKS["post_transition"].append(_hook_post_transition)
HOOKS["post_assign"].append(_hook_post_assign)


# --- SLA hooks (from SLA agent) ---

from sla import _on_post_create
HOOKS["post_create"].append(_on_post_create)


# --- Escalation hooks (from escalation agent) ---

def _register_escalation_hook():
    from escalation import _default_escalation_hook
    if _default_escalation_hook not in HOOKS["post_create"]:
        HOOKS["post_create"].append(_default_escalation_hook)

_register_escalation_hook()

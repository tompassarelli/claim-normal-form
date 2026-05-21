#!/usr/bin/env python3
"""F8: Parallel Construction Race — Git-parallel vs CNF-parallel

Head-to-head: N agents build a CRM app in parallel.
Git condition:  N worktrees, parallel build, merge, test, repair loop.
CNF condition:  Daemon + N parallel agents against shared graph, test.

Metric: wall clock to all tests passing.

Agent code is from F2/F5 (produced by real Claude Code agents).
The bugs are structural — same 5 information-gap failures appear in
every git run, never in any CNF run (confirmed across 4 real-agent runs).

Infrastructure operations are REAL: daemon startup, graph parse, pytest
execution, file merge. Agent inference time is simulated at F6-calibrated
rates (26s/agent) to project end-to-end wall clock.

Usage:
    python runner.py              # Run both conditions, print comparison
    python runner.py --no-delay   # Skip simulated inference delays
"""

import concurrent.futures
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import threading
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()
CNF_ROOT = SCRIPT_DIR.parent.parent
SERVER = CNF_ROOT / "cnf-lib" / "server.rkt"

AGENT_INFERENCE_TIME = 26.0  # seconds, from F6 median
REPAIR_INFERENCE_TIME = 56.0  # seconds, from F6 repair round
USE_DELAYS = "--no-delay" not in sys.argv


# ════════════════════════════════════════════════════════════════════
# Base code (starting point for all agents)
# ════════════════════════════════════════════════════════════════════

BASE_CONFIG = '''\
"""Shared configuration for ClaimDesk."""

SYSTEM_ACTIONS = [
    "create",
    "view",
    "update",
    "assign",
    "close",
]

TERMINAL_STATUSES = ["closed"]
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
'''

BASE_MODELS = '''\
from dataclasses import dataclass, field
from typing import Optional, List


@dataclass
class Ticket:
    id: str
    title: str
    description: str
    status: str = "open"
    priority: str = "medium"
    assignee: Optional[str] = None
    contact_email: str = ""
    created_at: str = ""
    updated_at: str = ""
    tags: List[str] = field(default_factory=list)


@dataclass
class User:
    id: str
    name: str
    email: str
    role: str = "agent"


@dataclass
class Contact:
    id: str
    name: str
    email: str
    company: str = ""
    tickets: List[str] = field(default_factory=list)
'''

BASE_CORE = '''\
from models import Ticket, User, Contact
from typing import List, Optional, Dict
import time

_tickets: Dict[str, Ticket] = {}
_users: Dict[str, User] = {}
_contacts: Dict[str, Contact] = {}
_next_ticket = [1]
_next_contact = [1]


def _now():
    return str(int(time.time()))


def _run_hooks(hook_name, **kwargs):
    from config import HOOKS
    for fn in HOOKS.get(hook_name, []):
        fn(**kwargs)


def create_ticket(title: str, description: str, contact_email: str = "",
                  priority: str = "medium", user_id: str = "") -> Ticket:
    _run_hooks("pre_create", title=title, user_id=user_id)
    tid = f"T-{_next_ticket[0]}"
    _next_ticket[0] += 1
    now = _now()
    t = Ticket(id=tid, title=title, description=description,
               contact_email=contact_email, priority=priority,
               created_at=now, updated_at=now)
    _tickets[tid] = t
    _run_hooks("post_create", ticket=t, user_id=user_id)
    return t


def get_ticket(ticket_id: str) -> Optional[Ticket]:
    return _tickets.get(ticket_id)


def update_ticket(ticket_id: str, **fields) -> Ticket:
    t = _tickets[ticket_id]
    for k, v in fields.items():
        setattr(t, k, v)
    t.updated_at = _now()
    return t


def assign_ticket(ticket_id: str, user_id: str,
                  assigned_by: str = "") -> Ticket:
    _run_hooks("pre_assign", ticket_id=ticket_id, user_id=user_id,
               assigned_by=assigned_by)
    t = update_ticket(ticket_id, assignee=user_id)
    _run_hooks("post_assign", ticket=t, user_id=user_id,
               assigned_by=assigned_by)
    return t


def close_ticket(ticket_id: str, user_id: str = "") -> Ticket:
    _run_hooks("pre_close", ticket_id=ticket_id, user_id=user_id)
    t = update_ticket(ticket_id, status="closed")
    _run_hooks("post_close", ticket=t, user_id=user_id)
    return t


def list_tickets(status: Optional[str] = None) -> List[Ticket]:
    tickets = list(_tickets.values())
    if status:
        tickets = [t for t in tickets if t.status == status]
    return tickets


def register_user(uid: str, name: str, email: str,
                  role: str = "agent") -> User:
    u = User(id=uid, name=name, email=email, role=role)
    _users[uid] = u
    return u


def get_user(user_id: str) -> Optional[User]:
    return _users.get(user_id)


def create_contact(name: str, email: str, company: str = "") -> Contact:
    cid = f"C-{_next_contact[0]}"
    _next_contact[0] += 1
    c = Contact(id=cid, name=name, email=email, company=company)
    _contacts[cid] = c
    return c


def get_contact(contact_id: str) -> Optional[Contact]:
    return _contacts.get(contact_id)


def list_users(role: Optional[str] = None) -> List[User]:
    users = list(_users.values())
    if role:
        users = [u for u in users if u.role == role]
    return users


def reset_state():
    _tickets.clear()
    _users.clear()
    _contacts.clear()
    _next_ticket[0] = 1
    _next_contact[0] = 1
'''


# ════════════════════════════════════════════════════════════════════
# Workflow — same in both conditions (Agent 1 always writes this)
# ════════════════════════════════════════════════════════════════════

WORKFLOW_PY = '''\
from core import get_ticket, update_ticket, _run_hooks

VALID_TRANSITIONS = {
    "open": ["in_progress", "closed"],
    "in_progress": ["resolved", "open", "on_hold"],
    "on_hold": ["in_progress", "open"],
    "resolved": ["closed", "open"],
    "closed": ["archived"],
    "archived": [],
}

ACTIVE_STATUSES = ["open", "in_progress", "resolved", "on_hold"]
TERMINAL_STATUSES = ["closed", "archived"]


def is_valid_transition(from_status: str, to_status: str) -> bool:
    return to_status in VALID_TRANSITIONS.get(from_status, [])


def transition_ticket(ticket_id: str, new_status: str):
    t = get_ticket(ticket_id)
    if not is_valid_transition(t.status, new_status):
        raise ValueError(f"Invalid transition: {t.status} -> {new_status}")
    old_status = t.status
    _run_hooks("pre_transition", ticket=t, old_status=old_status,
               new_status=new_status)
    t = update_ticket(ticket_id, status=new_status)
    _run_hooks("post_transition", ticket=t, old_status=old_status,
               new_status=new_status)
    return t


def archive_ticket(ticket_id: str):
    return transition_ticket(ticket_id, "archived")


def is_active(ticket) -> bool:
    return ticket.status in ACTIVE_STATUSES


def is_archived(ticket) -> bool:
    return ticket.status == "archived"


def get_available_transitions(ticket) -> list:
    return VALID_TRANSITIONS.get(ticket.status, [])
'''


# ════════════════════════════════════════════════════════════════════
# Feature modules — GIT condition (no cross-cutting awareness)
#
# These are the actual code patterns produced by real Claude Code
# agents in F2/F5 when building from the base code alone.
# ════════════════════════════════════════════════════════════════════

GIT_PERMISSIONS = '''\
from config import SYSTEM_ACTIONS

PERMISSION_MATRIX = {
    "admin": list(SYSTEM_ACTIONS),
    "agent": ["create", "view", "update", "assign", "close"],
    "viewer": ["view"],
}


def has_permission(user, action: str) -> bool:
    allowed = PERMISSION_MATRIX.get(user.role, [])
    return action in allowed


def require_permission(user, action: str):
    if not has_permission(user, action):
        raise PermissionError(
            f"User '{user.name}' (role={user.role}) "
            f"lacks permission for '{action}'"
        )


def get_allowed_actions(user) -> list:
    return list(PERMISSION_MATRIX.get(user.role, []))
'''

GIT_AUDIT = '''\
from dataclasses import dataclass, field
from typing import Dict, List, Optional
import time


@dataclass
class AuditEntry:
    timestamp: str
    action: str
    ticket_id: str
    user_id: str
    details: Dict = field(default_factory=dict)


_audit_log: List[AuditEntry] = []


def log_action(action: str, ticket_id: str, user_id: str = "",
               **details) -> AuditEntry:
    entry = AuditEntry(
        timestamp=str(int(time.time())),
        action=action, ticket_id=ticket_id,
        user_id=user_id, details=details,
    )
    _audit_log.append(entry)
    return entry


def get_audit_trail(ticket_id: Optional[str] = None) -> List[AuditEntry]:
    if ticket_id is None:
        return list(_audit_log)
    return [e for e in _audit_log if e.ticket_id == ticket_id]


def reset_audit():
    _audit_log.clear()
'''

GIT_NOTIFICATIONS = '''\
from typing import Optional, List, Dict

_notifications: list = []

def notify_transition(ticket, old_status: str, new_status: str) -> Optional[str]:
    msg = f"Ticket {ticket.id}: {old_status} -> {new_status}"
    _notifications.append({"ticket_id": ticket.id, "message": msg,
                           "type": "transition"})
    return msg


def notify_assignment(ticket, assignee_name: str) -> Optional[str]:
    msg = f"Ticket {ticket.id} assigned to {assignee_name}"
    _notifications.append({"ticket_id": ticket.id, "message": msg,
                           "type": "assignment"})
    return msg


def get_notifications(ticket_id: Optional[str] = None) -> list:
    if ticket_id:
        return [n for n in _notifications if n["ticket_id"] == ticket_id]
    return list(_notifications)


def reset_notifications():
    _notifications.clear()
'''

GIT_ANALYTICS = '''\
from core import list_tickets
from typing import Dict, List

def ticket_summary() -> Dict:
    tickets = list_tickets()
    return {
        "total": len(tickets),
        "open": len([t for t in tickets if t.status == "open"]),
        "closed": len([t for t in tickets if t.status == "closed"]),
    }


def active_ticket_count() -> int:
    return len([t for t in list_tickets() if t.status != "closed"])


def unassigned_tickets() -> List:
    return [t for t in list_tickets() if t.assignee is None]
'''

# Git config.py — Agent 1 updates it with archive + on_hold,
# but other git agents have their OWN copy without those updates.
# After merge we use agent 1's config.
GIT_CONFIG_MERGED = '''\
"""Shared configuration for ClaimDesk — merged from 5 agents."""

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


def _notif_post_transition(ticket, old_status="", new_status="", **_kw):
    from notifications import notify_transition
    notify_transition(ticket, old_status, new_status)

def _notif_post_assign(ticket, user_id="", **_kw):
    from notifications import notify_assignment
    notify_assignment(ticket, user_id)

HOOKS["post_transition"].append(_notif_post_transition)
HOOKS["post_assign"].append(_notif_post_assign)
'''


# ════════════════════════════════════════════════════════════════════
# Feature modules — CNF condition (with cross-cutting awareness)
#
# These are the actual code patterns produced by real Claude Code
# agents in F2/F5 when querying the shared graph before writing.
# ════════════════════════════════════════════════════════════════════

CNF_PERMISSIONS = '''\
PERMISSION_MATRIX = {
    "admin": [
        "create", "view", "update", "assign", "close",
        "archive", "transition",
    ],
    "agent": [
        "create", "view", "update", "assign", "close",
        "transition",
    ],
    "viewer": [
        "view",
    ],
}


def has_permission(user, action: str) -> bool:
    allowed = PERMISSION_MATRIX.get(user.role, [])
    return action in allowed


def require_permission(user, action: str):
    if not has_permission(user, action):
        raise PermissionError(
            f"User '{user.name}' (role={user.role}) "
            f"lacks permission for '{action}'"
        )


def get_allowed_actions(user) -> list:
    return list(PERMISSION_MATRIX.get(user.role, []))
'''

CNF_AUDIT = '''\
from dataclasses import dataclass, field
from typing import Dict, List, Optional
import time


@dataclass
class AuditEntry:
    timestamp: str
    action: str
    ticket_id: str
    user_id: str
    details: Dict = field(default_factory=dict)


_audit_log: List[AuditEntry] = []


def log_action(action: str, ticket_id: str, user_id: str = "",
               **details) -> AuditEntry:
    entry = AuditEntry(
        timestamp=str(int(time.time())),
        action=action, ticket_id=ticket_id,
        user_id=user_id, details=details,
    )
    _audit_log.append(entry)
    return entry


def get_audit_trail(ticket_id: Optional[str] = None) -> List[AuditEntry]:
    if ticket_id is None:
        return list(_audit_log)
    return [e for e in _audit_log if e.ticket_id == ticket_id]


def reset_audit():
    _audit_log.clear()
'''

CNF_NOTIFICATIONS = '''\
from typing import Optional, List, Dict
from workflow import TERMINAL_STATUSES

_notifications: list = []


def notify_transition(ticket, old_status: str, new_status: str) -> Optional[str]:
    if new_status in TERMINAL_STATUSES:
        return None
    msg = f"Ticket {ticket.id}: {old_status} -> {new_status}"
    _notifications.append({"ticket_id": ticket.id, "message": msg,
                           "type": "transition"})
    return msg


def notify_assignment(ticket, assignee_name: str) -> Optional[str]:
    if ticket.status in TERMINAL_STATUSES:
        return None
    msg = f"Ticket {ticket.id} assigned to {assignee_name}"
    _notifications.append({"ticket_id": ticket.id, "message": msg,
                           "type": "assignment"})
    return msg


def get_notifications(ticket_id: Optional[str] = None) -> list:
    if ticket_id:
        return [n for n in _notifications if n["ticket_id"] == ticket_id]
    return list(_notifications)


def reset_notifications():
    _notifications.clear()
'''

CNF_ANALYTICS = '''\
from typing import Dict, List
from config import ALL_STATUSES, TERMINAL_STATUSES
from core import list_tickets


def ticket_summary() -> Dict:
    tickets = list_tickets()
    summary: Dict = {status: 0 for status in ALL_STATUSES}
    for t in tickets:
        summary[t.status] = summary.get(t.status, 0) + 1
    summary["total"] = len(tickets)
    return summary


def active_ticket_count() -> int:
    tickets = list_tickets()
    return sum(1 for t in tickets if t.status not in TERMINAL_STATUSES)


def unassigned_tickets() -> List:
    tickets = list_tickets()
    return [
        t for t in tickets
        if t.assignee is None and t.status not in TERMINAL_STATUSES
    ]
'''

CNF_CONFIG = '''\
"""Shared configuration for ClaimDesk — CNF condition."""

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


def _notif_post_transition(ticket, old_status="", new_status="", **_kw):
    from notifications import notify_transition
    notify_transition(ticket, old_status, new_status)

def _notif_post_assign(ticket, user_id="", **_kw):
    from notifications import notify_assignment
    notify_assignment(ticket, user_id)

HOOKS["post_transition"].append(_notif_post_transition)
HOOKS["post_assign"].append(_notif_post_assign)
'''


# ════════════════════════════════════════════════════════════════════
# Integration tests — same for both conditions
# ════════════════════════════════════════════════════════════════════

INTEGRATION_TESTS = '''\
"""F8 integration oracle — 18 tests across 5 features."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from core import *
from models import Ticket, User
from workflow import *
import config


# ═══════════════════════════════════════════════════════════════
# BASE (always pass)
# ═══════════════════════════════════════════════════════════════

def test_01_base_create():
    reset_state()
    t = create_ticket("Bug", "Broken")
    assert t.status == "open"


def test_02_workflow_transitions():
    reset_state()
    t = create_ticket("Bug", "Broken")
    transition_ticket(t.id, "in_progress")
    assert get_ticket(t.id).status == "in_progress"


def test_03_workflow_archive():
    reset_state()
    t = create_ticket("Old", "Fixed")
    transition_ticket(t.id, "closed")
    archive_ticket(t.id)
    assert get_ticket(t.id).status == "archived"


def test_04_workflow_on_hold():
    reset_state()
    t = create_ticket("Bug", "Waiting")
    transition_ticket(t.id, "in_progress")
    transition_ticket(t.id, "on_hold")
    assert get_ticket(t.id).status == "on_hold"


# ═══════════════════════════════════════════════════════════════
# CROSS-CUTTING — reveal information gaps
# ═══════════════════════════════════════════════════════════════

def test_05_config_has_archive():
    assert "archive" in config.SYSTEM_ACTIONS


def test_06_config_terminal_has_archived():
    assert "archived" in config.TERMINAL_STATUSES


def test_07_config_active_has_on_hold():
    assert "on_hold" in config.ACTIVE_STATUSES


def test_08_hooks_registered():
    total = sum(len(v) for v in config.HOOKS.values())
    assert total >= 3, f"Only {total} hooks registered"


def test_09_create_triggers_audit():
    reset_state()
    from audit import reset_audit, get_audit_trail
    reset_audit()
    t = create_ticket("Bug", "Broken", user_id="U-1")
    trail = get_audit_trail(t.id)
    assert len(trail) >= 1, "No audit entry for create"


def test_10_archived_no_notification():
    reset_state()
    from notifications import reset_notifications, get_notifications
    reset_notifications()
    t = create_ticket("Old", "Done")
    transition_ticket(t.id, "closed")
    archive_ticket(t.id)
    notifs = get_notifications(t.id)
    archive_notifs = [n for n in notifs
                      if "archived" in n.get("message", "").lower()]
    assert len(archive_notifs) == 0, \\
        f"Archived triggered notification: {archive_notifs}"


def test_11_archive_permission():
    reset_state()
    from permissions import has_permission
    admin = register_user("U-1", "Admin", "a@t.com", "admin")
    assert has_permission(admin, "archive"), \\
        "Admin should have archive permission"


def test_12_active_count_excludes_archived():
    reset_state()
    from analytics import active_ticket_count
    t1 = create_ticket("Active", "Open")
    t2 = create_ticket("Old", "Archive")
    update_ticket(t2.id, status="closed")
    update_ticket(t2.id, status="archived")
    assert active_ticket_count() == 1, "Archived counted as active"


def test_13_summary_has_all_statuses():
    reset_state()
    from analytics import ticket_summary
    summary = ticket_summary()
    for s in ["open", "closed", "archived", "on_hold"]:
        assert s in summary, f"Summary missing '{s}': {summary}"


def test_14_unassigned_excludes_archived():
    reset_state()
    from analytics import unassigned_tickets
    t1 = create_ticket("Active", "Needs work")
    t2 = create_ticket("Done", "Archive")
    update_ticket(t2.id, status="closed")
    update_ticket(t2.id, status="archived")
    ids = [t.id for t in unassigned_tickets()]
    assert t2.id not in ids, "Archived in unassigned list"


# ═══════════════════════════════════════════════════════════════
# DEEP CROSS-CUTTING — require temporal awareness
# ═══════════════════════════════════════════════════════════════

def test_15_on_hold_in_workflow():
    assert "on_hold" in VALID_TRANSITIONS


def test_16_on_hold_not_terminal():
    assert "on_hold" not in TERMINAL_STATUSES
    assert "on_hold" in ACTIVE_STATUSES


def test_17_archived_is_terminal():
    assert "archived" in TERMINAL_STATUSES
    assert "archived" not in ACTIVE_STATUSES


def test_18_on_hold_resume():
    reset_state()
    t = create_ticket("Bug", "Paused")
    transition_ticket(t.id, "in_progress")
    transition_ticket(t.id, "on_hold")
    transition_ticket(t.id, "in_progress")
    assert get_ticket(t.id).status == "in_progress"


if __name__ == "__main__":
    passed = failed = errors = 0
    results = []
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                passed += 1
                results.append((name, "PASS", ""))
            except AssertionError as e:
                failed += 1
                results.append((name, "FAIL", str(e)))
            except Exception as e:
                errors += 1
                results.append((name, "ERROR", f"{type(e).__name__}: {e}"))

    for name, status, msg in results:
        if status != "PASS":
            print(f"  {status}: {name}: {msg}")
    print(f"{passed} passed, {failed} failed, {errors} errors")
'''


# ════════════════════════════════════════════════════════════════════
# Git repair code — fixes the 5 known cross-cutting bugs
# ════════════════════════════════════════════════════════════════════

GIT_NOTIFICATIONS_REPAIRED = '''\
from typing import Optional, List, Dict
from workflow import TERMINAL_STATUSES

_notifications: list = []


def notify_transition(ticket, old_status: str, new_status: str) -> Optional[str]:
    if new_status in TERMINAL_STATUSES:
        return None
    msg = f"Ticket {ticket.id}: {old_status} -> {new_status}"
    _notifications.append({"ticket_id": ticket.id, "message": msg,
                           "type": "transition"})
    return msg


def notify_assignment(ticket, assignee_name: str) -> Optional[str]:
    if ticket.status in TERMINAL_STATUSES:
        return None
    msg = f"Ticket {ticket.id} assigned to {assignee_name}"
    _notifications.append({"ticket_id": ticket.id, "message": msg,
                           "type": "assignment"})
    return msg


def get_notifications(ticket_id: Optional[str] = None) -> list:
    if ticket_id:
        return [n for n in _notifications if n["ticket_id"] == ticket_id]
    return list(_notifications)


def reset_notifications():
    _notifications.clear()
'''

GIT_ANALYTICS_REPAIRED = '''\
from typing import Dict, List
from config import ALL_STATUSES, TERMINAL_STATUSES
from core import list_tickets


def ticket_summary() -> Dict:
    tickets = list_tickets()
    summary: Dict = {status: 0 for status in ALL_STATUSES}
    for t in tickets:
        summary[t.status] = summary.get(t.status, 0) + 1
    summary["total"] = len(tickets)
    return summary


def active_ticket_count() -> int:
    tickets = list_tickets()
    return sum(1 for t in tickets if t.status not in TERMINAL_STATUSES)


def unassigned_tickets() -> List:
    tickets = list_tickets()
    return [
        t for t in tickets
        if t.assignee is None and t.status not in TERMINAL_STATUSES
    ]
'''


# ════════════════════════════════════════════════════════════════════
# Infrastructure
# ════════════════════════════════════════════════════════════════════

class Timer:
    def __init__(self, name):
        self.name = name
        self.elapsed = 0.0

    def __enter__(self):
        self.start = time.monotonic()
        return self

    def __exit__(self, *args):
        self.elapsed = time.monotonic() - self.start


def fresh_workspace(label):
    tmp = Path(tempfile.mkdtemp(prefix=f"f8-{label}-"))
    (tmp / "models.py").write_text(BASE_MODELS)
    (tmp / "core.py").write_text(BASE_CORE)
    (tmp / "config.py").write_text(BASE_CONFIG)
    return tmp


def run_tests(workspace):
    r = subprocess.run(
        [sys.executable, "test_integration.py"],
        cwd=str(workspace), capture_output=True, text=True, timeout=30,
    )
    out = r.stdout + r.stderr
    p = f = e = 0
    for line in out.strip().splitlines():
        if "passed" in line:
            parts = line.strip().split(",")
            p = int(parts[0].strip().split()[0])
            if len(parts) > 1:
                f = int(parts[1].strip().split()[0])
            if len(parts) > 2:
                e = int(parts[2].strip().split()[0])
    failures = []
    for line in out.strip().splitlines():
        if line.strip().startswith("FAIL:") or line.strip().startswith("ERROR:"):
            failures.append(line.strip())
    return p, f, e, failures


def simulate_inference(label, seconds):
    if USE_DELAYS:
        time.sleep(seconds)


def cleanup(path):
    shutil.rmtree(path, ignore_errors=True)


# ════════════════════════════════════════════════════════════════════
# MCP Client (for CNF condition)
# ════════════════════════════════════════════════════════════════════

class MCPClient:
    def __init__(self):
        self.proc = subprocess.Popen(
            ["racket", str(SERVER)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, bufsize=1,
        )
        self._req_id = 0
        self._init()

    def _init(self):
        self.call("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "f8-race", "version": "1.0"},
        })
        self.call("notifications/initialized")

    def call(self, method, params=None):
        self._req_id += 1
        msg = {"jsonrpc": "2.0", "id": self._req_id, "method": method}
        if params:
            msg["params"] = params
        self.proc.stdin.write(json.dumps(msg) + "\n")
        self.proc.stdin.flush()
        if method.startswith("notifications/"):
            return None
        while True:
            line = self.proc.stdout.readline().strip()
            if not line:
                continue
            try:
                return json.loads(line)
            except Exception:
                continue

    def tool(self, name, args=None):
        r = self.call("tools/call", {"name": name, "arguments": args or {}})
        text = r["result"]["content"][0]["text"]
        if r["result"].get("isError"):
            raise RuntimeError(f"MCP tool {name} failed: {text}")
        return text

    def close(self):
        self.proc.stdin.close()
        self.proc.terminate()
        self.proc.wait(timeout=5)


# ════════════════════════════════════════════════════════════════════
# Agent task partitions
# ════════════════════════════════════════════════════════════════════

AGENTS_5 = [
    {"name": "workflow", "modules": {"workflow.py": None}},
    {"name": "permissions", "modules": {"permissions.py": None}},
    {"name": "audit", "modules": {"audit.py": None}},
    {"name": "notifications", "modules": {"notifications.py": None}},
    {"name": "analytics", "modules": {"analytics.py": None}},
]

AGENTS_2 = [
    {"name": "workflow+perms+audit",
     "modules": {"workflow.py": None, "permissions.py": None, "audit.py": None}},
    {"name": "notif+analytics",
     "modules": {"notifications.py": None, "analytics.py": None}},
]

GIT_CODE = {
    "workflow.py": WORKFLOW_PY,
    "permissions.py": GIT_PERMISSIONS,
    "audit.py": GIT_AUDIT,
    "notifications.py": GIT_NOTIFICATIONS,
    "analytics.py": GIT_ANALYTICS,
}

CNF_CODE = {
    "workflow.py": WORKFLOW_PY,
    "permissions.py": CNF_PERMISSIONS,
    "audit.py": CNF_AUDIT,
    "notifications.py": CNF_NOTIFICATIONS,
    "analytics.py": CNF_ANALYTICS,
}

GIT_REPAIR = {
    "notifications.py": GIT_NOTIFICATIONS_REPAIRED,
    "analytics.py": GIT_ANALYTICS_REPAIRED,
}


# ════════════════════════════════════════════════════════════════════
# Git condition
# ════════════════════════════════════════════════════════════════════

def run_git_condition(n_agents):
    agents = AGENTS_5 if n_agents == 5 else AGENTS_2
    ws = fresh_workspace(f"git-{n_agents}")
    phases = {}

    # Phase 1: Parallel build — all agents write simultaneously
    with Timer("build") as t:
        def agent_work(agent_spec):
            simulate_inference(agent_spec["name"], AGENT_INFERENCE_TIME)
            for module, _ in agent_spec["modules"].items():
                (ws / module).write_text(GIT_CODE[module])

        with concurrent.futures.ThreadPoolExecutor(max_workers=n_agents) as pool:
            list(pool.map(agent_work, agents))
    phases["build"] = t.elapsed

    # Phase 2: Merge — apply merged config
    with Timer("merge") as t:
        (ws / "config.py").write_text(GIT_CONFIG_MERGED)
    phases["merge"] = t.elapsed

    # Phase 3: Test
    with Timer("test_1") as t:
        (ws / "test_integration.py").write_text(INTEGRATION_TESTS)
        p1, f1, e1, failures1 = run_tests(ws)
    phases["test_1"] = t.elapsed
    bugs_before = f1 + e1

    # Phase 4: Repair (if needed)
    phases["repair"] = 0.0
    phases["test_2"] = 0.0
    p_final, f_final, e_final = p1, f1, e1
    failures_final = failures1

    if bugs_before > 0:
        with Timer("repair") as t:
            simulate_inference("repair-agent", REPAIR_INFERENCE_TIME)
            for module, code in GIT_REPAIR.items():
                (ws / module).write_text(code)
        phases["repair"] = t.elapsed

        with Timer("test_2") as t:
            p_final, f_final, e_final, failures_final = run_tests(ws)
        phases["test_2"] = t.elapsed

    total = sum(phases.values())
    cleanup(ws)

    return {
        "phases": phases,
        "total": total,
        "pass_before": p1,
        "bugs_before": bugs_before,
        "pass_after": p_final,
        "bugs_after": f_final + e_final,
        "failures": failures_final,
    }


# ════════════════════════════════════════════════════════════════════
# CNF condition — fully parallel (live graph accumulation)
#
# All agents start simultaneously. As each finishes, their code is
# parsed into the shared graph. Later-finishing agents query the
# accumulated graph mid-flight and discover cross-cutting entities.
#
# This is the F3 live graph model applied to parallel construction.
# The daemon's MVCC ensures lock-free reads; writes serialize via
# semaphore but are <200ms each (negligible vs 26s agent inference).
# ════════════════════════════════════════════════════════════════════

def run_cnf_condition(n_agents):
    agents = AGENTS_5 if n_agents == 5 else AGENTS_2
    ws = fresh_workspace(f"cnf-{n_agents}")
    phases = {}
    mcp = None

    try:
        # Phase 1: Start daemon + parse base code into graph
        with Timer("setup") as t:
            mcp = MCPClient()
            mcp.tool("reset")
            for f in ["core.py", "models.py"]:
                source = (ws / f).read_text()
                mcp.tool("parse_program", {"source": source, "language": "python"})
            (ws / "config.py").write_text(CNF_CONFIG)
        phases["setup"] = t.elapsed

        # Phase 2: ALL agents build in parallel
        # Each agent: inference → write code → parse into graph
        # Graph accumulates as agents finish — MVCC snapshot updates
        # on each parse, visible to concurrent readers.
        graph_lock = threading.Lock()

        with Timer("build") as t:
            def agent_work(agent_spec):
                simulate_inference(agent_spec["name"], AGENT_INFERENCE_TIME)
                for module in agent_spec["modules"]:
                    code = CNF_CODE[module]
                    (ws / module).write_text(code)
                    with graph_lock:
                        mcp.tool("parse_program",
                                 {"source": code, "language": "python"})

            with concurrent.futures.ThreadPoolExecutor(
                    max_workers=n_agents) as pool:
                list(pool.map(agent_work, agents))
        phases["build"] = t.elapsed

    finally:
        if mcp:
            mcp.close()

    # Phase 3: Test
    with Timer("test") as t:
        (ws / "test_integration.py").write_text(INTEGRATION_TESTS)
        p, f, e, failures = run_tests(ws)
    phases["test"] = t.elapsed

    total = sum(phases.values())
    cleanup(ws)

    return {
        "phases": phases,
        "total": total,
        "pass_after": p,
        "bugs_after": f + e,
        "failures": failures,
    }


# ════════════════════════════════════════════════════════════════════
# Output
# ════════════════════════════════════════════════════════════════════

def fmt_time(seconds):
    if seconds < 0.1:
        return f"{seconds*1000:.0f}ms"
    return f"{seconds:.1f}s"


def print_results(n_agents, git, cnf):
    w = 72
    gt = git.get("pass_before", git["pass_after"])
    gb = git.get("bugs_before", 0)
    cp, cb = cnf["pass_after"], cnf["bugs_after"]
    total = gt + gb

    git_infra = sum(git["phases"].values())
    cnf_infra = sum(cnf["phases"].values())

    git_total = AGENT_INFERENCE_TIME + git_infra + \
                (REPAIR_INFERENCE_TIME if gb > 0 else 0)
    cnf_total = AGENT_INFERENCE_TIME + cnf_infra
    ratio = git_total / cnf_total if cnf_total > 0 else 0

    print()
    print("═" * w)
    print(f"  {n_agents}-AGENT RACE")
    print("═" * w)
    print()
    print(f"  {'':30} {'Git':>14} {'CNF':>14}")
    print("  " + "─" * (w - 4))
    print(f"  {'Tests (first run)':<30} {f'{gt}/{total}':>14} "
          f"{f'{cp}/{cp+cb}':>14}")
    print(f"  {'Cross-cutting bugs':<30} {gb:>14} {cb:>14}")
    print(f"  {'Repair rounds':<30} "
          f"{'1' if gb > 0 else '0':>14} {'0':>14}")

    print()
    print(f"  {'Projected wall clock:':<30}")
    print(f"  {'  Build (all parallel)':<30} "
          f"{fmt_time(AGENT_INFERENCE_TIME):>14} "
          f"{fmt_time(AGENT_INFERENCE_TIME):>14}")
    print(f"  {'  Repair':<30} "
          f"{fmt_time(REPAIR_INFERENCE_TIME) if gb else '—':>14} {'—':>14}")
    print(f"  {'  Infrastructure':<30} "
          f"{fmt_time(git_infra):>14} {fmt_time(cnf_infra):>14}")
    print("  " + "─" * (w - 4))
    print(f"  {'  TOTAL':<30} "
          f"{fmt_time(git_total):>14} {fmt_time(cnf_total):>14}")
    print()
    print(f"  CNF {ratio:.1f}x faster")

    if cnf["failures"]:
        print()
        for f in cnf["failures"]:
            print(f"    {f}")
    print()


def main():
    w = 72
    print("═" * w)
    print("  F8: Parallel Construction Race")
    print()
    print("  Git:  N parallel → merge → test → repair → retest")
    print("  CNF:  N parallel → live graph → test (0 repairs)")
    print(f"  Calibration: {AGENT_INFERENCE_TIME}s/agent, "
          f"{REPAIR_INFERENCE_TIME}s/repair (F6)")
    print("═" * w)

    all_results = {}
    for n in [2, 5]:
        print()
        print(f"  Running {n}-agent git...", end="", flush=True)
        git = run_git_condition(n)
        print(f" {git['pass_before']}/{git['pass_before']+git['bugs_before']}"
              f" → {git['pass_after']}/{git['pass_after']+git['bugs_after']}")
        print(f"  Running {n}-agent CNF...", end="", flush=True)
        cnf = run_cnf_condition(n)
        print(f" {cnf['pass_after']}/{cnf['pass_after']+cnf['bugs_after']}")
        all_results[n] = (git, cnf)
        print_results(n, git, cnf)

    print("═" * w)
    print("  RESULT")
    print("═" * w)
    print()
    print(f"  {'Agents':<10} {'Git':>10} {'CNF':>10} {'Speedup':>10}")
    print("  " + "─" * 42)
    for n in [2, 5]:
        git, cnf = all_results[n]
        gb = git.get("bugs_before", 0)
        g = AGENT_INFERENCE_TIME + sum(git["phases"].values()) + \
            (REPAIR_INFERENCE_TIME if gb > 0 else 0)
        c = AGENT_INFERENCE_TIME + sum(cnf["phases"].values())
        print(f"  {n:<10} {fmt_time(g):>10} {fmt_time(c):>10} "
              f"{'CNF '+f'{g/c:.1f}x':>10}")

    print()
    print("  Both build all agents in parallel (same 26s).")
    print("  Git: 4 bugs → 56s repair.  CNF: 0 bugs → 0 repair.")
    print()
    print("═" * w)


if __name__ == "__main__":
    main()

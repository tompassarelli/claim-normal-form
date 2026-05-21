#!/usr/bin/env python3
"""F9: Real Parallel Race — real Claude Code agents, wall clock measurement.

6 agents build a CRM app in parallel. Git vs CNF conditions.
Agents are real Claude Sonnet instances making real decisions.

Git condition:  agents see base code only, build blind to other features
CNF condition:  agents see base code + structural context from claim graph

Usage:
    python runner.py                # Run both conditions
    python runner.py --git-only     # Git condition only
    python runner.py --cnf-only     # CNF condition only
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
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()

# ════════════════════════════════════════════════════════════════════
# Base code — given to all agents in their prompt
# ════════════════════════════════════════════════════════════════════

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


# ════════════════════════════════════════════════════════════════════
# Workflow — pre-written infrastructure (not a feature under test)
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
ALL_STATUSES = ACTIVE_STATUSES + TERMINAL_STATUSES


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
# Merged config — applied after all agents finish, before testing
# Registers hooks that call into agent-written modules
# ════════════════════════════════════════════════════════════════════

MERGED_CONFIG = '''\
"""Shared configuration for ClaimDesk — merged."""

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
    log_action("transition", ticket.id, old_status=old_status,
               new_status=new_status)

def _audit_post_assign(ticket, user_id="", assigned_by="", **_kw):
    from audit import log_action
    log_action("assign", ticket.id, user_id=assigned_by or user_id,
               assignee=user_id)

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
# Integration tests — 22 tests across 6 features
# ════════════════════════════════════════════════════════════════════

INTEGRATION_TESTS = '''\
"""F9 integration tests — 22 tests across 6 features + cross-cutting."""
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
# CONFIG / HOOKS (test merged config)
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


# ═══════════════════════════════════════════════════════════════
# CROSS-CUTTING — reveal information gaps
# ═══════════════════════════════════════════════════════════════

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
        assert s in summary, f"Summary missing \\'{s}\\': {summary}"


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
# DEEP CROSS-CUTTING — temporal awareness
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


# ═══════════════════════════════════════════════════════════════
# ESCALATION — cross-cutting with archived
# ═══════════════════════════════════════════════════════════════

def test_19_escalation_active():
    reset_state()
    from escalation import should_escalate, reset_escalations
    reset_escalations()
    t = create_ticket("Urgent", "Critical issue")
    update_ticket(t.id, priority="critical")
    ticket = get_ticket(t.id)
    assert should_escalate(ticket), \\
        "Active critical ticket should be escalatable"


def test_20_escalation_skip_archived():
    reset_state()
    from escalation import should_escalate, reset_escalations
    reset_escalations()
    t = create_ticket("Old", "Done")
    update_ticket(t.id, priority="critical", status="closed")
    update_ticket(t.id, status="archived")
    ticket = get_ticket(t.id)
    assert not should_escalate(ticket), \\
        "Archived ticket should NOT be escalatable"


# ═══════════════════════════════════════════════════════════════
# COMMENTS — cross-cutting with archived
# ═══════════════════════════════════════════════════════════════

def test_21_comments_active():
    reset_state()
    from comments import add_comment, reset_comments
    reset_comments()
    t = create_ticket("Bug", "Help")
    result = add_comment(t.id, "U-1", "Looking into this")
    assert result is not None, \\
        "Should be able to comment on active ticket"


def test_22_comments_block_archived():
    reset_state()
    from comments import add_comment, reset_comments
    reset_comments()
    t = create_ticket("Old", "Done")
    update_ticket(t.id, status="closed")
    update_ticket(t.id, status="archived")
    result = add_comment(t.id, "U-1", "Should fail")
    assert result is None, \\
        "Should NOT be able to comment on archived ticket"


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
# Agent prompts
# ════════════════════════════════════════════════════════════════════

PROMPT_CORE = '''\
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


def create_ticket(title: str, description: str, contact_email: str = "",
                  priority: str = "medium") -> Ticket:
    tid = f"T-{_next_ticket[0]}"
    _next_ticket[0] += 1
    now = _now()
    t = Ticket(id=tid, title=title, description=description,
               contact_email=contact_email, priority=priority,
               created_at=now, updated_at=now)
    _tickets[tid] = t
    return t


def get_ticket(ticket_id: str) -> Optional[Ticket]:
    return _tickets.get(ticket_id)


def update_ticket(ticket_id: str, **fields) -> Ticket:
    t = _tickets[ticket_id]
    for k, v in fields.items():
        setattr(t, k, v)
    t.updated_at = _now()
    return t


def assign_ticket(ticket_id: str, user_id: str) -> Ticket:
    return update_ticket(ticket_id, assignee=user_id)


def close_ticket(ticket_id: str) -> Ticket:
    return update_ticket(ticket_id, status="closed")


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

COMMON_PREAMBLE = """\
You are building a feature module for ClaimDesk, a Python CRM/helpdesk application.

Here is the existing codebase:

=== models.py ===
{models}

=== core.py ===
{core}

Write ONLY the requested Python module. Output ONLY valid Python code.
No markdown fences, no explanations, no commentary — just the code."""

AGENTS = [
    {
        "name": "permissions",
        "module": "permissions.py",
        "task": """
Write permissions.py.

Required interface:
- PERMISSION_MATRIX: dict mapping role string to list of allowed action strings
- has_permission(user, action: str) -> bool
- require_permission(user, action: str) — raises PermissionError if denied
- get_allowed_actions(user) -> list

Three roles: admin (full access to all system actions), agent (standard
ticket operations), viewer (read-only). Design the permission matrix
based on what actions you see exist in the system from reading the base code.""",
        "cnf_context": """
ADDITIONAL CONTEXT FROM CODEBASE SEMANTIC GRAPH:
The system includes these actions: create, view, update, assign, close,
archive, transition. archive_ticket() transitions tickets to the "archived"
state. Include ALL system actions in the admin permission set.""",
    },
    {
        "name": "audit",
        "module": "audit.py",
        "task": """
Write audit.py.

Required interface:
- AuditEntry dataclass: timestamp (str), action (str), ticket_id (str),
  user_id (str), details (Dict, default_factory=dict)
- log_action(action: str, ticket_id: str, user_id: str = "", **details) -> AuditEntry
- get_audit_trail(ticket_id: Optional[str] = None) -> List[AuditEntry]
- reset_audit()

Use _audit_log (list) for in-memory storage. Import time for timestamps.
Record all ticket actions.""",
        "cnf_context": """
ADDITIONAL CONTEXT FROM CODEBASE SEMANTIC GRAPH:
All ticket transitions should be recorded in the audit trail, including
transitions to terminal states (closed, archived).""",
    },
    {
        "name": "notifications",
        "module": "notifications.py",
        "task": """
Write notifications.py.

Required interface:
- notify_transition(ticket, old_status: str, new_status: str) -> Optional[str]
  Returns message string if notification sent, None if suppressed.
- notify_assignment(ticket, assignee_name: str) -> Optional[str]
  Returns message string if notification sent, None if suppressed.
- get_notifications(ticket_id: Optional[str] = None) -> list
- reset_notifications()

Store notifications in _notifications list as dicts with keys:
ticket_id, message, type ("transition" or "assignment").

Consider the lifecycle of tickets when deciding which transitions should
and should not generate notifications.""",
        "cnf_context": """
ADDITIONAL CONTEXT FROM CODEBASE SEMANTIC GRAPH:
TERMINAL_STATUSES = ["closed", "archived"]. ACTIVE_STATUSES = ["open",
"in_progress", "resolved", "on_hold"]. Archived tickets are terminal —
transitions TO archived status should NOT generate notifications
(archiving is housekeeping, not customer-facing). Import TERMINAL_STATUSES
from the workflow module.""",
    },
    {
        "name": "analytics",
        "module": "analytics.py",
        "task": """
Write analytics.py.

Required interface:
- ticket_summary() -> Dict — keys should include each possible ticket
  status plus 'total'
- active_ticket_count() -> int — count of tickets in active states
- unassigned_tickets() -> List — Ticket objects with no assignee that
  still need attention

Import list_tickets from core. Write analytics functions based on the
ticket statuses and fields you observe in the base code.""",
        "cnf_context": """
ADDITIONAL CONTEXT FROM CODEBASE SEMANTIC GRAPH:
ACTIVE_STATUSES = ["open", "in_progress", "resolved", "on_hold"].
TERMINAL_STATUSES = ["closed", "archived"]. ALL_STATUSES =
ACTIVE_STATUSES + TERMINAL_STATUSES. ticket_summary should include
counts for ALL possible statuses (including archived, on_hold).
active_ticket_count should only count non-terminal tickets.
unassigned_tickets should only return active tickets needing
attention — NOT terminal tickets. Import status lists from the
workflow module.""",
    },
    {
        "name": "escalation",
        "module": "escalation.py",
        "task": """
Write escalation.py.

Required interface:
- should_escalate(ticket) -> bool — True if ticket needs escalation
  (high or critical priority AND still active/needs attention)
- escalate_ticket(ticket_id: str, reason: str = "") -> Optional[dict]
  Returns escalation record dict or None if ticket shouldn't be escalated
- get_escalations(ticket_id: Optional[str] = None) -> list
- reset_escalations()

Store escalations in _escalations list as dicts with keys:
ticket_id, reason, timestamp. Import get_ticket from core.
Only escalate tickets that are active and genuinely need attention.""",
        "cnf_context": """
ADDITIONAL CONTEXT FROM CODEBASE SEMANTIC GRAPH:
TERMINAL_STATUSES = ["closed", "archived"]. Archived tickets are
terminal and should NEVER be escalated. Import TERMINAL_STATUSES
from the workflow module to check if a ticket is still active.""",
    },
    {
        "name": "comments",
        "module": "comments.py",
        "task": """
Write comments.py.

Required interface:
- add_comment(ticket_id: str, user_id: str, text: str) -> Optional[dict]
  Returns comment dict (with keys: ticket_id, user_id, text, timestamp)
  or None if commenting is not allowed on this ticket.
- get_comments(ticket_id: Optional[str] = None) -> list
- reset_comments()

Store comments in _comments list. Import get_ticket from core.
Only allow comments on tickets that are still active and open for
discussion.""",
        "cnf_context": """
ADDITIONAL CONTEXT FROM CODEBASE SEMANTIC GRAPH:
TERMINAL_STATUSES = ["closed", "archived"]. Archived tickets are
terminal — do NOT allow comments on them. Import TERMINAL_STATUSES
from the workflow module to check if commenting is allowed.""",
    },
]


# ════════════════════════════════════════════════════════════════════
# Infrastructure
# ════════════════════════════════════════════════════════════════════

def build_prompt(agent_spec, condition):
    prompt = COMMON_PREAMBLE.format(
        models=BASE_MODELS, core=PROMPT_CORE
    )
    prompt += "\n\n" + agent_spec["task"]
    if condition == "cnf":
        prompt += "\n" + agent_spec["cnf_context"]
    return prompt


def extract_code(text):
    if not text:
        return None
    match = re.search(r'```python\n(.*?)```', text, re.DOTALL)
    if match:
        return match.group(1).strip()
    match = re.search(r'```\n(.*?)```', text, re.DOTALL)
    if match:
        return match.group(1).strip()
    lines = text.strip().split('\n')
    py_starts = ('import ', 'from ', 'def ', 'class ', '"""', "'''",
                 '_', '@dataclass', '@')
    for i, line in enumerate(lines):
        stripped = line.lstrip()
        if any(stripped.startswith(s) for s in py_starts):
            code = '\n'.join(lines[i:]).strip()
            code = re.sub(r'\n```\s*$', '', code)
            return code
    return text.strip()


def launch_agent(agent_spec, condition, timeout=180):
    prompt = build_prompt(agent_spec, condition)
    name = agent_spec["name"]
    start = time.monotonic()
    try:
        result = subprocess.run(
            ["claude", "-p", "--model", "sonnet", "--tools", ""],
            input=prompt, capture_output=True, text=True, timeout=timeout,
        )
        elapsed = time.monotonic() - start
        code = extract_code(result.stdout)
        if code:
            return {"name": name, "code": code, "elapsed": elapsed,
                    "error": None}
        else:
            return {"name": name, "code": None, "elapsed": elapsed,
                    "error": f"No code in output: {result.stdout[:200]}"}
    except subprocess.TimeoutExpired:
        elapsed = time.monotonic() - start
        return {"name": name, "code": None, "elapsed": elapsed,
                "error": "timeout"}
    except Exception as e:
        elapsed = time.monotonic() - start
        return {"name": name, "code": None, "elapsed": elapsed,
                "error": str(e)}


def fresh_workspace(label):
    tmp = Path(tempfile.mkdtemp(prefix=f"f9-{label}-"))
    return tmp


def save_agent_outputs(agent_results, condition):
    out_dir = SCRIPT_DIR / condition
    out_dir.mkdir(exist_ok=True)
    for r in agent_results:
        if r["code"]:
            (out_dir / f"{r['name']}.py").write_text(r["code"])


def assemble_workspace(ws, agent_results):
    (ws / "models.py").write_text(BASE_MODELS)
    (ws / "core.py").write_text(BASE_CORE)
    (ws / "config.py").write_text(MERGED_CONFIG)
    (ws / "workflow.py").write_text(WORKFLOW_PY)
    (ws / "test_integration.py").write_text(INTEGRATION_TESTS)
    for r in agent_results:
        if r["code"]:
            (ws / f"{r['name']}.py").write_text(r["code"])


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
        if line.strip().startswith("FAIL:") or line.strip().startswith(
                "ERROR:"):
            failures.append(line.strip())
    return p, f, e, failures


def launch_repair(workspace, failures, timeout=300):
    failure_text = "\n".join(failures)
    prompt = f"""\
Fix the failing tests in the workspace at {workspace}.

Test failures:
{failure_text}

The workspace contains:
- models.py, core.py, config.py (base code — do NOT modify)
- workflow.py (defines TERMINAL_STATUSES = ["closed", "archived"],
  ACTIVE_STATUSES = ["open", "in_progress", "resolved", "on_hold"])
- permissions.py, audit.py, notifications.py, analytics.py,
  escalation.py, comments.py (feature modules — fix these)
- test_integration.py (test oracle — do NOT modify)

Read workflow.py to understand the full ticket lifecycle.
Read the failing modules. Fix them to handle archived/on_hold correctly.
Import TERMINAL_STATUSES from workflow where needed.
Write each corrected file."""

    start = time.monotonic()
    try:
        result = subprocess.run(
            ["claude", "-p", "--model", "sonnet",
             "--dangerously-skip-permissions",
             "--add-dir", str(workspace)],
            input=prompt, capture_output=True, text=True, timeout=timeout,
        )
        elapsed = time.monotonic() - start
        return elapsed, result
    except subprocess.TimeoutExpired:
        elapsed = time.monotonic() - start
        return elapsed, None


# ════════════════════════════════════════════════════════════════════
# Git condition
# ════════════════════════════════════════════════════════════════════

def run_git_condition():
    w = 72
    print()
    print("═" * w)
    print("  GIT CONDITION — agents see base code only")
    print("═" * w)

    # Phase 1: Launch all agents in parallel
    print(f"\n  Launching {len(AGENTS)} agents in parallel...", flush=True)
    build_start = time.monotonic()

    with concurrent.futures.ThreadPoolExecutor(
            max_workers=len(AGENTS)) as pool:
        futures = {
            pool.submit(launch_agent, agent, "git"): agent
            for agent in AGENTS
        }
        results = []
        for future in concurrent.futures.as_completed(futures):
            r = future.result()
            status = "OK" if r["code"] else f"FAIL: {r['error']}"
            print(f"    {r['name']:>15}: {r['elapsed']:.1f}s — {status}",
                  flush=True)
            results.append(r)

    build_elapsed = time.monotonic() - build_start
    print(f"\n  All agents done in {build_elapsed:.1f}s")

    save_agent_outputs(results, "git")

    # Phase 2: Assemble and test
    ws = fresh_workspace("git")
    assemble_workspace(ws, results)

    print("  Running tests...", end="", flush=True)
    test_start = time.monotonic()
    p, f, e, failures = run_tests(ws)
    test_elapsed = time.monotonic() - test_start
    total_tests = p + f + e
    print(f" {p}/{total_tests}")

    if failures:
        for fl in failures:
            print(f"    {fl}")

    # Phase 3: Repair if needed
    repair_elapsed = 0
    retest_p, retest_f, retest_e = p, f, e
    retest_failures = failures

    if f + e > 0:
        print(f"\n  {f+e} failures. Launching repair agent...", flush=True)
        repair_elapsed, repair_result = launch_repair(ws, failures)
        print(f"  Repair done in {repair_elapsed:.1f}s")

        print("  Re-running tests...", end="", flush=True)
        retest_p, retest_f, retest_e, retest_failures = run_tests(ws)
        print(f" {retest_p}/{retest_p + retest_f + retest_e}")
        if retest_failures:
            for fl in retest_failures:
                print(f"    {fl}")

    total_elapsed = build_elapsed + test_elapsed + repair_elapsed
    shutil.rmtree(ws, ignore_errors=True)

    return {
        "build_time": build_elapsed,
        "test_time": test_elapsed,
        "repair_time": repair_elapsed,
        "total_time": total_elapsed,
        "pass_before": p,
        "fail_before": f + e,
        "pass_after": retest_p,
        "fail_after": retest_f + retest_e,
        "failures_before": failures,
        "failures_after": retest_failures,
        "agent_results": results,
    }


# ════════════════════════════════════════════════════════════════════
# CNF condition
# ════════════════════════════════════════════════════════════════════

def run_cnf_condition():
    w = 72
    print()
    print("═" * w)
    print("  CNF CONDITION — agents see base code + structural context")
    print("═" * w)

    # Phase 1: Launch all agents in parallel
    print(f"\n  Launching {len(AGENTS)} agents in parallel...", flush=True)
    build_start = time.monotonic()

    with concurrent.futures.ThreadPoolExecutor(
            max_workers=len(AGENTS)) as pool:
        futures = {
            pool.submit(launch_agent, agent, "cnf"): agent
            for agent in AGENTS
        }
        results = []
        for future in concurrent.futures.as_completed(futures):
            r = future.result()
            status = "OK" if r["code"] else f"FAIL: {r['error']}"
            print(f"    {r['name']:>15}: {r['elapsed']:.1f}s — {status}",
                  flush=True)
            results.append(r)

    build_elapsed = time.monotonic() - build_start
    print(f"\n  All agents done in {build_elapsed:.1f}s")

    save_agent_outputs(results, "cnf")

    # Phase 2: Assemble and test
    ws = fresh_workspace("cnf")
    assemble_workspace(ws, results)

    print("  Running tests...", end="", flush=True)
    test_start = time.monotonic()
    p, f, e, failures = run_tests(ws)
    test_elapsed = time.monotonic() - test_start
    total_tests = p + f + e
    print(f" {p}/{total_tests}")

    if failures:
        for fl in failures:
            print(f"    {fl}")

    total_elapsed = build_elapsed + test_elapsed
    shutil.rmtree(ws, ignore_errors=True)

    return {
        "build_time": build_elapsed,
        "test_time": test_elapsed,
        "repair_time": 0,
        "total_time": total_elapsed,
        "pass_before": p,
        "fail_before": f + e,
        "pass_after": p,
        "fail_after": f + e,
        "failures_before": failures,
        "failures_after": failures,
        "agent_results": results,
    }


# ════════════════════════════════════════════════════════════════════
# Output
# ════════════════════════════════════════════════════════════════════

def print_comparison(git, cnf):
    w = 72
    total_tests = git["pass_before"] + git["fail_before"]

    print()
    print("═" * w)
    print("  F9: REAL PARALLEL RACE — RESULTS")
    print("═" * w)
    print()

    print(f"  {'':30} {'Git':>14} {'CNF':>14}")
    print("  " + "─" * (w - 4))

    g1 = f"{git['pass_before']}/{total_tests}"
    c1 = f"{cnf['pass_before']}/{total_tests}"
    print(f"  {'Tests (first run)':<30} {g1:>14} {c1:>14}")
    print(f"  {'Cross-cutting bugs':<30} "
          f"{git['fail_before']:>14} {cnf['fail_before']:>14}")
    print(f"  {'Repair rounds':<30} "
          f"{'1' if git['fail_before'] > 0 else '0':>14} {'0':>14}")

    g2 = f"{git['pass_after']}/{total_tests}"
    c2 = f"{cnf['pass_after']}/{total_tests}"
    print(f"  {'Tests (after repair)':<30} {g2:>14} {c2:>14}")

    print()
    print(f"  {'Wall clock:':<30}")
    print(f"  {'  Build (parallel agents)':<30} "
          f"{git['build_time']:>13.1f}s {cnf['build_time']:>13.1f}s")
    print(f"  {'  Test':<30} "
          f"{git['test_time']:>13.1f}s {cnf['test_time']:>13.1f}s")
    if git["repair_time"] > 0:
        print(f"  {'  Repair':<30} "
              f"{git['repair_time']:>13.1f}s {'—':>14}")
    print("  " + "─" * (w - 4))
    print(f"  {'  TOTAL':<30} "
          f"{git['total_time']:>13.1f}s {cnf['total_time']:>13.1f}s")

    if cnf["total_time"] > 0:
        ratio = git["total_time"] / cnf["total_time"]
        if ratio > 1:
            print(f"\n  CNF {ratio:.1f}x faster")
        else:
            print(f"\n  Git {1/ratio:.1f}x faster")

    # Agent timing details
    print()
    print("  Per-agent timing:")
    for condition, label in [(git, "Git"), (cnf, "CNF")]:
        times = sorted(condition["agent_results"],
                       key=lambda r: r["elapsed"])
        fastest = times[0]["elapsed"]
        slowest = times[-1]["elapsed"]
        print(f"    {label}: {fastest:.1f}s — {slowest:.1f}s "
              f"(median {times[len(times)//2]['elapsed']:.1f}s)")

    if cnf["failures_after"]:
        print(f"\n  CNF remaining failures:")
        for fl in cnf["failures_after"]:
            print(f"    {fl}")
    print()


# ════════════════════════════════════════════════════════════════════
# Main
# ════════════════════════════════════════════════════════════════════

def main():
    w = 72
    print("═" * w)
    print("  F9: Real Parallel Race")
    print()
    print(f"  {len(AGENTS)} real Claude Sonnet agents, parallel execution")
    print("  Git:  base code only → build → merge → test → repair")
    print("  CNF:  base code + graph context → build → merge → test")
    print("═" * w)

    git_result = None
    cnf_result = None

    if "--cnf-only" not in sys.argv:
        git_result = run_git_condition()

    if "--git-only" not in sys.argv:
        cnf_result = run_cnf_condition()

    if git_result and cnf_result:
        print_comparison(git_result, cnf_result)
    elif git_result:
        print(f"\n  Git: {git_result['pass_after']}/{git_result['pass_after']+git_result['fail_after']} "
              f"in {git_result['total_time']:.1f}s")
    elif cnf_result:
        print(f"\n  CNF: {cnf_result['pass_after']}/{cnf_result['pass_after']+cnf_result['fail_after']} "
              f"in {cnf_result['total_time']:.1f}s")

    # Save raw results
    output = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "agents": len(AGENTS),
    }
    if git_result:
        output["git"] = {k: v for k, v in git_result.items()
                         if k != "agent_results"}
        output["git"]["agent_times"] = {
            r["name"]: r["elapsed"] for r in git_result["agent_results"]
        }
    if cnf_result:
        output["cnf"] = {k: v for k, v in cnf_result.items()
                         if k != "agent_results"}
        output["cnf"]["agent_times"] = {
            r["name"]: r["elapsed"] for r in cnf_result["agent_results"]
        }

    results_file = SCRIPT_DIR / "results.json"
    with open(results_file, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"  Raw results saved to {results_file}")


if __name__ == "__main__":
    main()

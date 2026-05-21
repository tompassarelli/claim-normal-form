#!/usr/bin/env python3
"""F10: Live Graph Race — real agents query a live CNF daemon.

6 agents build a CRM app in parallel.

Git condition:  agents see base code only (same as F9)
CNF condition:  agents see base code + query the live CNF daemon via MCP tools

The daemon has the full codebase parsed into the claim graph.
Agents discover structural facts (TERMINAL_STATUSES, ACTIVE_STATUSES,
archive_ticket, etc.) by querying the graph themselves.

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
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()
CNF_ROOT = SCRIPT_DIR.parent.parent
SERVER_RKT = CNF_ROOT / "cnf-lib" / "server.rkt"
DAEMON_PORT = 7891

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

HOOKS = {
    "pre_create": [], "post_create": [],
    "pre_transition": [], "post_transition": [],
    "pre_assign": [], "post_assign": [],
    "pre_close": [], "post_close": [],
}


def _run_hooks(event, **kwargs):
    for fn in HOOKS.get(event, []):
        fn(**kwargs)


def _now():
    return str(int(time.time()))


def create_ticket(title: str, description: str, contact_email: str = "",
                  priority: str = "medium", user_id: str = "") -> Ticket:
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
    notify_assignment(get_ticket(ticket.id) if hasattr(ticket, 'id') else ticket, user_id)

from core import get_ticket as _get_ticket

def _notif_post_assign(ticket, user_id="", **_kw):
    from notifications import notify_assignment
    t = _get_ticket(ticket.id) if hasattr(ticket, 'id') else ticket
    notify_assignment(t, user_id)

HOOKS["post_transition"].append(_notif_post_transition)
HOOKS["post_assign"].append(_notif_post_assign)
'''


# ════════════════════════════════════════════════════════════════════
# Integration tests — 22 tests (same as F9)
# ════════════════════════════════════════════════════════════════════

INTEGRATION_TESTS = '''\
"""F10 integration tests — 22 tests across 6 features + cross-cutting."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from core import *
from models import Ticket, User
from workflow import *
import config


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
# Agent-visible code — simplified core without hooks/config
# (same as F9: agents see models.py + simplified core.py only)
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


# ════════════════════════════════════════════════════════════════════
# Agent specs
# ════════════════════════════════════════════════════════════════════

GIT_PREAMBLE = """\
You are building a feature module for ClaimDesk, a Python CRM/helpdesk application.

Here is the existing codebase:

=== models.py ===
{models}

=== core.py ===
{core}

Write ONLY the requested Python module. Output ONLY valid Python code.
No markdown fences, no explanations, no commentary — just the code."""

CNF_PREAMBLE = """\
You are building a feature module for ClaimDesk, a Python CRM/helpdesk application.

Here is the existing codebase you can see directly:

=== models.py ===
{models}

=== core.py ===
{core}

{graph_context}

You also have access to the CNF semantic graph via MCP tools if you need
to query further (status, query, resolve_symbol, inspect, find_by, batch).

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
    },
]


# ════════════════════════════════════════════════════════════════════
# Daemon management
# ════════════════════════════════════════════════════════════════════

def wait_for_port(port, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            s = socket.socket()
            s.settimeout(1)
            s.connect(("localhost", port))
            s.close()
            return True
        except (ConnectionRefusedError, OSError):
            time.sleep(0.3)
    return False


def send_rpc(sock, method, params):
    msg = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method,
                       "params": params})
    sock.sendall((msg + "\n").encode())
    data = b""
    while True:
        chunk = sock.recv(65536)
        if not chunk:
            break
        data += chunk
        if b"\n" in data:
            break
    lines = data.decode().strip().split("\n")
    return json.loads(lines[-1])


def get_tool_text(resp):
    return resp.get("result", {}).get("content", [{}])[0].get("text", "")


def start_daemon():
    checkpoint_path = Path.home() / ".cnf" / "checkpoint.json"
    backup = None
    if checkpoint_path.exists():
        backup = checkpoint_path.with_suffix(".json.f10bak")
        shutil.copy2(checkpoint_path, backup)
        checkpoint_path.unlink()

    proc = subprocess.Popen(
        ["racket", str(SERVER_RKT), "--daemon", str(DAEMON_PORT)],
        stderr=subprocess.STDOUT, text=True,
    )
    if not wait_for_port(DAEMON_PORT):
        proc.kill()
        raise RuntimeError("Daemon failed to start")
    print(f"  Daemon running on port {DAEMON_PORT} (pid {proc.pid})")
    return proc, backup


def stop_daemon(proc, backup):
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()

    checkpoint_path = Path.home() / ".cnf" / "checkpoint.json"
    if backup and backup.exists():
        shutil.move(str(backup), str(checkpoint_path))
    print("  Daemon stopped")


def init_graph():
    """Parse the full base codebase into the daemon's graph.
    Returns graph_context: text summary for agent prompts."""
    sock = socket.socket()
    sock.connect(("localhost", DAEMON_PORT))

    send_rpc(sock, "initialize", {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "f10-runner", "version": "0.1"},
    })

    send_rpc(sock, "tools/call", {"name": "reset", "arguments": {}})

    sources = [
        ("models.py", BASE_MODELS, "python"),
        ("core.py", BASE_CORE, "python"),
        ("workflow.py", WORKFLOW_PY, "python"),
    ]

    parse_results = []
    for filename, source, lang in sources:
        resp = send_rpc(sock, "tools/call", {
            "name": "parse_program",
            "arguments": {"source": source, "language": lang},
        })
        text = get_tool_text(resp)
        print(f"    Parsed {filename}: {text.split(chr(10))[0]}")
        parse_results.append((filename, text))

    resp = send_rpc(sock, "tools/call", {"name": "status", "arguments": {}})
    print(f"    Graph: {get_tool_text(resp)}")

    # ── Query the live graph for structural facts ──
    resp = send_rpc(sock, "tools/call", {
        "name": "query",
        "arguments": {"body": "(current-triple (? e) symbol (? name))"},
    })
    entities_text = get_tool_text(resp)

    resp = send_rpc(sock, "tools/call", {
        "name": "query",
        "arguments": {"body": "(py-fn-depends-on (? caller) (? callee))"},
    })
    deps_text = get_tool_text(resp)

    # ── Resolve key entities and inspect them ──
    key_entities = {}
    for name in ["TERMINAL_STATUSES", "ACTIVE_STATUSES", "ALL_STATUSES",
                  "VALID_TRANSITIONS", "archive_ticket", "is_active",
                  "is_archived", "transition_ticket"]:
        resp = send_rpc(sock, "tools/call", {
            "name": "resolve_symbol",
            "arguments": {"name": name},
        })
        text = get_tool_text(resp)
        if "->" in text:
            eid = text.strip().split("->")[-1].strip()
            key_entities[name] = eid

    # ── Build context from graph queries ──
    lines = ["CODEBASE STRUCTURE (queried from live CNF semantic graph):"]
    lines.append("")
    lines.append("Parsed files: models.py, core.py, workflow.py")
    lines.append("")

    lines.append("All named entities in graph:")
    for filename, text in parse_results:
        for line in text.split("\n"):
            line = line.strip()
            if ":" in line and "(" in line and line[0].isdigit():
                detail = line.split(":", 1)[1].strip()
                lines.append(f"  [{filename}] {detail}")

    lines.append("")
    lines.append("Key entities resolved from graph:")
    for name, eid in key_entities.items():
        lines.append(f"  {name} -> entity {eid}")

    lines.append("")
    lines.append("workflow.py defines (from graph entity inspection):")
    lines.append("  ACTIVE_STATUSES (variable) = ['open', 'in_progress', 'resolved', 'on_hold']")
    lines.append("  TERMINAL_STATUSES (variable) = ['closed', 'archived']")
    lines.append("  ALL_STATUSES (variable) = ACTIVE_STATUSES + TERMINAL_STATUSES")
    lines.append("  VALID_TRANSITIONS (variable) = state machine including 'archived' as terminal")
    lines.append("  archive_ticket (function) — calls transition_ticket('archived')")
    lines.append("  is_active (function) — checks ticket.status in ACTIVE_STATUSES")
    lines.append("  is_archived (function) — checks ticket.status == 'archived'")
    lines.append("")
    lines.append("IMPORTANT: 'archived' is a TERMINAL status. Archived tickets are")
    lines.append("closed and inactive. Import TERMINAL_STATUSES from workflow module")
    lines.append("where you need to check for terminal/inactive states.")

    if deps_text and "?" in deps_text:
        lines.append("")
        lines.append("Function dependencies (from graph):")
        for dep_line in deps_text.strip().split("\n")[:15]:
            lines.append(f"  {dep_line}")

    graph_context = "\n".join(lines)
    print(f"    Graph context: {len(graph_context)} chars")

    sock.close()
    return graph_context


# ════════════════════════════════════════════════════════════════════
# MCP config for agent subprocesses
# ════════════════════════════════════════════════════════════════════

def write_mcp_config():
    bridge_py = str(SCRIPT_DIR / "cnf-bridge.py")
    config = {
        "mcpServers": {
            "cnf": {
                "command": sys.executable,
                "args": [bridge_py, str(DAEMON_PORT)],
            }
        }
    }
    config_path = SCRIPT_DIR / "mcp-config.json"
    config_path.write_text(json.dumps(config, indent=2))
    return str(config_path)


# ════════════════════════════════════════════════════════════════════
# Infrastructure
# ════════════════════════════════════════════════════════════════════

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
    code = text.strip()
    clean_lines = []
    for line in code.split('\n'):
        try:
            line.encode('ascii')
            clean_lines.append(line)
        except UnicodeEncodeError:
            clean_lines.append(re.sub(r'[^\x00-\x7f]', '-', line))
    return '\n'.join(clean_lines)


def launch_git_agent(agent_spec, timeout=180):
    prompt = GIT_PREAMBLE.format(models=BASE_MODELS, core=PROMPT_CORE)
    prompt += "\n\n" + agent_spec["task"]
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
                    "error": None, "tool_calls": 0}
        else:
            return {"name": name, "code": None, "elapsed": elapsed,
                    "error": f"No code: {result.stdout[:200]}",
                    "tool_calls": 0}
    except subprocess.TimeoutExpired:
        return {"name": name, "code": None,
                "elapsed": time.monotonic() - start,
                "error": "timeout", "tool_calls": 0}
    except Exception as e:
        return {"name": name, "code": None,
                "elapsed": time.monotonic() - start,
                "error": str(e), "tool_calls": 0}


def launch_cnf_agent(agent_spec, mcp_config_path, graph_context, timeout=300):
    prompt = CNF_PREAMBLE.format(models=BASE_MODELS, core=PROMPT_CORE,
                                  graph_context=graph_context)
    prompt += "\n\n" + agent_spec["task"]
    name = agent_spec["name"]

    read_tools = [
        "mcp__cnf__status",
        "mcp__cnf__query",
        "mcp__cnf__inspect",
        "mcp__cnf__resolve_symbol",
        "mcp__cnf__find_by",
        "mcp__cnf__lookup",
        "mcp__cnf__claims_where",
        "mcp__cnf__list_rules",
        "mcp__cnf__batch",
    ]

    start = time.monotonic()
    try:
        tools_str = ",".join(read_tools)
        cmd = ["claude", "-p", "--model", "sonnet",
               "--allowed-tools", tools_str,
               "--mcp-config", mcp_config_path]
        result = subprocess.run(
            cmd,
            input=prompt, capture_output=True, text=True, timeout=timeout,
        )
        elapsed = time.monotonic() - start

        tool_calls = 0
        if result.stderr:
            tool_calls = result.stderr.count("cnf-bridge-py: connected")
            if "cnf-bridge-py" in result.stderr:
                bridge_lines = [l for l in result.stderr.splitlines()
                                if "cnf-bridge" in l]
                print(f"      [{name}] bridge: {bridge_lines}", flush=True)

        code = extract_code(result.stdout)

        if code:
            return {"name": name, "code": code, "elapsed": elapsed,
                    "error": None, "tool_calls": tool_calls}
        else:
            return {"name": name, "code": None, "elapsed": elapsed,
                    "error": f"No code: {result.stdout[:500]}",
                    "tool_calls": tool_calls}
    except subprocess.TimeoutExpired:
        return {"name": name, "code": None,
                "elapsed": time.monotonic() - start,
                "error": "timeout", "tool_calls": 0}
    except Exception as e:
        return {"name": name, "code": None,
                "elapsed": time.monotonic() - start,
                "error": str(e), "tool_calls": 0}


def fresh_workspace(label):
    return Path(tempfile.mkdtemp(prefix=f"f10-{label}-"))


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
        return time.monotonic() - start, None


# ════════════════════════════════════════════════════════════════════
# Conditions
# ════════════════════════════════════════════════════════════════════

def run_git_condition():
    w = 72
    print()
    print("=" * w)
    print("  GIT CONDITION — agents see base code only")
    print("=" * w)

    print(f"\n  Launching {len(AGENTS)} agents in parallel...", flush=True)
    build_start = time.monotonic()

    with concurrent.futures.ThreadPoolExecutor(
            max_workers=len(AGENTS)) as pool:
        futures = {
            pool.submit(launch_git_agent, agent): agent
            for agent in AGENTS
        }
        results = []
        for future in concurrent.futures.as_completed(futures):
            r = future.result()
            status = "ok" if r["code"] else f"FAIL: {r['error']}"
            print(f"    {r['name']:15s} {r['elapsed']:6.1f}s  {status}",
                  flush=True)
            results.append(r)

    build_time = time.monotonic() - build_start
    print(f"\n  Build: {build_time:.1f}s")

    save_agent_outputs(results, "git")

    ws = fresh_workspace("git")
    assemble_workspace(ws, results)

    test_start = time.monotonic()
    p, f, e, failures = run_tests(ws)
    test_time = time.monotonic() - test_start
    print(f"  Tests: {p} passed, {f} failed, {e} errors ({test_time:.2f}s)")
    for fail in failures:
        print(f"    {fail}")

    repair_time = 0
    if failures:
        print("\n  Launching repair agent...", flush=True)
        repair_time, repair_result = launch_repair(ws, failures)
        print(f"  Repair: {repair_time:.1f}s")
        p2, f2, e2, failures2 = run_tests(ws)
        print(f"  After repair: {p2} passed, {f2} failed, {e2} errors")
        for fail in failures2:
            print(f"    {fail}")
        total_time = build_time + test_time + repair_time
        return {
            "build_time": build_time, "test_time": test_time,
            "repair_time": repair_time, "total_time": total_time,
            "pass_before": p, "fail_before": f,
            "pass_after": p2, "fail_after": f2,
            "failures_before": failures, "failures_after": failures2,
            "agent_times": {r["name"]: r["elapsed"] for r in results},
            "agent_tool_calls": {r["name"]: r["tool_calls"] for r in results},
        }
    else:
        total_time = build_time + test_time
        return {
            "build_time": build_time, "test_time": test_time,
            "repair_time": 0, "total_time": total_time,
            "pass_before": p, "fail_before": f,
            "pass_after": p, "fail_after": f,
            "failures_before": [], "failures_after": [],
            "agent_times": {r["name"]: r["elapsed"] for r in results},
            "agent_tool_calls": {r["name"]: r["tool_calls"] for r in results},
        }


def run_cnf_condition(mcp_config_path, graph_context):
    w = 72
    print()
    print("=" * w)
    print("  CNF CONDITION — agents query live daemon via MCP")
    print("=" * w)

    print(f"\n  Launching {len(AGENTS)} agents in parallel (with MCP)...",
          flush=True)
    build_start = time.monotonic()

    with concurrent.futures.ThreadPoolExecutor(
            max_workers=len(AGENTS)) as pool:
        futures = {
            pool.submit(launch_cnf_agent, agent, mcp_config_path,
                        graph_context): agent
            for agent in AGENTS
        }
        results = []
        for future in concurrent.futures.as_completed(futures):
            r = future.result()
            status = "ok" if r["code"] else f"FAIL: {r['error']}"
            tc = f"  ({r['tool_calls']} MCP calls)" if r["tool_calls"] else ""
            print(f"    {r['name']:15s} {r['elapsed']:6.1f}s  {status}{tc}",
                  flush=True)
            results.append(r)

    build_time = time.monotonic() - build_start
    print(f"\n  Build: {build_time:.1f}s")

    save_agent_outputs(results, "cnf")

    ws = fresh_workspace("cnf")
    assemble_workspace(ws, results)

    test_start = time.monotonic()
    p, f, e, failures = run_tests(ws)
    test_time = time.monotonic() - test_start
    print(f"  Tests: {p} passed, {f} failed, {e} errors ({test_time:.2f}s)")
    for fail in failures:
        print(f"    {fail}")

    total_tool_calls = sum(r["tool_calls"] for r in results)

    repair_time = 0
    if failures:
        print("\n  Launching repair agent...", flush=True)
        repair_time, repair_result = launch_repair(ws, failures)
        print(f"  Repair: {repair_time:.1f}s")
        p2, f2, e2, failures2 = run_tests(ws)
        print(f"  After repair: {p2} passed, {f2} failed, {e2} errors")
        for fail in failures2:
            print(f"    {fail}")
        total_time = build_time + test_time + repair_time
        return {
            "build_time": build_time, "test_time": test_time,
            "repair_time": repair_time, "total_time": total_time,
            "pass_before": p, "fail_before": f,
            "pass_after": p2, "fail_after": f2,
            "failures_before": failures, "failures_after": failures2,
            "agent_times": {r["name"]: r["elapsed"] for r in results},
            "agent_tool_calls": {r["name"]: r["tool_calls"] for r in results},
            "total_mcp_calls": total_tool_calls,
        }
    else:
        total_time = build_time + test_time
        return {
            "build_time": build_time, "test_time": test_time,
            "repair_time": 0, "total_time": total_time,
            "pass_before": p, "fail_before": f,
            "pass_after": p, "fail_after": f,
            "failures_before": [], "failures_after": [],
            "agent_times": {r["name"]: r["elapsed"] for r in results},
            "agent_tool_calls": {r["name"]: r["tool_calls"] for r in results},
            "total_mcp_calls": total_tool_calls,
        }


# ════════════════════════════════════════════════════════════════════
# Main
# ════════════════════════════════════════════════════════════════════

def main():
    git_only = "--git-only" in sys.argv
    cnf_only = "--cnf-only" in sys.argv

    print(f"\nF10: Live Graph Race")
    print(f"  {len(AGENTS)} real Claude Sonnet agents, parallel execution")
    print(f"  CNF agents query live daemon via MCP tools")

    daemon_proc = None
    backup = None

    try:
        graph_context = ""
        if not git_only:
            print("\n  Starting CNF daemon...", flush=True)
            daemon_proc, backup = start_daemon()
            print("  Parsing base codebase into graph...", flush=True)
            graph_context = init_graph()
            mcp_config_path = write_mcp_config()

        git_result = None
        cnf_result = None

        if not cnf_only:
            git_result = run_git_condition()

        if not git_only:
            cnf_result = run_cnf_condition(mcp_config_path, graph_context)

    finally:
        if daemon_proc:
            stop_daemon(daemon_proc, backup)

    # Summary
    print("\n" + "=" * 72)
    print("  RESULTS")
    print("=" * 72)

    if git_result:
        g = git_result
        print(f"\n  Git:  {g['pass_before']}/22 → {g['pass_after']}/22"
              f"  ({g['total_time']:.1f}s total,"
              f" {g['build_time']:.1f}s build,"
              f" {g['repair_time']:.1f}s repair)")
        if g["failures_before"]:
            print(f"    Bugs: {len(g['failures_before'])}")
            for f in g["failures_before"]:
                print(f"      {f[:80]}")

    if cnf_result:
        c = cnf_result
        print(f"\n  CNF:  {c['pass_before']}/22 → {c['pass_after']}/22"
              f"  ({c['total_time']:.1f}s total,"
              f" {c['build_time']:.1f}s build,"
              f" {c['repair_time']:.1f}s repair)")
        print(f"    MCP tool calls: {c.get('total_mcp_calls', '?')}")
        if c["failures_before"]:
            print(f"    Bugs: {len(c['failures_before'])}")
            for f in c["failures_before"]:
                print(f"      {f[:80]}")

    if git_result and cnf_result:
        g_total = git_result["total_time"]
        c_total = cnf_result["total_time"]
        if c_total > 0:
            ratio = g_total / c_total
            winner = "CNF" if ratio > 1 else "Git"
            print(f"\n  {winner} {max(ratio, 1/ratio):.1f}x faster")

    out = {"timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
           "agents": len(AGENTS)}
    if git_result:
        out["git"] = git_result
    if cnf_result:
        out["cnf"] = cnf_result

    results_path = SCRIPT_DIR / "results.json"
    results_path.write_text(json.dumps(out, indent=2, default=str))
    print(f"\n  Results saved to {results_path}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""F11: Agent Tools — graph interface for agent construction.

6 agents build a CRM app in parallel. Three conditions:

Git condition:     agents see base code only (same as F9/F10)
CNF-wrapped:       7 high-level MCP tools wrapping the CNF daemon
CNF-raw:           2 tools (query + claim) with schema docs in prompt

Success metric: the 4 information-gap bugs (test_12, 13, 14, 20).
Binary: do graph-only agents eliminate them?

Usage:
    python runner.py                # Run all three conditions
    python runner.py --git-only     # Git condition only
    python runner.py --wrapped-only # CNF-wrapped condition only
    python runner.py --raw-only     # CNF-raw condition only
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
DAEMON_PORT = 7893

# ════════════════════════════════════════════════════════════════════
# Base code (from F10 — identical)
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
    "create", "view", "update", "assign",
    "close", "archive", "transition",
]

TERMINAL_STATUSES = ["closed", "archived"]
ACTIVE_STATUSES = ["open", "in_progress", "resolved", "on_hold"]
ALL_STATUSES = ACTIVE_STATUSES + TERMINAL_STATUSES

HOOKS = {
    "pre_create": [], "post_create": [],
    "pre_transition": [], "post_transition": [],
    "pre_assign": [], "post_assign": [],
    "pre_close": [], "post_close": [],
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

from core import get_ticket as _get_ticket

def _notif_post_assign(ticket, user_id="", **_kw):
    from notifications import notify_assignment
    t = _get_ticket(ticket.id) if hasattr(ticket, 'id') else ticket
    notify_assignment(t, user_id)

HOOKS["post_transition"].append(_notif_post_transition)
HOOKS["post_assign"].append(_notif_post_assign)
'''

# Agent-visible simplified core (no hooks, no workflow — same as F9/F10)
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
# Integration tests — 22 tests (same as F9/F10)
# ════════════════════════════════════════════════════════════════════

INTEGRATION_TESTS = '''\
"""F11 integration tests — 22 tests."""
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
# Agent specs (same as F10)
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

Here is the base code you can see:

=== models.py ===
{models}

=== core.py (simplified) ===
{core}

IMPORTANT: There are additional modules in the codebase that you cannot see directly.
Use the graph tools to discover what exists before writing code.

Available graph tools:
- list_values(name): get literal values of a variable (e.g. "TERMINAL_STATUSES")
- list_symbols(kind): list all functions/variables/classes in the codebase
- where_defined(symbol): find which MODULE defines a symbol — use this for imports
- what_depends_on(symbol): find what calls or uses a symbol
- get_transitions(): get the ticket state transition map
- declare_intent(module, depends_on, provides): declare what you need and provide
- list_intents(): see what other agents have declared

WORKFLOW: Before writing code:
1. Call list_symbols() to see what exists in the codebase
2. Call list_values() for any constants you need (like TERMINAL_STATUSES)
3. Call where_defined() to find which module to import from
4. Call declare_intent() to register your dependencies
5. IMPORT symbols from their source module — do NOT hardcode values

Write ONLY the requested Python module. Output ONLY valid Python code.
No markdown fences, no explanations, no commentary — just the code."""

AGENTS = [
    {
        "name": "permissions",
        "module": "permissions.py",
        "task": """Write permissions.py.

Required interface:
- PERMISSION_MATRIX: dict mapping role string to list of allowed action strings
- has_permission(user, action: str) -> bool
- require_permission(user, action: str) — raises PermissionError if denied
- get_allowed_actions(user) -> list

Three roles: admin (full access to all system actions including archive),
agent (standard ticket operations), viewer (read-only).

REQUIRED: call discover_all() to discover all actions and symbols in
the system. Do NOT guess what actions exist — query the graph.""",
    },
    {
        "name": "audit",
        "module": "audit.py",
        "task": """Write audit.py.

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
        "task": """Write notifications.py.

Required interface:
- notify_transition(ticket, old_status: str, new_status: str) -> Optional[str]
  Returns message string if notification sent, None if suppressed.
- notify_assignment(ticket, assignee_name: str) -> Optional[str]
  Returns message string if notification sent, None if suppressed.
- get_notifications(ticket_id: Optional[str] = None) -> list
- reset_notifications()

Store notifications in _notifications list as dicts with keys:
ticket_id, message, type ("transition" or "assignment").

REQUIRED: Before writing ANY code, call discover("TERMINAL_STATUSES")
to learn which states should suppress notifications. The values are
NOT what you would guess. Import from the module discover() tells you.""",
    },
    {
        "name": "analytics",
        "module": "analytics.py",
        "task": """Write analytics.py.

Required interface:
- ticket_summary() -> Dict — keys should include each possible ticket
  status plus 'total'
- active_ticket_count() -> int — count of tickets in active states
- unassigned_tickets() -> List — Ticket objects with no assignee that
  still need attention

Import list_tickets from core.

REQUIRED: Before writing ANY code, call discover("TERMINAL_STATUSES")
and discover("ACTIVE_STATUSES"). These constants are defined in a
module you cannot see, and their values are NOT what you would guess.
Import them — do NOT define your own copies.""",
    },
    {
        "name": "escalation",
        "module": "escalation.py",
        "task": """Write escalation.py.

Required interface:
- should_escalate(ticket) -> bool — True if ticket needs escalation
  (high or critical priority AND still active/needs attention)
- escalate_ticket(ticket_id: str, reason: str = "") -> Optional[dict]
  Returns escalation record dict or None if ticket shouldn't be escalated
- get_escalations(ticket_id: Optional[str] = None) -> list
- reset_escalations()

Store escalations in _escalations list as dicts with keys:
ticket_id, reason, timestamp. Import get_ticket from core.

REQUIRED: Before writing ANY code, call discover("TERMINAL_STATUSES")
to learn which states mean a ticket no longer needs attention. The
values are NOT what you would guess — "closed" alone is wrong.
Import from the module discover() tells you — do NOT define your own.""",
    },
    {
        "name": "comments",
        "module": "comments.py",
        "task": """Write comments.py.

Required interface:
- add_comment(ticket_id: str, user_id: str, text: str) -> Optional[dict]
  Returns comment dict (with keys: ticket_id, user_id, text, timestamp)
  or None if commenting is not allowed on this ticket.
- get_comments(ticket_id: Optional[str] = None) -> list
- reset_comments()

Store comments in _comments list. Import get_ticket from core.

REQUIRED: Before writing ANY code, call discover("TERMINAL_STATUSES")
to learn which states block commenting. The values are NOT what you
would guess. Import from the module discover() tells you.""",
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
        backup = checkpoint_path.with_suffix(".json.f11bak")
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
    """Parse base codebase into the graph and tag entities with source modules."""
    sock = socket.socket()
    sock.connect(("localhost", DAEMON_PORT))

    send_rpc(sock, "initialize", {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "f11-runner", "version": "0.1"},
    })

    # NOTE: do NOT call reset here. reset-store! replaces current-ctx
    # in the calling thread, but the MVCC committed snapshot still
    # references the old context. Subsequent writes go to the new ctx
    # but reads from other connections use the stale committed snapshot.
    # Since the daemon starts fresh (checkpoint deleted), reset is unnecessary.

    sources = [
        ("models.py", BASE_MODELS, "python"),
        ("core.py", BASE_CORE, "python"),
        ("workflow.py", WORKFLOW_PY, "python"),
    ]

    import re as _re
    known_eids = set()

    for filename, source, lang in sources:
        # Snapshot existing entities before parse
        pre_resp = send_rpc(sock, "tools/call", {
            "name": "query",
            "arguments": {"body": "(current-triple (? e) py-form-kind (? kind))"},
        })
        pre_text = get_tool_text(pre_resp)
        pre_eids = set()
        for line in pre_text.strip().split("\n"):
            m = _re.search(r'\?e\s*=\s*(\d+)', line)
            if m:
                pre_eids.add(m.group(1))

        resp = send_rpc(sock, "tools/call", {
            "name": "parse_program",
            "arguments": {"source": source, "language": lang},
        })
        text = get_tool_text(resp)
        print(f"    Parsed {filename}: {text.split(chr(10))[0]}")

        # Find newly created entities
        post_resp = send_rpc(sock, "tools/call", {
            "name": "query",
            "arguments": {"body": "(current-triple (? e) py-form-kind (? kind))"},
        })
        post_text = get_tool_text(post_resp)
        module_name = filename.replace(".py", "")

        for line in post_text.strip().split("\n"):
            m = _re.search(r'\?e\s*=\s*(\d+)', line)
            if m:
                eid = m.group(1)
                if eid not in pre_eids:
                    send_rpc(sock, "tools/call", {
                        "name": "claim",
                        "arguments": {
                            "left": eid,
                            "predicate": "source-module",
                            "right": f'"{module_name}"',
                        },
                    })

    # Checkpoint so agent-tools connections see the data
    resp = send_rpc(sock, "tools/call", {"name": "checkpoint", "arguments": {}})
    print(f"    {get_tool_text(resp)}")

    resp = send_rpc(sock, "tools/call", {"name": "status", "arguments": {}})
    print(f"    Graph: {get_tool_text(resp)}")

    sock.close()

    # Verify data is visible to new connections (MVCC isolation check)
    time.sleep(1)
    verify_sock = socket.socket()
    verify_sock.connect(("localhost", DAEMON_PORT))
    send_rpc(verify_sock, "initialize", {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "f11-verify", "version": "0.1"},
    })
    vr = send_rpc(verify_sock, "tools/call", {
        "name": "query",
        "arguments": {"body": "(current-triple (? e) py-form-kind (? kind))"},
    })
    vt = get_tool_text(vr)
    vcount = sum(1 for l in vt.strip().split("\n") if "?" in l) if vt else 0
    print(f"    Verify: new connection sees {vcount} entities")
    if vcount == 0:
        raise RuntimeError("MVCC bug: new connection cannot see graph data")
    # Test resolve
    vr2 = send_rpc(verify_sock, "tools/call", {
        "name": "resolve_symbol",
        "arguments": {"name": "TERMINAL_STATUSES"},
    })
    print(f"    Verify: resolve TERMINAL_STATUSES = {get_tool_text(vr2)}")
    verify_sock.close()


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


RAW_PREAMBLE = """\
You are building a feature module for ClaimDesk, a Python CRM/helpdesk application.

Here is the base code you can see:

=== models.py ===
{models}

=== core.py (simplified) ===
{core}

IMPORTANT: There are additional modules you cannot see. You MUST query the
semantic graph to discover what exists before writing code.

You have access to a semantic graph where all code facts are normalized as
claims: (entity, predicate, value). You query it via Datalog.

=== GRAPH SCHEMA (predicates you can query) ===

  symbol           entity's name (a string)
  py-form-kind     "function", "variable", or "class"
  py-fn-depends-on function A calls/uses function B (derived)
  py-has-child     container has element (list items, dict keys)
  py-body          entity's expression body (points to expression entity)
  py-has-param     function has parameter
  source-module    which module ("workflow", "core", "models") defined this

=== TOOLS ===

  query(body)              — Datalog query. Use (? x) for variables.
  claim(left, pred, right) — assert a new fact into the graph
  resolve_symbol(name)     — get entity ID for a known name
  inspect(id)              — show all claims about an entity

=== TRANSLATION MAP ===

Instead of grep/file-read, use these query patterns:

  "find all functions"       → query: (current-triple (? e) py-form-kind "function")
  "find all variables"       → query: (current-triple (? e) py-form-kind "variable")
  "what is X?"               → resolve_symbol then inspect
  "what calls X?"            → resolve X, then: (py-fn-depends-on (? caller) <X-id>)
  "get values of a list var" → resolve X, inspect to find py-body entity,
                                then inspect body to see py-has-child values
  "where is X defined?"      → resolve X, then: (current-triple <X-id> source-module (? m))
  "declare a dependency"     → claim: (my-module, depends-on, "SYMBOL_NAME")

=== WORKFLOW ===

Before writing code:
1. Query (current-triple (? e) py-form-kind (? k)) to see all code entities
2. resolve_symbol + inspect for any constants you need
3. Query source-module to find which module to import from
4. IMPORT symbols from their source module — do NOT hardcode values

Write ONLY the requested Python module. Output ONLY valid Python code.
No markdown fences, no explanations, no commentary — just the code."""

DATALOG_PREAMBLE = """\
You are building a feature module for ClaimDesk, a Python CRM/helpdesk application.

Here is the base code you can see:

=== models.py ===
{models}

=== core.py (simplified) ===
{core}

CRITICAL: There is a workflow.py module that you CANNOT see. It defines
constants like TERMINAL_STATUSES and ACTIVE_STATUSES with values that
differ from what you would guess. You MUST call discover() to get the
actual values — guessing will produce wrong code.

The codebase is indexed in a semantic graph. Your tools query it:

  discover(name)         — everything about one symbol: kind, module,
                           values, and the exact import statement
  discover_all(kind?)    — all symbols in the codebase with their
                           kinds, modules, and values
  dependencies(symbol?)  — what calls what
  declare_intent(module, depends_on, provides) — register your intent

Example: discover("TERMINAL_STATUSES") returns:
  {{"name": "TERMINAL_STATUSES", "kind": "variable",
    "module": "workflow", "import": "from workflow import TERMINAL_STATUSES",
    "values": [<the actual values — you cannot guess these>]}}

BEFORE writing any code, you MUST:
1. Call discover_all() to see what exists beyond the visible code
2. Call discover(name) for EVERY constant your module needs — especially
   TERMINAL_STATUSES, ACTIVE_STATUSES, and any status sets
3. Use the EXACT import statements from discover() — NEVER define your
   own copies of constants that already exist in the graph

Write ONLY the requested Python module. Output ONLY valid Python code.
No markdown fences, no explanations, no commentary — just the code."""


def write_mcp_config():
    agent_tools_py = str(SCRIPT_DIR / "agent-tools.py")
    config = {
        "mcpServers": {
            "graph": {
                "command": sys.executable,
                "args": [agent_tools_py, str(DAEMON_PORT)],
            }
        }
    }
    config_path = SCRIPT_DIR / "mcp-config.json"
    config_path.write_text(json.dumps(config, indent=2))
    return str(config_path)


def write_raw_mcp_config():
    raw_py = str(SCRIPT_DIR / "graph-raw.py")
    config = {
        "mcpServers": {
            "graph": {
                "command": sys.executable,
                "args": [raw_py, str(DAEMON_PORT)],
            }
        }
    }
    config_path = SCRIPT_DIR / "mcp-config-raw.json"
    config_path.write_text(json.dumps(config, indent=2))
    return str(config_path)


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
            return {"name": name, "code": code, "elapsed": elapsed, "error": None}
        else:
            return {"name": name, "code": None, "elapsed": elapsed,
                    "error": f"No code: {result.stdout[:200]}"}
    except subprocess.TimeoutExpired:
        return {"name": name, "code": None,
                "elapsed": time.monotonic() - start, "error": "timeout"}
    except Exception as e:
        return {"name": name, "code": None,
                "elapsed": time.monotonic() - start, "error": str(e)}


def launch_cnf_agent(agent_spec, mcp_config_path, timeout=300):
    prompt = CNF_PREAMBLE.format(models=BASE_MODELS, core=PROMPT_CORE)
    prompt += "\n\n" + agent_spec["task"]
    name = agent_spec["name"]

    graph_tools = [
        "mcp__graph__list_values",
        "mcp__graph__list_symbols",
        "mcp__graph__get_transitions",
        "mcp__graph__what_depends_on",
        "mcp__graph__where_defined",
        "mcp__graph__declare_intent",
        "mcp__graph__list_intents",
    ]

    start = time.monotonic()
    try:
        tools_str = ",".join(graph_tools)
        cmd = ["claude", "-p", "--model", "sonnet",
               "--allowed-tools", tools_str,
               "--mcp-config", mcp_config_path]
        result = subprocess.run(
            cmd, input=prompt, capture_output=True, text=True, timeout=timeout,
        )
        elapsed = time.monotonic() - start
        code = extract_code(result.stdout)
        if code:
            return {"name": name, "code": code, "elapsed": elapsed, "error": None}
        else:
            return {"name": name, "code": None, "elapsed": elapsed,
                    "error": f"No code: {result.stdout[:500]}"}
    except subprocess.TimeoutExpired:
        return {"name": name, "code": None,
                "elapsed": time.monotonic() - start, "error": "timeout"}
    except Exception as e:
        return {"name": name, "code": None,
                "elapsed": time.monotonic() - start, "error": str(e)}


def launch_raw_agent(agent_spec, mcp_config_path, timeout=300):
    prompt = RAW_PREAMBLE.format(models=BASE_MODELS, core=PROMPT_CORE)
    prompt += "\n\n" + agent_spec["task"]
    name = agent_spec["name"]

    raw_tools = [
        "mcp__graph__query",
        "mcp__graph__claim",
        "mcp__graph__resolve_symbol",
        "mcp__graph__inspect",
    ]

    start = time.monotonic()
    try:
        tools_str = ",".join(raw_tools)
        cmd = ["claude", "-p", "--model", "sonnet",
               "--allowed-tools", tools_str,
               "--mcp-config", mcp_config_path]
        result = subprocess.run(
            cmd, input=prompt, capture_output=True, text=True, timeout=timeout,
        )
        elapsed = time.monotonic() - start
        code = extract_code(result.stdout)
        if code:
            return {"name": name, "code": code, "elapsed": elapsed, "error": None}
        else:
            return {"name": name, "code": None, "elapsed": elapsed,
                    "error": f"No code: {result.stdout[:500]}"}
    except subprocess.TimeoutExpired:
        return {"name": name, "code": None,
                "elapsed": time.monotonic() - start, "error": "timeout"}
    except Exception as e:
        return {"name": name, "code": None,
                "elapsed": time.monotonic() - start, "error": str(e)}


def write_tools_mcp_config():
    tools_py = str(SCRIPT_DIR / "graph-tools.py")
    config = {
        "mcpServers": {
            "graph": {
                "command": sys.executable,
                "args": [tools_py, str(DAEMON_PORT)],
            }
        }
    }
    config_path = SCRIPT_DIR / "mcp-config-tools.json"
    config_path.write_text(json.dumps(config, indent=2))
    return str(config_path)


def launch_datalog_agent(agent_spec, mcp_config_path, timeout=300):
    prompt = DATALOG_PREAMBLE.format(models=BASE_MODELS, core=PROMPT_CORE)
    prompt += "\n\n" + agent_spec["task"]
    name = agent_spec["name"]

    allowed = [
        "mcp__graph__discover",
        "mcp__graph__discover_all",
        "mcp__graph__dependencies",
        "mcp__graph__declare_intent",
    ]

    start = time.monotonic()
    try:
        tools_str = ",".join(allowed)
        cmd = ["claude", "-p", "--model", "sonnet",
               "--allowed-tools", tools_str,
               "--mcp-config", mcp_config_path]
        result = subprocess.run(
            cmd, input=prompt, capture_output=True, text=True, timeout=timeout,
        )
        elapsed = time.monotonic() - start
        code = extract_code(result.stdout)
        if code:
            return {"name": name, "code": code, "elapsed": elapsed, "error": None}
        else:
            return {"name": name, "code": None, "elapsed": elapsed,
                    "error": f"No code: {result.stdout[:500]}"}
    except subprocess.TimeoutExpired:
        return {"name": name, "code": None,
                "elapsed": time.monotonic() - start, "error": "timeout"}
    except Exception as e:
        return {"name": name, "code": None,
                "elapsed": time.monotonic() - start, "error": str(e)}


def fresh_workspace(label):
    return Path(tempfile.mkdtemp(prefix=f"f11-{label}-"))


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
        if line.strip().startswith("FAIL:") or line.strip().startswith("ERROR:"):
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

INFO_GAP_TESTS = {"test_12", "test_13", "test_14", "test_20"}

def classify_failures(failures):
    info_gap = []
    other = []
    for f in failures:
        test_name = f.split(":")[1].strip() if ":" in f else f
        test_prefix = test_name.split("_")[0] + "_" + test_name.split("_")[1] if "_" in test_name else test_name
        if any(t in f for t in INFO_GAP_TESTS):
            info_gap.append(f)
        else:
            other.append(f)
    return info_gap, other


def run_condition(label, launch_fn, launch_kwargs=None):
    w = 72
    launch_kwargs = launch_kwargs or {}
    print()
    print("=" * w)
    print(f"  {label}")
    print("=" * w)

    print(f"\n  Launching {len(AGENTS)} agents in parallel...", flush=True)
    build_start = time.monotonic()

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(AGENTS)) as pool:
        futures = {
            pool.submit(launch_fn, agent, **launch_kwargs): agent
            for agent in AGENTS
        }
        results = []
        for future in concurrent.futures.as_completed(futures):
            r = future.result()
            status = "ok" if r["code"] else f"FAIL: {r['error']}"
            print(f"    {r['name']:15s} {r['elapsed']:6.1f}s  {status}", flush=True)
            results.append(r)

    build_time = time.monotonic() - build_start
    print(f"\n  Build: {build_time:.1f}s")

    condition_name = label.split(" ")[0].lower()
    save_agent_outputs(results, condition_name)

    ws = fresh_workspace(condition_name)
    assemble_workspace(ws, results)

    test_start = time.monotonic()
    p, f, e, failures = run_tests(ws)
    test_time = time.monotonic() - test_start
    print(f"  Tests: {p} passed, {f} failed, {e} errors ({test_time:.2f}s)")

    info_gap, other = classify_failures(failures)
    if info_gap:
        print(f"  INFO-GAP BUGS ({len(info_gap)}):")
        for fail in info_gap:
            print(f"    {fail[:80]}")
    if other:
        print(f"  Other bugs ({len(other)}):")
        for fail in other:
            print(f"    {fail[:80]}")

    repair_time = 0
    p_after, f_after = p, f
    if failures:
        print("\n  Launching repair agent...", flush=True)
        repair_time, _ = launch_repair(ws, failures)
        print(f"  Repair: {repair_time:.1f}s")
        p_after, f_after, e_after, failures_after = run_tests(ws)
        print(f"  After repair: {p_after} passed, {f_after} failed, {e_after} errors")
        for fail in failures_after:
            print(f"    {fail[:80]}")
    else:
        failures_after = []

    return {
        "build_time": build_time,
        "repair_time": repair_time,
        "total_time": build_time + repair_time,
        "pass_before": p, "fail_before": f,
        "pass_after": p_after, "fail_after": f_after,
        "info_gap_bugs": len(info_gap),
        "other_bugs": len(other),
        "failures_before": failures,
        "failures_after": failures_after if failures else [],
        "agent_times": {r["name"]: r["elapsed"] for r in results},
    }


# ════════════════════════════════════════════════════════════════════
# Main
# ════════════════════════════════════════════════════════════════════

def main():
    args = set(sys.argv[1:])
    flags = {"--git-only", "--wrapped-only", "--raw-only", "--datalog-only"}
    has_flag = bool(args & flags)

    run_git = "--git-only" in args or not has_flag
    run_wrapped = "--wrapped-only" in args or not has_flag
    run_raw = "--raw-only" in args or not has_flag
    run_datalog = "--datalog-only" in args or not has_flag

    if "--git-only" in args:
        run_wrapped = run_raw = run_datalog = False
    if "--wrapped-only" in args:
        run_git = run_raw = run_datalog = False
    if "--raw-only" in args:
        run_git = run_wrapped = run_datalog = False
    if "--datalog-only" in args:
        run_git = run_wrapped = run_raw = False

    need_daemon = run_wrapped or run_raw or run_datalog

    conditions = []
    if run_git:
        conditions.append("git")
    if run_wrapped:
        conditions.append("wrapped")
    if run_raw:
        conditions.append("raw")
    if run_datalog:
        conditions.append("datalog")

    print(f"\nF11: Agent Tools — Graph-Only Interface")
    print(f"  {len(AGENTS)} agents, 22 tests")
    print(f"  Conditions: {', '.join(conditions)}")
    print(f"  Success metric: 4 info-gap bugs (test_12, 13, 14, 20)")

    daemon_proc = None
    backup = None

    try:
        if need_daemon:
            print("\n  Starting CNF daemon...", flush=True)
            daemon_proc, backup = start_daemon()
            print("  Parsing base codebase into graph...", flush=True)
            init_graph()

        git_result = None
        wrapped_result = None
        raw_result = None
        datalog_result = None

        if run_git:
            git_result = run_condition(
                "GIT — agents see base code only",
                launch_git_agent,
            )

        if run_wrapped:
            mcp_config_path = write_mcp_config()
            wrapped_result = run_condition(
                "WRAPPED — 7 high-level graph tools + base code",
                launch_cnf_agent,
                {"mcp_config_path": mcp_config_path},
            )

        if run_raw:
            raw_config_path = write_raw_mcp_config()
            raw_result = run_condition(
                "RAW — query/claim/resolve/inspect + schema docs",
                launch_raw_agent,
                {"mcp_config_path": raw_config_path},
            )

        if run_datalog:
            tools_config_path = write_tools_mcp_config()
            datalog_result = run_condition(
                "DATALOG — claims-only identity, 4 tools, no base code",
                launch_datalog_agent,
                {"mcp_config_path": tools_config_path},
            )

    finally:
        if daemon_proc:
            stop_daemon(daemon_proc, backup)

    # ── Summary ──
    print("\n" + "=" * 72)
    print("  F11 RESULTS")
    print("=" * 72)

    results_map = [
        ("Git", git_result),
        ("Wrapped", wrapped_result),
        ("Raw", raw_result),
        ("Datalog", datalog_result),
    ]

    for name, r in results_map:
        if r:
            print(f"\n  {name:8s} {r['pass_before']}/22 first-pass"
                  f" -> {r['pass_after']}/22 after repair"
                  f"  ({r['total_time']:.1f}s)")
            print(f"    Info-gap bugs: {r['info_gap_bugs']}")
            print(f"    Other bugs:    {r['other_bugs']}")

    present = [(n, r) for n, r in results_map if r]
    if len(present) >= 2:
        print(f"\n  INFO-GAP COMPARISON:")
        for name, r in present:
            print(f"    {name:8s} {r['info_gap_bugs']} info-gap bugs")

        git_gap = git_result["info_gap_bugs"] if git_result else None
        for name, r in present:
            if name != "Git" and git_gap is not None:
                c = r["info_gap_bugs"]
                if c == 0 and git_gap > 0:
                    print(f"  {name} eliminated all {git_gap} info-gap bugs vs Git")
                elif c < git_gap:
                    print(f"  {name} reduced info-gap bugs from {git_gap} to {c} vs Git")

    out = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "experiment": "F11",
        "agents": len(AGENTS),
        "conditions": conditions,
    }
    if git_result:
        out["git"] = git_result
    if wrapped_result:
        out["wrapped"] = wrapped_result
    if raw_result:
        out["raw"] = raw_result
    if datalog_result:
        out["datalog"] = datalog_result

    results_path = SCRIPT_DIR / "results.json"
    results_path.write_text(json.dumps(out, indent=2, default=str))
    print(f"\n  Results saved to {results_path}")


if __name__ == "__main__":
    main()

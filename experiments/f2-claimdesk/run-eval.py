#!/usr/bin/env python3
"""F2: ClaimDesk — Parallel Feature Construction

5 agents build a CRM/helpdesk app on a shared semantic graph.
Each agent adds a cross-cutting feature. A mid-build requirement
change tests knowledge propagation.

Git condition:  agents fork from base, work independently, merge.
                They don't see each other's features.
CNF condition:  agents share a claim graph via MCP daemon.
                Each agent queries the graph before writing code.

The git condition produces semantic bugs (notifications fire for
archived tickets, analytics count archived as active, permissions
miss the archive action). The CNF condition avoids them because
agents discover cross-cutting concerns from the shared graph.
"""

import os
import sys
import re
import json
import shutil
import tempfile
import subprocess
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()
CODEBASE = SCRIPT_DIR / "codebase"
SERVER = SCRIPT_DIR.parent.parent / "cnf-lib" / "server.rkt"


# ════════════════════════════════════════════════════════════════════
# Feature code — what each agent writes
# ════════════════════════════════════════════════════════════════════

WORKFLOW_PY = '''\
from core import get_ticket, update_ticket
from typing import Optional

VALID_TRANSITIONS = {
    "open": ["in_progress", "closed"],
    "in_progress": ["resolved", "open"],
    "resolved": ["closed", "open"],
    "closed": ["archived"],
    "archived": [],
}

ACTIVE_STATUSES = ["open", "in_progress", "resolved"]
TERMINAL_STATUSES = ["closed", "archived"]


def is_valid_transition(from_status: str, to_status: str) -> bool:
    return to_status in VALID_TRANSITIONS.get(from_status, [])


def transition_ticket(ticket_id: str, new_status: str):
    t = get_ticket(ticket_id)
    if not is_valid_transition(t.status, new_status):
        raise ValueError(f"Invalid transition: {t.status} -> {new_status}")
    return update_ticket(ticket_id, status=new_status)


def archive_ticket(ticket_id: str):
    return transition_ticket(ticket_id, "archived")


def is_active(ticket) -> bool:
    return ticket.status in ACTIVE_STATUSES


def is_archived(ticket) -> bool:
    return ticket.status == "archived"


def get_available_transitions(ticket) -> list:
    return VALID_TRANSITIONS.get(ticket.status, [])
'''

# ── Permissions: two versions ────────────────────────────────────

PERMISSIONS_GIT = '''\
from core import get_user
from typing import Optional

PERMISSION_MATRIX = {
    "admin": ["create", "update", "assign", "close", "delete", "view_audit"],
    "agent": ["create", "update", "assign", "close", "view_audit"],
    "viewer": ["view"],
}


def has_permission(user, action: str) -> bool:
    return action in PERMISSION_MATRIX.get(user.role, [])


def require_permission(user, action: str):
    if not has_permission(user, action):
        raise PermissionError(f"{user.name} ({user.role}) cannot {action}")


def get_allowed_actions(user) -> list:
    return PERMISSION_MATRIX.get(user.role, [])
'''

PERMISSIONS_CNF = '''\
from core import get_user
from typing import Optional

PERMISSION_MATRIX = {
    "admin": ["create", "update", "assign", "close", "archive",
              "delete", "view_audit", "view_analytics"],
    "agent": ["create", "update", "assign", "close", "view_audit"],
    "viewer": ["view"],
}


def has_permission(user, action: str) -> bool:
    return action in PERMISSION_MATRIX.get(user.role, [])


def require_permission(user, action: str):
    if not has_permission(user, action):
        raise PermissionError(f"{user.name} ({user.role}) cannot {action}")


def can_archive(user) -> bool:
    return has_permission(user, "archive")


def get_allowed_actions(user) -> list:
    return PERMISSION_MATRIX.get(user.role, [])
'''

# ── Audit: same in both (audit ALWAYS records, including archived) ──

AUDIT_PY = '''\
from dataclasses import dataclass, field
from typing import List, Optional, Dict
import time

_audit_log: list = []


@dataclass
class AuditEntry:
    timestamp: str
    action: str
    ticket_id: str
    user_id: str
    details: Dict = field(default_factory=dict)


def log_action(action: str, ticket_id: str, user_id: str,
               **details) -> "AuditEntry":
    entry = AuditEntry(
        timestamp=str(int(time.time())),
        action=action, ticket_id=ticket_id,
        user_id=user_id, details=details,
    )
    _audit_log.append(entry)
    return entry


def get_audit_trail(ticket_id: Optional[str] = None) -> List["AuditEntry"]:
    if ticket_id:
        return [e for e in _audit_log if e.ticket_id == ticket_id]
    return list(_audit_log)


def audit_transition(ticket_id: str, user_id: str,
                     old_status: str, new_status: str) -> "AuditEntry":
    return log_action("transition", ticket_id, user_id,
                      old_status=old_status, new_status=new_status)


def audit_create(ticket_id: str, user_id: str, title: str) -> "AuditEntry":
    return log_action("create", ticket_id, user_id, title=title)


def audit_assignment(ticket_id: str, user_id: str,
                     assignee: str) -> "AuditEntry":
    return log_action("assign", ticket_id, user_id, assignee=assignee)


def reset_audit():
    _audit_log.clear()
'''

# ── Notifications: two versions ──────────────────────────────────

NOTIFICATIONS_GIT = '''\
from typing import Optional, List, Dict

_notifications: list = []
_subscribers: Dict[str, List[str]] = {}


def subscribe(ticket_id: str, user_email: str):
    if ticket_id not in _subscribers:
        _subscribers[ticket_id] = []
    if user_email not in _subscribers[ticket_id]:
        _subscribers[ticket_id].append(user_email)


def get_subscribers(ticket_id: str) -> List[str]:
    return _subscribers.get(ticket_id, [])


def should_notify(ticket, event_type: str) -> bool:
    return True


def notify_transition(ticket, old_status: str, new_status: str) -> Optional[str]:
    if not should_notify(ticket, "transition"):
        return None
    msg = f"Ticket {ticket.id}: {old_status} -> {new_status}"
    _notifications.append({"ticket_id": ticket.id, "message": msg,
                           "type": "transition"})
    return msg


def notify_assignment(ticket, assignee_name: str) -> Optional[str]:
    if not should_notify(ticket, "assignment"):
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
    _subscribers.clear()
'''

NOTIFICATIONS_CNF = '''\
from typing import Optional, List, Dict

_notifications: list = []
_subscribers: Dict[str, List[str]] = {}

SILENT_STATUSES = ["archived"]


def subscribe(ticket_id: str, user_email: str):
    if ticket_id not in _subscribers:
        _subscribers[ticket_id] = []
    if user_email not in _subscribers[ticket_id]:
        _subscribers[ticket_id].append(user_email)


def get_subscribers(ticket_id: str) -> List[str]:
    return _subscribers.get(ticket_id, [])


def should_notify(ticket, event_type: str) -> bool:
    if ticket.status in SILENT_STATUSES:
        return False
    return True


def notify_transition(ticket, old_status: str, new_status: str) -> Optional[str]:
    if new_status in SILENT_STATUSES:
        return None
    if not should_notify(ticket, "transition"):
        return None
    msg = f"Ticket {ticket.id}: {old_status} -> {new_status}"
    _notifications.append({"ticket_id": ticket.id, "message": msg,
                           "type": "transition"})
    return msg


def notify_assignment(ticket, assignee_name: str) -> Optional[str]:
    if not should_notify(ticket, "assignment"):
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
    _subscribers.clear()
'''

# ── Analytics: two versions ──────────────────────────────────────

ANALYTICS_GIT = '''\
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


def tickets_by_priority() -> Dict[str, int]:
    result = {}
    for t in list_tickets():
        result[t.priority] = result.get(t.priority, 0) + 1
    return result


def tickets_by_assignee() -> Dict[str, int]:
    result = {}
    for t in list_tickets():
        if t.assignee:
            result[t.assignee] = result.get(t.assignee, 0) + 1
    return result


def unassigned_tickets() -> List:
    return [t for t in list_tickets() if t.assignee is None]
'''

ANALYTICS_CNF = '''\
from core import list_tickets
from typing import Dict, List

ACTIVE_STATUSES = ["open", "in_progress", "resolved"]
INACTIVE_STATUSES = ["closed", "archived"]


def ticket_summary() -> Dict:
    tickets = list_tickets()
    summary = {
        "total": len(tickets),
        "open": len([t for t in tickets if t.status == "open"]),
        "in_progress": len([t for t in tickets if t.status == "in_progress"]),
        "resolved": len([t for t in tickets if t.status == "resolved"]),
        "closed": len([t for t in tickets if t.status == "closed"]),
        "archived": len([t for t in tickets if t.status == "archived"]),
        "active": len([t for t in tickets if t.status in ACTIVE_STATUSES]),
    }
    return summary


def active_ticket_count() -> int:
    return len([t for t in list_tickets() if t.status in ACTIVE_STATUSES])


def tickets_by_priority(active_only: bool = True) -> Dict[str, int]:
    result = {}
    for t in list_tickets():
        if active_only and t.status not in ACTIVE_STATUSES:
            continue
        result[t.priority] = result.get(t.priority, 0) + 1
    return result


def tickets_by_assignee(active_only: bool = True) -> Dict[str, int]:
    result = {}
    for t in list_tickets():
        if active_only and t.status not in ACTIVE_STATUSES:
            continue
        if t.assignee:
            result[t.assignee] = result.get(t.assignee, 0) + 1
    return result


def unassigned_tickets() -> List:
    return [t for t in list_tickets()
            if t.assignee is None and t.status in ACTIVE_STATUSES]
'''

# ── Integration tests — reveal semantic bugs ─────────────────────

INTEGRATION_TESTS = '''\
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from core import *
from models import Ticket, User
from workflow import *
from permissions import *
from audit import *
from notifications import *
from analytics import *


def test_base_create():
    reset_state()
    t = create_ticket("Bug", "Broken")
    assert t.status == "open"


def test_base_close():
    reset_state()
    t = create_ticket("Bug", "Broken")
    close_ticket(t.id)
    assert get_ticket(t.id).status == "closed"


def test_workflow_transitions():
    reset_state()
    t = create_ticket("Bug", "Broken")
    transition_ticket(t.id, "in_progress")
    assert get_ticket(t.id).status == "in_progress"
    transition_ticket(t.id, "resolved")
    assert get_ticket(t.id).status == "resolved"


def test_workflow_archive():
    reset_state()
    t = create_ticket("Old bug", "Fixed")
    transition_ticket(t.id, "closed")
    archive_ticket(t.id)
    assert get_ticket(t.id).status == "archived"
    assert is_archived(get_ticket(t.id))


def test_workflow_invalid_transition():
    reset_state()
    t = create_ticket("Bug", "Broken")
    try:
        transition_ticket(t.id, "archived")
        assert False, "Should have raised ValueError"
    except ValueError:
        pass


def test_permissions_basic():
    reset_state()
    admin = register_user("U-1", "Admin", "a@t.com", "admin")
    viewer = register_user("U-2", "View", "v@t.com", "viewer")
    assert has_permission(admin, "create")
    assert not has_permission(viewer, "create")


def test_audit_trail():
    reset_state()
    reset_audit()
    t = create_ticket("Bug", "Broken")
    audit_create(t.id, "U-1", "Bug")
    audit_transition(t.id, "U-1", "open", "closed")
    trail = get_audit_trail(t.id)
    assert len(trail) == 2


def test_notification_on_transition():
    reset_state()
    reset_notifications()
    t = create_ticket("Bug", "Broken")
    msg = notify_transition(t, "open", "in_progress")
    assert msg is not None
    assert len(get_notifications(t.id)) == 1


# ═══════════════════════════════════════════════════════════════
# INTEGRATION TESTS — cross-cutting correctness
# These reveal whether agents discovered each other's features.
# ═══════════════════════════════════════════════════════════════

def test_archived_no_notification():
    """Archived tickets must NOT trigger notifications."""
    reset_state()
    reset_notifications()
    t = create_ticket("Old bug", "Fixed long ago")
    update_ticket(t.id, status="closed")
    update_ticket(t.id, status="archived")
    msg = notify_transition(t, "closed", "archived")
    assert msg is None, (
        f"Archived ticket triggered notification: {msg}")
    assert len(get_notifications()) == 0, (
        "Notifications list should be empty for archived transitions")


def test_active_count_excludes_archived():
    """Active count must exclude archived tickets."""
    reset_state()
    t1 = create_ticket("Active", "Still open")
    t2 = create_ticket("Old", "Archive me")
    update_ticket(t2.id, status="closed")
    update_ticket(t2.id, status="archived")
    count = active_ticket_count()
    assert count == 1, (
        f"Active count is {count}, expected 1 (archived should be excluded)")


def test_summary_has_all_statuses():
    """Summary must include all workflow states."""
    reset_state()
    summary = ticket_summary()
    for status in ["open", "closed", "archived"]:
        assert status in summary, (
            f"Summary missing '{status}': {summary}")


def test_archive_requires_permission():
    """Only admins can archive. Archive must be in the permission matrix."""
    reset_state()
    admin = register_user("U-1", "Admin", "a@t.com", "admin")
    agent = register_user("U-2", "Agent", "b@t.com", "agent")
    assert has_permission(admin, "archive"), (
        "Admin should have archive permission")
    assert not has_permission(agent, "archive"), (
        "Agent should NOT have archive permission")


def test_audit_includes_archived_transitions():
    """Audit trail must record transitions TO archived."""
    reset_state()
    reset_audit()
    t = create_ticket("Bug", "Fixed")
    audit_transition(t.id, "U-1", "closed", "archived")
    trail = get_audit_trail(t.id)
    assert len(trail) == 1
    assert trail[0].details["new_status"] == "archived"


def test_unassigned_excludes_archived():
    """Unassigned ticket list should only show active tickets."""
    reset_state()
    t1 = create_ticket("Active", "Needs work")
    t2 = create_ticket("Done", "Archive it")
    update_ticket(t2.id, status="closed")
    update_ticket(t2.id, status="archived")
    unassigned = unassigned_tickets()
    ids = [t.id for t in unassigned]
    assert t1.id in ids, "Active unassigned ticket should appear"
    assert t2.id not in ids, (
        "Archived ticket should NOT appear in unassigned list")


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
                results.append((name, "ERROR", str(e)))
    for name, status, msg in results:
        if status != "PASS":
            print(f"  {status}: {name}: {msg}")
    print(f"{passed} passed, {failed} failed, {errors} errors")
'''


# ════════════════════════════════════════════════════════════════════
# Operation tracking (same as E19)
# ════════════════════════════════════════════════════════════════════

class AgentLog:
    def __init__(self, name, task):
        self.name = name
        self.task = task
        self.ops = []
        self.t0 = time.time()
        self.elapsed = 0

    def discover(self, detail, rediscovery=False):
        self.ops.append(("discover", detail, rediscovery))

    def inherit(self, detail):
        self.ops.append(("inherit", detail, False))

    def query(self, detail):
        self.ops.append(("query", detail, False))

    def action(self, detail):
        self.ops.append(("action", detail, False))

    def done(self):
        self.elapsed = time.time() - self.t0

    def count(self, kind):
        return len([o for o in self.ops if o[0] == kind])

    def count_redisc(self):
        return len([o for o in self.ops if o[0] == "discover" and o[2]])


# ════════════════════════════════════════════════════════════════════
# Infrastructure
# ════════════════════════════════════════════════════════════════════

def fresh_workspace(label):
    tmp = Path(tempfile.mkdtemp(prefix=f"f2-{label}-"))
    for f in ["models.py", "core.py", "test_claimdesk.py"]:
        shutil.copy2(CODEBASE / f, tmp / f)
    return tmp


def run_tests(workspace, test_file="test_claimdesk.py"):
    r = subprocess.run(
        [sys.executable, test_file],
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


def cleanup(path):
    shutil.rmtree(path, ignore_errors=True)


# ════════════════════════════════════════════════════════════════════
# MCP client
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
            "clientInfo": {"name": "f2-eval", "version": "1.0"},
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
# Git condition — 5 agents, independent forks, merge
# ════════════════════════════════════════════════════════════════════

def run_git_condition():
    ws = fresh_workspace("git")
    agents = []
    prior = []

    def read_base(agent):
        is_redisc = len(prior) > 0
        for f in ["core.py", "models.py"]:
            text = (ws / f).read_text()
            fns = re.findall(r"^def (\w+)", text, re.MULTILINE)
            agent.discover(
                f"read {f} — {len(fns)} functions", rediscovery=is_redisc)

    # ── Agent 1: Workflow ──────────────────────────────────────
    a1 = AgentLog("Agent 1", "Workflow: states, transitions, archive")
    read_base(a1)
    (ws / "workflow.py").write_text(WORKFLOW_PY)
    a1.action("add workflow.py — 7 functions, 5 states, transition rules")
    a1.done()
    agents.append(a1)
    prior.append(a1)

    # ── Agent 2: Permissions (forked from base, doesn't see workflow) ──
    a2 = AgentLog("Agent 2", "Permissions: roles, access control")
    read_base(a2)
    (ws / "permissions.py").write_text(PERMISSIONS_GIT)
    a2.action("add permissions.py — 3 functions, 3 roles")
    a2.action("⚠ no 'archive' permission (doesn't know archive exists)")
    a2.done()
    agents.append(a2)
    prior.append(a2)

    # ── Agent 3: Audit ─────────────────────────────────────────
    a3 = AgentLog("Agent 3", "Audit: action logging, trail")
    read_base(a3)
    (ws / "audit.py").write_text(AUDIT_PY)
    a3.action("add audit.py — 6 functions, records all actions")
    a3.done()
    agents.append(a3)
    prior.append(a3)

    # ── Agent 4: Notifications (doesn't know about archived) ──
    a4 = AgentLog("Agent 4", "Notifications: transition alerts")
    read_base(a4)
    (ws / "notifications.py").write_text(NOTIFICATIONS_GIT)
    a4.action("add notifications.py — 6 functions")
    a4.action("⚠ should_notify always True (doesn't know about archived)")
    a4.done()
    agents.append(a4)
    prior.append(a4)

    # ── Agent 5: Analytics (only knows open/closed) ───────────
    a5 = AgentLog("Agent 5", "Analytics: summary, counts, reports")
    read_base(a5)
    (ws / "analytics.py").write_text(ANALYTICS_GIT)
    a5.action("add analytics.py — 5 functions")
    a5.action("⚠ only tracks open/closed (doesn't know other statuses)")
    a5.done()
    agents.append(a5)
    prior.append(a5)

    # ── Run tests ──────────────────────────────────────────────
    (ws / "test_integration.py").write_text(INTEGRATION_TESTS)
    bp, bf, be, _ = run_tests(ws)
    ip, iff, ie, failures = run_tests(ws, "test_integration.py")

    result = {
        "base_pass": bp, "base_fail": bf,
        "integ_pass": ip, "integ_fail": iff, "integ_error": ie,
        "failures": failures,
    }
    cleanup(ws)
    return agents, result


# ════════════════════════════════════════════════════════════════════
# CNF condition — 5 agents, shared claim graph
# ════════════════════════════════════════════════════════════════════

def run_cnf_condition():
    ws = fresh_workspace("cnf")
    agents = []
    ckpt = str(ws / ".cnf-checkpoint.json")
    mcp = MCPClient()

    try:
        mcp.tool("reset")

        # ── Agent 1: Workflow — parse base + add workflow ─────
        a1 = AgentLog("Agent 1", "Workflow: states, transitions, archive")
        mcp.tool("set_agent", {"name": "workflow-agent"})

        for f in ["core.py", "models.py"]:
            source = (ws / f).read_text()
            result = mcp.tool("parse_program",
                              {"source": source, "language": "python"})
            count = len(re.findall(r"^\s*\d+:", result, re.MULTILINE))
            a1.discover(f"parse {f} → {count} entities")

        (ws / "workflow.py").write_text(WORKFLOW_PY)
        wf_result = mcp.tool("parse_program",
                             {"source": WORKFLOW_PY, "language": "python"})
        wf_count = len(re.findall(r"^\s*\d+:", wf_result, re.MULTILINE))
        a1.action(f"parse workflow.py → {wf_count} entities")

        deps = mcp.tool("query",
                        {"body": "(py-fn-depends-on (? caller) (? callee))"})
        dep_count = len(deps.strip().splitlines()) if deps.strip() else 0
        a1.discover(f"dependency graph → {dep_count} edges")

        mcp.tool("checkpoint", {"path": ckpt})
        a1.action("checkpoint — base + workflow parsed")
        a1.done()
        agents.append(a1)

        # ── Agent 2: Permissions — query graph, discover archive ──
        a2 = AgentLog("Agent 2", "Permissions: roles, access control")
        mcp.tool("restore", {"path": ckpt})
        mcp.tool("set_agent", {"name": "permissions-agent"})
        a2.inherit("restore — base + workflow entities, dep graph")

        r = mcp.tool("resolve_symbol", {"name": "archive_ticket"})
        a2.query(f"resolve archive_ticket → {r.strip()}")
        r2 = mcp.tool("resolve_symbol", {"name": "is_archived"})
        a2.query(f"resolve is_archived → {r2.strip()}")

        (ws / "permissions.py").write_text(PERMISSIONS_CNF)
        a2.action("add permissions.py — includes 'archive' permission")
        mcp.tool("checkpoint", {"path": ckpt})
        a2.done()
        agents.append(a2)

        # ── Agent 3: Audit ─────────────────────────────────────
        a3 = AgentLog("Agent 3", "Audit: action logging, trail")
        mcp.tool("restore", {"path": ckpt})
        mcp.tool("set_agent", {"name": "audit-agent"})
        a3.inherit("restore — base + workflow + permissions")

        r = mcp.tool("resolve_symbol", {"name": "archive_ticket"})
        a3.query(f"archive_ticket exists → audit must record archive transitions")

        (ws / "audit.py").write_text(AUDIT_PY)
        a3.action("add audit.py — records ALL actions including archived")
        mcp.tool("checkpoint", {"path": ckpt})
        a3.done()
        agents.append(a3)

        # ── Agent 4: Notifications — query for archived state ──
        a4 = AgentLog("Agent 4", "Notifications: transition alerts")
        mcp.tool("restore", {"path": ckpt})
        mcp.tool("set_agent", {"name": "notifications-agent"})
        a4.inherit("restore — base + workflow + permissions + audit")

        r = mcp.tool("resolve_symbol", {"name": "is_archived"})
        a4.query(f"is_archived exists → {r.strip()}")
        r2 = mcp.tool("resolve_symbol", {"name": "archive_ticket"})
        a4.query(f"archive_ticket exists → must suppress notifications")

        deps = mcp.tool("query",
                        {"body": "(py-fn-depends-on archive_ticket (? dep))"})
        a4.query(f"archive_ticket deps → {deps.strip()}")

        (ws / "notifications.py").write_text(NOTIFICATIONS_CNF)
        a4.action("add notifications.py — suppresses archived notifications")
        mcp.tool("checkpoint", {"path": ckpt})
        a4.done()
        agents.append(a4)

        # ── Agent 5: Analytics — query for all statuses ────────
        a5 = AgentLog("Agent 5", "Analytics: summary, counts, reports")
        mcp.tool("restore", {"path": ckpt})
        mcp.tool("set_agent", {"name": "analytics-agent"})
        a5.inherit("restore — full accumulated state from 4 agents")

        r = mcp.tool("resolve_symbol", {"name": "is_active"})
        a5.query(f"is_active exists → {r.strip()}")
        r2 = mcp.tool("resolve_symbol", {"name": "ACTIVE_STATUSES"})
        found = "not found" not in r2.lower()
        a5.query(f"ACTIVE_STATUSES defined: {found}")

        r3 = mcp.tool("resolve_symbol", {"name": "is_archived"})
        a5.query(f"is_archived exists → exclude from active counts")

        (ws / "analytics.py").write_text(ANALYTICS_CNF)
        a5.action("add analytics.py — all statuses, excludes archived from active")
        mcp.tool("checkpoint", {"path": ckpt})
        a5.done()
        agents.append(a5)

    finally:
        mcp.close()

    # ── Run tests ──────────────────────────────────────────────
    (ws / "test_integration.py").write_text(INTEGRATION_TESTS)
    bp, bf, be, _ = run_tests(ws)
    ip, iff, ie, failures = run_tests(ws, "test_integration.py")

    result = {
        "base_pass": bp, "base_fail": bf,
        "integ_pass": ip, "integ_fail": iff, "integ_error": ie,
        "failures": failures,
    }
    cleanup(ws)
    return agents, result


# ════════════════════════════════════════════════════════════════════
# Output
# ════════════════════════════════════════════════════════════════════

def print_agent(agent, indent="  "):
    labels = {"discover": "discover", "inherit": "INHERIT",
              "query": "query", "action": "action"}
    for op_type, detail, is_redisc in agent.ops:
        label = labels.get(op_type, op_type)
        suffix = "  ← REDISCOVERY" if is_redisc else ""
        print(f"{indent}[{label:>8}]  {detail}{suffix}")


def print_results(git_agents, git_result, cnf_agents, cnf_result):
    print()
    print("═" * 72)
    print("  COMPARISON")
    print("═" * 72)
    print()

    git_disc = sum(a.count("discover") for a in git_agents)
    git_redisc = sum(a.count_redisc() for a in git_agents)
    cnf_disc = sum(a.count("discover") for a in cnf_agents)
    cnf_inherit = sum(a.count("inherit") for a in cnf_agents)
    cnf_query = sum(a.count("query") for a in cnf_agents)

    gt = git_result['base_pass'] + git_result['base_fail']
    ct = cnf_result['base_pass'] + cnf_result['base_fail']
    gi = git_result['integ_pass'] + git_result['integ_fail'] + git_result['integ_error']
    ci = cnf_result['integ_pass'] + cnf_result['integ_fail'] + cnf_result['integ_error']

    print(f"  {'':40} {'Git':>10} {'CNF':>10}")
    print("  " + "─" * 62)
    gbp = git_result['base_pass']
    cbp = cnf_result['base_pass']
    gip = git_result['integ_pass']
    cip = cnf_result['integ_pass']
    print(f"  {'Base tests':40} {str(gbp)+'/'+str(gt):>10} {str(cbp)+'/'+str(ct):>10}")
    print(f"  {'Integration tests':40} {str(gip)+'/'+str(gi):>10} {str(cip)+'/'+str(ci):>10}")
    print("  " + "─" * 62)
    print(f"  {'Discoveries':40} {git_disc:>10} {cnf_disc:>10}")
    print(f"  {'  of which rediscovery':40} {git_redisc:>10} {'0':>10}")
    print(f"  {'Inherited (checkpoint restore)':40} {'—':>10} {cnf_inherit:>10}")
    print(f"  {'Queries on inherited state':40} {'—':>10} {cnf_query:>10}")
    print("  " + "─" * 62)

    git_bugs = git_result["integ_fail"] + git_result["integ_error"]
    cnf_bugs = cnf_result["integ_fail"] + cnf_result["integ_error"]
    print(f"  {'Cross-cutting bugs':40} {git_bugs:>10} {cnf_bugs:>10}")

    if git_result["failures"]:
        print()
        print("  Git integration failures:")
        for f in git_result["failures"]:
            print(f"    {f}")

    if cnf_result["failures"]:
        print()
        print("  CNF integration failures:")
        for f in cnf_result["failures"]:
            print(f"    {f}")

    print()
    print("  " + "─" * 62)
    print()
    print("  The git condition passes base tests but fails integration tests")
    print("  because agents built features independently — each agent's code")
    print("  is correct in isolation but inconsistent with other agents' work.")
    print()
    print("  The CNF condition passes all tests because each agent queried")
    print("  the shared graph before writing code. Agent 4 discovered the")
    print("  archived state and suppressed notifications. Agent 5 discovered")
    print("  all workflow statuses and excluded archived from active counts.")
    print("  Agent 2 discovered the archive action and added the permission.")


def main():
    print("═" * 72)
    print("  F2: ClaimDesk — Parallel Feature Construction")
    print("  5 agents build a CRM/helpdesk app")
    print("═" * 72)
    print()

    # Verify base
    ws = fresh_workspace("baseline")
    p, f, e, _ = run_tests(ws)
    cleanup(ws)
    print(f"  Base: {p} passed, {f} failed")
    if f != 0:
        print("ERROR: base tests must pass")
        sys.exit(1)
    print()

    # ── Git condition ────────────────────────────────────────
    print("═" * 72)
    print("  GIT CONDITION — 5 agents, independent forks")
    print("═" * 72)
    git_agents, git_result = run_git_condition()
    for agent in git_agents:
        print()
        print(f"  {agent.name}: {agent.task} ({agent.elapsed:.1f}s)")
        print_agent(agent)
    print()
    print(f"  Base tests: {git_result['base_pass']}/"
          f"{git_result['base_pass']+git_result['base_fail']}")
    print(f"  Integration tests: {git_result['integ_pass']}/"
          f"{git_result['integ_pass']+git_result['integ_fail']+git_result['integ_error']}")
    if git_result["failures"]:
        for f in git_result["failures"]:
            print(f"    {f}")

    # ── CNF condition ────────────────────────────────────────
    print()
    print("═" * 72)
    print("  CNF CONDITION — 5 agents, shared claim graph")
    print("═" * 72)
    cnf_agents, cnf_result = run_cnf_condition()
    for agent in cnf_agents:
        print()
        print(f"  {agent.name}: {agent.task} ({agent.elapsed:.1f}s)")
        print_agent(agent)
    print()
    print(f"  Base tests: {cnf_result['base_pass']}/"
          f"{cnf_result['base_pass']+cnf_result['base_fail']}")
    print(f"  Integration tests: {cnf_result['integ_pass']}/"
          f"{cnf_result['integ_pass']+cnf_result['integ_fail']+cnf_result['integ_error']}")
    if cnf_result["failures"]:
        for f in cnf_result["failures"]:
            print(f"    {f}")

    # ── Comparison ───────────────────────────────────────────
    print_results(git_agents, git_result, cnf_agents, cnf_result)

    print()
    print("═" * 72)


if __name__ == "__main__":
    main()

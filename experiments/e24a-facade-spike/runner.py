#!/usr/bin/env python3
"""E24a: Facade Spike — do semantic facades close info-gap bugs?

2 agents build modules for ClaimDesk. The hidden knowledge is in
workflow.py (statuses, transitions). Agents see models.py + core.py
in their prompt but must discover workflow.py through facade tools.

Three conditions:
  facade_full:  5 facade tools (discover_lifecycle + discover + discover_all
                + dependencies + verify_references)
  facade_basic: 4 tools WITHOUT discover_lifecycle (ablation)
  no_graph:     no MCP tools, just models.py + core.py in prompt

Success metric: 4 info-gap tests that require knowledge from workflow.py.

Usage:
    python runner.py                        # default: facade_full
    python runner.py --condition facade_full
    python runner.py --condition facade_basic
    python runner.py --condition no_graph
"""

import argparse
import concurrent.futures
import json
import os
import re
import shutil
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
MODEL = "sonnet"
TIMEOUT = 300

# ════════════════════════════════════════════════════════════════════
# Base codebase — agents see these in their prompt
# ════════════════════════════════════════════════════════════════════

MODELS_PY = '''\
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
'''

CORE_PY = '''\
from models import Ticket, User
from typing import List, Optional, Dict
import time

_tickets: Dict[str, Ticket] = {}
_users: Dict[str, User] = {}
_next_ticket = [1]

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
    _next_ticket[0] = 1
'''

# Hidden from agents — only discoverable through the graph
WORKFLOW_PY = (SCRIPT_DIR / "codebase" / "workflow.py").read_text()

# ════════════════════════════════════════════════════════════════════
# Agent prompts — intentionally minimal (~40 words of task)
# ════════════════════════════════════════════════════════════════════

NOTIFICATIONS_PROMPT = """\
Build notifications.py for ClaimDesk. When a ticket transitions between \
statuses, notify interested parties. Some ticket states should not trigger \
notifications. Use the available tools to discover the codebase structure \
before writing code.

Required API:
- notify_transition(ticket_id: str, old_status: str, new_status: str) -> None
- get_notifications() -> list of dicts
- reset_notifications() -> None

Here is the existing codebase you are extending:

<models.py>
{models}
</models.py>

<core.py>
{core}
</core.py>

Write ONLY the notifications.py module. Output ONLY valid Python code."""

ANALYTICS_PROMPT = """\
Build analytics.py for ClaimDesk. Use the available tools to discover the \
codebase structure before writing code.

Required API:
- ticket_summary() -> dict mapping each possible status string to count
- active_ticket_count() -> int (exclude terminal/inactive tickets)
- unassigned_tickets() -> list of Ticket (exclude terminal/inactive tickets)

Here is the existing codebase you are extending:

<models.py>
{models}
</models.py>

<core.py>
{core}
</core.py>

Write ONLY the analytics.py module. Output ONLY valid Python code."""

AGENTS = [
    {"name": "notifications", "module": "notifications.py",
     "prompt": NOTIFICATIONS_PROMPT},
    {"name": "analytics", "module": "analytics.py",
     "prompt": ANALYTICS_PROMPT},
]

# ════════════════════════════════════════════════════════════════════
# Integration tests — 6 tests, 4 target info-gap bugs
# ════════════════════════════════════════════════════════════════════

INTEGRATION_TESTS = '''\
"""E24a integration tests — 6 tests, 4 info-gap targets."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from models import Ticket
from core import create_ticket, update_ticket, get_ticket, list_tickets, register_user, reset_state
from workflow import TERMINAL_STATUSES, ACTIVE_STATUSES, VALID_TRANSITIONS, transition_ticket


def setup():
    reset_state()
    register_user("u1", "Alice", "alice@test.com", role="agent")
    register_user("u2", "Admin", "admin@test.com", role="admin")


def test_01_notify_on_transition():
    """Basic: notification fires on status change."""
    setup()
    from notifications import notify_transition, get_notifications, reset_notifications
    reset_notifications()
    t = create_ticket("Bug", "desc")
    transition_ticket(t.id, "in_progress")
    notify_transition(t.id, "open", "in_progress")
    assert len(get_notifications()) > 0, "Should have at least one notification"


def test_02_no_notify_for_archived():
    """INFO-GAP: Archived tickets must NOT trigger notifications."""
    setup()
    from notifications import notify_transition, get_notifications, reset_notifications
    reset_notifications()
    t = create_ticket("Old", "desc")
    transition_ticket(t.id, "closed")
    transition_ticket(t.id, "archived")
    notify_transition(t.id, "closed", "archived")
    notifs = get_notifications()
    archived_notifs = [n for n in notifs
                       if isinstance(n, dict) and "archived" in str(n).lower()]
    assert len(archived_notifs) == 0, \\
        f"Archived transition should NOT trigger notification: {notifs}"


def test_03_active_count_excludes_archived():
    """INFO-GAP: active_ticket_count() must not count archived tickets."""
    setup()
    from analytics import active_ticket_count
    t1 = create_ticket("Active", "desc")
    t2 = create_ticket("Archived", "desc")
    transition_ticket(t2.id, "closed")
    transition_ticket(t2.id, "archived")
    count = active_ticket_count()
    assert count == 1, f"Expected 1 active, got {count}. Archived ticket was counted."


def test_04_summary_includes_all_statuses():
    """INFO-GAP: ticket_summary() must have entries for on_hold and archived."""
    setup()
    from analytics import ticket_summary
    t1 = create_ticket("A", "desc")
    t2 = create_ticket("B", "desc")
    transition_ticket(t1.id, "in_progress")
    transition_ticket(t1.id, "on_hold")
    transition_ticket(t2.id, "closed")
    transition_ticket(t2.id, "archived")
    summary = ticket_summary()
    assert "on_hold" in summary, f"Summary missing on_hold: {summary}"
    assert "archived" in summary, f"Summary missing archived: {summary}"


def test_05_unassigned_excludes_archived():
    """INFO-GAP: unassigned_tickets() must not include archived tickets."""
    setup()
    from analytics import unassigned_tickets
    t1 = create_ticket("Active unassigned", "desc")
    t2 = create_ticket("Archived unassigned", "desc")
    transition_ticket(t2.id, "closed")
    transition_ticket(t2.id, "archived")
    unassigned = unassigned_tickets()
    assert len(unassigned) == 1, \\
        f"Expected 1 unassigned, got {len(unassigned)}. Archived was included."


def test_06_notify_uses_workflow_import():
    """INFO-GAP (code check): notifications.py must import from workflow."""
    with open(os.path.join(os.path.dirname(__file__), "notifications.py")) as f:
        source = f.read()
    assert "from workflow import" in source or "import workflow" in source, \\
        "notifications.py must import from workflow module, not define its own status constants"


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

INFO_GAP_TESTS = {"test_02", "test_03", "test_04", "test_05"}

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


def kill_port(port):
    try:
        result = subprocess.run(["ss", "-tlnp"], capture_output=True, text=True)
        for line in result.stdout.splitlines():
            if f":{port}" in line:
                m = re.search(r'pid=(\d+)', line)
                if m:
                    os.kill(int(m.group(1)), 9)
                    time.sleep(1)
    except Exception:
        pass


def start_daemon():
    kill_port(DAEMON_PORT)

    checkpoint_path = Path.home() / ".cnf" / "checkpoint.json"
    backup = None
    if checkpoint_path.exists():
        backup = checkpoint_path.with_suffix(".json.e24abak")
        shutil.copy2(checkpoint_path, backup)
        checkpoint_path.unlink()

    proc = subprocess.Popen(
        ["racket", str(SERVER_RKT), "--daemon", str(DAEMON_PORT)],
        stderr=subprocess.PIPE, text=True,
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
    """Parse models.py, core.py, workflow.py into the graph."""
    sock = socket.socket()
    sock.connect(("localhost", DAEMON_PORT))

    send_rpc(sock, "initialize", {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "e24a-runner", "version": "0.1"},
    })

    sources = [
        ("models.py", MODELS_PY, "python"),
        ("core.py", CORE_PY, "python"),
        ("workflow.py", WORKFLOW_PY, "python"),
    ]

    resp = send_rpc(sock, "tools/call", {
        "name": "define_predicates",
        "arguments": {"names": ["source-module"]},
    })
    define_text = get_tool_text(resp)
    print(f"    Predicate: {define_text}")
    sm_match = re.search(r'source-module:\s*(\d+)', define_text)
    sm_pred_id = sm_match.group(1) if sm_match else "source-module"

    for filename, source, lang in sources:
        pre_resp = send_rpc(sock, "tools/call", {
            "name": "query",
            "arguments": {"body": "(current-triple (? e) py-form-kind (? kind))"},
        })
        pre_text = get_tool_text(pre_resp)
        pre_eids = set()
        for line in pre_text.strip().split("\n"):
            m = re.search(r'\?e\s*=\s*(\d+)', line)
            if m:
                pre_eids.add(m.group(1))

        resp = send_rpc(sock, "tools/call", {
            "name": "parse_program",
            "arguments": {"source": source, "language": lang},
        })
        text = get_tool_text(resp)
        print(f"    Parsed {filename}: {text.split(chr(10))[0]}")

        post_resp = send_rpc(sock, "tools/call", {
            "name": "query",
            "arguments": {"body": "(current-triple (? e) py-form-kind (? kind))"},
        })
        post_text = get_tool_text(post_resp)
        module_name = filename.replace(".py", "")

        for line in post_text.strip().split("\n"):
            m = re.search(r'\?e\s*=\s*(\d+)', line)
            if m:
                eid = m.group(1)
                if eid not in pre_eids:
                    send_rpc(sock, "tools/call", {
                        "name": "claim",
                        "arguments": {
                            "left": eid,
                            "predicate": sm_pred_id,
                            "right": f'"{module_name}"',
                        },
                    })

    # Checkpoint so MCP tool connections see the data
    resp = send_rpc(sock, "tools/call", {"name": "checkpoint", "arguments": {}})
    print(f"    {get_tool_text(resp)}")

    resp = send_rpc(sock, "tools/call", {"name": "status", "arguments": {}})
    print(f"    Graph: {get_tool_text(resp)}")

    sock.close()

    # Verify new connections can see the data
    time.sleep(1)
    verify_sock = socket.socket()
    verify_sock.connect(("localhost", DAEMON_PORT))
    send_rpc(verify_sock, "initialize", {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "e24a-verify", "version": "0.1"},
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
    verify_sock.close()


# ════════════════════════════════════════════════════════════════════
# Code extraction
# ════════════════════════════════════════════════════════════════════

def extract_code(text):
    """Extract Python code from agent output."""
    if not text:
        return None
    match = re.search(r'```python\n(.*?)```', text, re.DOTALL)
    if match:
        return match.group(1).strip()
    match = re.search(r'```\n(.*?)```', text, re.DOTALL)
    if match:
        return match.group(1).strip()
    # Try to find raw code starting with common Python patterns
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


# ════════════════════════════════════════════════════════════════════
# Agent launching
# ════════════════════════════════════════════════════════════════════

def write_mcp_config(condition):
    """Write MCP config for the given condition. Returns path."""
    facade_py = str(SCRIPT_DIR / "facade-tools.py")
    args = [facade_py, str(DAEMON_PORT)]
    if condition == "facade_basic":
        args += ["--exclude", "discover_lifecycle"]

    config = {
        "mcpServers": {
            "cnf-facade": {
                "command": sys.executable,
                "args": args,
            }
        }
    }
    config_path = SCRIPT_DIR / f"mcp-config-{condition}.json"
    config_path.write_text(json.dumps(config, indent=2))
    return str(config_path)


def launch_facade_agent(agent_spec, mcp_config_path):
    """Launch an agent with facade MCP tools."""
    prompt = agent_spec["prompt"].format(models=MODELS_PY, core=CORE_PY)
    name = agent_spec["name"]

    start = time.monotonic()
    try:
        allowed = [f"mcp__cnf-facade__{t}" for t in FACADE_TOOL_NAMES]
        cmd = ["claude", "-p", "--model", MODEL,
               "--output-format", "json",
               "--tools", "",
               "--allowedTools"] + allowed + [
               "--mcp-config", mcp_config_path]
        result = subprocess.run(
            cmd, input=prompt, capture_output=True, text=True, timeout=TIMEOUT,
        )
        elapsed = time.monotonic() - start

        output_text = result.stdout or ""
        agent_result = _parse_agent_output(output_text)

        code = extract_code(agent_result)
        if code:
            return {"name": name, "code": code, "elapsed": elapsed,
                    "raw_output": output_text, "error": None}
        else:
            return {"name": name, "code": None, "elapsed": elapsed,
                    "raw_output": output_text,
                    "error": f"No code extracted from output ({len(output_text)} chars)"}
    except subprocess.TimeoutExpired:
        return {"name": name, "code": None, "elapsed": time.monotonic() - start,
                "raw_output": "", "error": "timeout"}
    except Exception as e:
        return {"name": name, "code": None, "elapsed": time.monotonic() - start,
                "raw_output": "", "error": str(e)}


def launch_no_graph_agent(agent_spec):
    """Launch an agent with no MCP tools (baseline)."""
    prompt = agent_spec["prompt"].format(models=MODELS_PY, core=CORE_PY)
    name = agent_spec["name"]

    start = time.monotonic()
    try:
        cmd = ["claude", "-p", "--model", MODEL,
               "--output-format", "json",
               "--tools", ""]
        result = subprocess.run(
            cmd, input=prompt, capture_output=True, text=True, timeout=TIMEOUT,
        )
        elapsed = time.monotonic() - start

        output_text = result.stdout or ""
        agent_result = _parse_agent_output(output_text)

        code = extract_code(agent_result)
        if code:
            return {"name": name, "code": code, "elapsed": elapsed,
                    "raw_output": output_text, "error": None}
        else:
            return {"name": name, "code": None, "elapsed": elapsed,
                    "raw_output": output_text,
                    "error": f"No code extracted from output ({len(output_text)} chars)"}
    except subprocess.TimeoutExpired:
        return {"name": name, "code": None, "elapsed": time.monotonic() - start,
                "raw_output": "", "error": "timeout"}
    except Exception as e:
        return {"name": name, "code": None, "elapsed": time.monotonic() - start,
                "raw_output": "", "error": str(e)}


def _parse_agent_output(raw):
    """Extract text from --output-format json, falling back to raw text."""
    try:
        data = json.loads(raw)
        # Claude CLI JSON format: {"result": "...", ...} or just text
        if isinstance(data, dict):
            return data.get("result", data.get("content", raw))
        return raw
    except (json.JSONDecodeError, TypeError):
        return raw


# ════════════════════════════════════════════════════════════════════
# Test running
# ════════════════════════════════════════════════════════════════════

def assemble_workspace(agent_results):
    """Create a temp workspace with all modules and tests."""
    ws = Path(tempfile.mkdtemp(prefix="e24a-"))
    (ws / "models.py").write_text(MODELS_PY)
    (ws / "core.py").write_text(CORE_PY)
    (ws / "workflow.py").write_text(WORKFLOW_PY)
    (ws / "test_integration.py").write_text(INTEGRATION_TESTS)
    for r in agent_results:
        if r["code"]:
            (ws / r["module"]).write_text(r["code"])
    return ws


def run_tests(workspace):
    """Run integration tests, return {test_name: 'pass'|'fail'|'error', ...}."""
    r = subprocess.run(
        [sys.executable, "test_integration.py"],
        cwd=str(workspace), capture_output=True, text=True, timeout=30,
    )
    out = r.stdout + r.stderr

    results = {}
    p = f = e = 0
    for line in out.strip().splitlines():
        if line.strip().startswith("PASS:") or line.strip().startswith("FAIL:") or line.strip().startswith("ERROR:"):
            parts = line.strip().split(":", 2)
            status = parts[0].strip().lower()
            test_name = parts[1].strip().split(":")[0].strip() if len(parts) > 1 else ""
            results[test_name] = status
        elif "passed" in line:
            nums = line.strip().split(",")
            p = int(nums[0].strip().split()[0])
            if len(nums) > 1:
                f = int(nums[1].strip().split()[0])
            if len(nums) > 2:
                e = int(nums[2].strip().split()[0])

    # If we only got the summary line, infer per-test from the output
    if not results:
        for line in out.strip().splitlines():
            line = line.strip()
            if line.startswith("FAIL:"):
                test_name = line.split(":")[1].strip().split(":")[0].strip()
                results[test_name] = "fail"
            elif line.startswith("ERROR:"):
                test_name = line.split(":")[1].strip().split(":")[0].strip()
                results[test_name] = "error"

    # Tests not in results are assumed pass
    all_tests = [f"test_{i:02d}" for i in range(1, 7)]
    for t in all_tests:
        found = any(t in k for k in results)
        if not found:
            results[t] = "pass"

    return results, p, f, e


# ════════════════════════════════════════════════════════════════════
# Tool-use scoring
# ════════════════════════════════════════════════════════════════════

FACADE_TOOL_NAMES = [
    "discover_lifecycle",
    "discover_all",
    "discover",
    "dependencies",
    "verify_references",
]


def extract_run_metrics(raw_output):
    """Extract structured metrics from claude -p --output-format json."""
    metrics = {"turns": 0, "cost": 0.0, "denials": []}
    if not raw_output:
        return metrics
    try:
        data = json.loads(raw_output)
        metrics["turns"] = data.get("num_turns", 0)
        metrics["cost"] = round(data.get("total_cost_usd", 0), 4)
        metrics["denials"] = [
            d.get("tool_name", "") for d in data.get("permission_denials", [])
        ]
    except (json.JSONDecodeError, TypeError):
        pass
    return metrics


def score_tool_usage(raw_output):
    """Parse agent output for evidence of facade tool calls.

    Returns list of tool names that appear to have been called.
    """
    text = raw_output.lower()
    called = []
    for tool in FACADE_TOOL_NAMES:
        patterns = [
            f'"name": "{tool}"',
            f'"{tool}"',
            re.escape(tool),
        ]
        if any(re.search(p, text) for p in patterns):
            called.append(tool)
    return called


def check_code_quality(code, agent_name):
    """Check agent code for signs of info-gap knowledge.

    Returns dict of quality signals.
    """
    if not code:
        return {"has_code": False}

    signals = {"has_code": True}

    signals["imports_workflow"] = bool(
        re.search(r'from workflow import|import workflow', code))

    signals["uses_terminal_statuses"] = "TERMINAL_STATUSES" in code

    signals["uses_active_statuses"] = "ACTIVE_STATUSES" in code

    signals["uses_all_statuses"] = "ALL_STATUSES" in code

    signals["uses_is_active"] = "is_active" in code

    signals["knows_archived"] = "archived" in code.lower()

    signals["knows_on_hold"] = "on_hold" in code.lower()

    signals["hardcoded_statuses"] = bool(
        re.search(r'\{.*"closed".*"resolved".*\}', code) or
        re.search(r'\[.*"closed".*"resolved".*\]', code))

    return signals


# ════════════════════════════════════════════════════════════════════
# Condition runner
# ════════════════════════════════════════════════════════════════════

def run_condition(condition):
    w = 72
    print()
    print("=" * w)
    print(f"  E24a: {condition}")
    print("=" * w)

    print(f"\n  Launching {len(AGENTS)} agents in parallel...", flush=True)
    build_start = time.monotonic()

    if condition == "no_graph":
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(AGENTS)) as pool:
            futures = {
                pool.submit(launch_no_graph_agent, agent): agent
                for agent in AGENTS
            }
            results = []
            for future in concurrent.futures.as_completed(futures):
                r = future.result()
                # Add module name for workspace assembly
                agent = futures[future]
                r["module"] = agent["module"]
                status = "ok" if r["code"] else f"FAIL: {r['error']}"
                print(f"    {r['name']:15s} {r['elapsed']:6.1f}s  {status}",
                      flush=True)
                results.append(r)
    else:
        mcp_config_path = write_mcp_config(condition)

        with concurrent.futures.ThreadPoolExecutor(max_workers=len(AGENTS)) as pool:
            futures = {
                pool.submit(launch_facade_agent, agent, mcp_config_path): agent
                for agent in AGENTS
            }
            results = []
            for future in concurrent.futures.as_completed(futures):
                r = future.result()
                agent = futures[future]
                r["module"] = agent["module"]
                status = "ok" if r["code"] else f"FAIL: {r['error']}"
                print(f"    {r['name']:15s} {r['elapsed']:6.1f}s  {status}",
                      flush=True)
                results.append(r)

    build_time = time.monotonic() - build_start
    print(f"\n  Build: {build_time:.1f}s")

    # Save agent outputs
    out_dir = SCRIPT_DIR / condition
    out_dir.mkdir(exist_ok=True)
    for r in results:
        if r["code"]:
            (out_dir / r["module"]).write_text(r["code"])
        if r.get("raw_output"):
            (out_dir / f"{r['name']}-output.txt").write_text(r["raw_output"])

    # Assemble workspace and run tests
    ws = assemble_workspace(results)
    test_results, p, f, e = run_tests(ws)
    print(f"  Tests: {p} passed, {f} failed, {e} errors")

    # Classify info-gap failures
    info_gap_bugs = 0
    for test_name in INFO_GAP_TESTS:
        # Match by prefix
        matched = [k for k in test_results if test_name in k]
        for m in matched:
            if test_results[m] != "pass":
                info_gap_bugs += 1
        if not matched:
            # Test didn't run at all (likely import error) — count as bug
            info_gap_bugs += 1

    for test_name, status in sorted(test_results.items()):
        marker = " [INFO-GAP]" if any(ig in test_name for ig in INFO_GAP_TESTS) else ""
        if status != "pass":
            print(f"    {status.upper()}: {test_name}{marker}")

    # Score tool usage and discovery metrics
    agent_details = {}
    for r in results:
        tool_calls = score_tool_usage(r.get("raw_output", ""))
        code_quality = check_code_quality(r.get("code"), r["name"])
        run_metrics = extract_run_metrics(r.get("raw_output", ""))
        agent_details[r["name"]] = {
            "elapsed": round(r["elapsed"], 1),
            "tool_calls": tool_calls,
            "code_quality": code_quality,
            "turns": run_metrics["turns"],
            "cost": run_metrics["cost"],
            "denials": run_metrics["denials"],
            "error": r.get("error"),
            "info_gap_bugs": 0,
        }
        print(f"\n  {r['name']}:")
        print(f"    Turns: {run_metrics['turns']}  Cost: ${run_metrics['cost']}")
        print(f"    Tools called: {tool_calls if tool_calls else 'none'}")
        for k, v in code_quality.items():
            if k != "has_code":
                print(f"    {k}: {v}")

    # Assign info-gap bugs to agents
    notif_gaps = sum(1 for t in ["test_02", "test_06"]
                     if any(t in k and test_results.get(k) != "pass"
                            for k in test_results))
    analytics_gaps = sum(1 for t in ["test_03", "test_04", "test_05"]
                         if any(t in k and test_results.get(k) != "pass"
                                for k in test_results))
    if "notifications" in agent_details:
        agent_details["notifications"]["info_gap_bugs"] = notif_gaps
    if "analytics" in agent_details:
        agent_details["analytics"]["info_gap_bugs"] = analytics_gaps

    return {
        "condition": condition,
        "build_time": round(build_time, 1),
        "agents": agent_details,
        "tests": test_results,
        "info_gap_total": f"{info_gap_bugs}/4",
        "info_gap_bugs": info_gap_bugs,
        "workspace": str(ws),
    }


# ════════════════════════════════════════════════════════════════════
# Main
# ════════════════════════════════════════════════════════════════════

def print_single_result(result):
    w = 72
    print("\n" + "=" * w)
    print("  E24a RESULTS")
    print("=" * w)

    print(f"\n  Condition:    {result['condition']}")
    print(f"  Build time:   {result['build_time']}s")
    print(f"  Info-gap:     {result['info_gap_total']}")

    for name, details in result["agents"].items():
        print(f"\n  {name}:")
        print(f"    Time:        {details['elapsed']}s")
        print(f"    Turns:       {details.get('turns', '?')}")
        print(f"    Cost:        ${details.get('cost', '?')}")
        print(f"    Info-gap:    {details['info_gap_bugs']} bugs")
        cq = details.get("code_quality", {})
        for k in ["imports_workflow", "knows_archived", "knows_on_hold",
                   "uses_is_active", "uses_all_statuses", "hardcoded_statuses"]:
            if k in cq:
                print(f"    {k}: {cq[k]}")

    print(f"\n  Tests:")
    for test_name, status in sorted(result["tests"].items()):
        marker = " [INFO-GAP]" if any(ig in test_name for ig in INFO_GAP_TESTS) else ""
        icon = "PASS" if status == "pass" else status.upper()
        print(f"    {icon}: {test_name}{marker}")


def aggregate_multi(all_runs, condition):
    """Aggregate discovery-rate metrics across multiple runs."""
    n = len(all_runs)
    w = 72

    print("\n" + "=" * w)
    print(f"  E24a-multi: {condition} — {n} runs")
    print("=" * w)

    # Per-agent discovery metrics
    for agent_name in ["analytics", "notifications"]:
        runs_with_agent = [r for r in all_runs if agent_name in r["agents"]]
        if not runs_with_agent:
            continue

        na = len(runs_with_agent)
        imports_wf = sum(1 for r in runs_with_agent
                         if r["agents"][agent_name].get("code_quality", {}).get("imports_workflow"))
        knows_arch = sum(1 for r in runs_with_agent
                         if r["agents"][agent_name].get("code_quality", {}).get("knows_archived"))
        knows_oh = sum(1 for r in runs_with_agent
                       if r["agents"][agent_name].get("code_quality", {}).get("knows_on_hold"))
        uses_is_active = sum(1 for r in runs_with_agent
                             if r["agents"][agent_name].get("code_quality", {}).get("uses_is_active"))
        uses_all_st = sum(1 for r in runs_with_agent
                          if r["agents"][agent_name].get("code_quality", {}).get("uses_all_statuses"))
        hardcoded = sum(1 for r in runs_with_agent
                        if r["agents"][agent_name].get("code_quality", {}).get("hardcoded_statuses"))

        turns = [r["agents"][agent_name].get("turns", 0) for r in runs_with_agent]
        costs = [r["agents"][agent_name].get("cost", 0) for r in runs_with_agent]
        bugs = [r["agents"][agent_name].get("info_gap_bugs", 0) for r in runs_with_agent]

        print(f"\n  {agent_name} ({na} runs):")
        print(f"    imports_workflow:    {imports_wf}/{na}")
        print(f"    knows_archived:     {knows_arch}/{na}")
        print(f"    knows_on_hold:      {knows_oh}/{na}")
        print(f"    uses_is_active:     {uses_is_active}/{na}")
        print(f"    uses_ALL_STATUSES:  {uses_all_st}/{na}")
        print(f"    hardcoded_statuses: {hardcoded}/{na}")
        print(f"    mean turns:         {sum(turns)/na:.1f}")
        print(f"    mean cost:          ${sum(costs)/na:.4f}")
        print(f"    mean info-gap bugs: {sum(bugs)/na:.1f}")
        print(f"    info-gap bugs/run:  {bugs}")

    # Global info-gap
    all_bugs = [r["info_gap_bugs"] for r in all_runs]
    total_opportunities = n * 4
    total_bugs = sum(all_bugs)
    print(f"\n  AGGREGATE:")
    print(f"    Runs:               {n}")
    print(f"    Info-gap bugs:      {total_bugs}/{total_opportunities}"
          f" ({total_bugs/total_opportunities:.0%} failure rate)")
    print(f"    Per-run bugs:       {all_bugs}")
    print(f"    Mean bugs/run:      {sum(all_bugs)/n:.1f}")

    total_cost = sum(r["agents"].get("analytics", {}).get("cost", 0) +
                     r["agents"].get("notifications", {}).get("cost", 0)
                     for r in all_runs)
    print(f"    Total cost:         ${total_cost:.2f}")
    print(f"    Mean cost/run:      ${total_cost/n:.4f}")


def main():
    parser = argparse.ArgumentParser(description="E24a: Facade Spike")
    parser.add_argument("--condition", default="facade_full",
                        choices=["facade_full", "facade_basic", "no_graph"],
                        help="Which condition to run (default: facade_full)")
    parser.add_argument("--runs", type=int, default=1,
                        help="Number of runs per condition (default: 1)")
    args = parser.parse_args()

    condition = args.condition
    num_runs = args.runs
    need_daemon = condition in ("facade_full", "facade_basic")

    print(f"\nE24a: Facade Spike — Semantic Facade Tools")
    print(f"  2 agents (notifications, analytics), 6 tests")
    print(f"  Condition: {condition}")
    print(f"  Runs: {num_runs}")
    print(f"  Success metric: 4 info-gap bugs (test_02, 03, 04, 05)")

    daemon_proc = None
    backup = None
    all_runs = []

    try:
        if need_daemon:
            print("\n  Starting CNF daemon...", flush=True)
            daemon_proc, backup = start_daemon()
            print("  Parsing base codebase into graph...", flush=True)
            init_graph()

        for run_idx in range(num_runs):
            if num_runs > 1:
                print(f"\n  ──── Run {run_idx + 1}/{num_runs} ────")

            # Clean output dir between runs to prevent contamination
            out_dir = SCRIPT_DIR / condition
            if out_dir.exists():
                shutil.rmtree(out_dir)

            result = run_condition(condition)
            all_runs.append(result)

            if num_runs == 1:
                print_single_result(result)

    finally:
        if daemon_proc:
            stop_daemon(daemon_proc, backup)

    if num_runs > 1:
        aggregate_multi(all_runs, condition)

    # Save results
    results_path = SCRIPT_DIR / "results.json"
    output = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "experiment": "E24a-multi" if num_runs > 1 else "E24a",
        "condition": condition,
        "num_runs": num_runs,
        "runs": [{
            "agents": r["agents"],
            "tests": r["tests"],
            "info_gap_total": r["info_gap_total"],
            "info_gap_bugs": r["info_gap_bugs"],
            "build_time": r["build_time"],
        } for r in all_runs],
    }
    if num_runs > 1:
        all_bugs = [r["info_gap_bugs"] for r in all_runs]
        output["aggregate"] = {
            "total_bugs": sum(all_bugs),
            "total_opportunities": num_runs * 4,
            "failure_rate": round(sum(all_bugs) / (num_runs * 4), 3),
            "per_run_bugs": all_bugs,
        }
    results_path.write_text(json.dumps(output, indent=2, default=str))
    print(f"\n  Results saved to {results_path}")


if __name__ == "__main__":
    main()

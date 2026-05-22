#!/usr/bin/env python3
"""E24b: Concurrent Facade Agents — facade + shared graph + concurrent agents.

3 agents build ClaimDesk modules simultaneously.
Two conditions:
  cnf:   shared daemon, facade tools, no filesystem access
  file:  isolated worktrees, full source tools, git merge + repair

Usage:
    python runner.py --condition cnf
    python runner.py --condition file
    python runner.py --condition cnf --runs 3
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
DAEMON_PORT = 7892
MODEL = "sonnet"
TIMEOUT = 300

# ════════════════════════════════════════════════════════════════════
# Base codebase — agents see these in their prompt
# ════════════════════════════════════════════════════════════════════

MODELS_PY = (SCRIPT_DIR / "codebase" / "models.py").read_text()
CORE_PY = (SCRIPT_DIR / "codebase" / "core.py").read_text()
WORKFLOW_PY = (SCRIPT_DIR / "codebase" / "workflow.py").read_text()

# ════════════════════════════════════════════════════════════════════
# Agent prompts — minimal, no spoon-feeding
# ════════════════════════════════════════════════════════════════════

NOTIFICATIONS_PROMPT = """\
Build notifications.py for ClaimDesk. When a ticket transitions between \
statuses, notify interested parties. Some ticket states should not trigger \
notifications. {discovery_instruction}

Required API:
- notify_transition(ticket_id: str, old_status: str, new_status: str) -> None
- subscribe(ticket_id: str, user_email: str) -> None
- get_notifications(ticket_id: str = None) -> list of dicts
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
Build analytics.py for ClaimDesk. {discovery_instruction}

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

PERMISSIONS_PROMPT = """\
Build permissions.py for ClaimDesk. Implement role-based access control. \
Agents can manage their own assigned tickets. Admins can manage all tickets. \
Archiving a ticket requires admin role. Reassignment requires admin or \
current assignee. {discovery_instruction}

Required API:
- can_manage(user_id: str, ticket_id: str) -> bool
- can_archive(user_id: str) -> bool
- can_reassign(user_id: str, ticket_id: str) -> bool
- check_permission(user_id: str, ticket_id: str, action: str) -> bool

Here is the existing codebase you are extending:

<models.py>
{models}
</models.py>

<core.py>
{core}
</core.py>

Write ONLY the permissions.py module. Output ONLY valid Python code."""

CNF_DISCOVERY = "Use the available tools to discover the codebase structure before writing code."
FILE_DISCOVERY = "Read the existing codebase files to understand the project structure before writing code."

AGENTS = [
    {"name": "notifications", "module": "notifications.py",
     "prompt": NOTIFICATIONS_PROMPT},
    {"name": "analytics", "module": "analytics.py",
     "prompt": ANALYTICS_PROMPT},
    {"name": "permissions", "module": "permissions.py",
     "prompt": PERMISSIONS_PROMPT},
]

# ════════════════════════════════════════════════════════════════════
# Integration tests — 15 tests, 8 info-gap targets
# ════════════════════════════════════════════════════════════════════

INTEGRATION_TESTS = '''\
"""E24b integration tests — 15 tests, 8 info-gap targets."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from models import Ticket, User
from core import (create_ticket, update_ticket, get_ticket, list_tickets,
                  register_user, get_user, reset_state)
from workflow import (TERMINAL_STATUSES, ACTIVE_STATUSES, VALID_TRANSITIONS,
                      transition_ticket)


def setup():
    reset_state()
    register_user("u1", "Alice", "alice@test.com", role="agent")
    register_user("u2", "Admin", "admin@test.com", role="admin")
    register_user("u3", "Bob", "bob@test.com", role="agent")


# ── Info-gap tests ──

def test_01_no_notify_for_archived():
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


def test_02_active_count_excludes_archived():
    """INFO-GAP: active_ticket_count() must not count archived tickets."""
    setup()
    from analytics import active_ticket_count
    t1 = create_ticket("Active", "desc")
    t2 = create_ticket("Archived", "desc")
    transition_ticket(t2.id, "closed")
    transition_ticket(t2.id, "archived")
    count = active_ticket_count()
    assert count == 1, f"Expected 1 active, got {count}. Archived ticket was counted."


def test_03_summary_includes_all_statuses():
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


def test_04_unassigned_excludes_archived():
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


def test_05_archive_requires_admin():
    """INFO-GAP: Only admins can archive tickets."""
    setup()
    from permissions import can_archive
    assert can_archive("u2") == True, "Admin should be able to archive"
    assert can_archive("u1") == False, "Agent should NOT be able to archive"


def test_06_no_manage_archived():
    """INFO-GAP: Agents cannot manage archived tickets."""
    setup()
    from permissions import can_manage
    t = create_ticket("Done", "desc")
    update_ticket(t.id, assignee="u1")
    transition_ticket(t.id, "closed")
    transition_ticket(t.id, "archived")
    assert can_manage("u1", t.id) == False, \\
        "Agent should NOT manage archived ticket even if assigned"


def test_07_notifications_imports_workflow():
    """INFO-GAP (code check): notifications.py must import from workflow."""
    with open(os.path.join(os.path.dirname(__file__), "notifications.py")) as f:
        source = f.read()
    assert "from workflow import" in source or "import workflow" in source, \\
        "notifications.py must import from workflow module"


def test_08_permissions_imports_workflow():
    """INFO-GAP (code check): permissions.py must import from workflow."""
    with open(os.path.join(os.path.dirname(__file__), "permissions.py")) as f:
        source = f.read()
    assert "from workflow import" in source or "import workflow" in source, \\
        "permissions.py must import from workflow module"


# ── Cross-module tests ──

def test_09_admin_sees_all_in_summary():
    """CROSS: Admin role doesn't affect analytics (no permission gating on reads)."""
    setup()
    from analytics import ticket_summary
    create_ticket("A", "desc")
    create_ticket("B", "desc")
    summary = ticket_summary()
    total = sum(summary.values())
    assert total == 2, f"Summary should count all tickets regardless of user: {summary}"


def test_10_permission_check_actions():
    """CROSS: check_permission dispatches correctly for different actions."""
    setup()
    from permissions import check_permission
    t = create_ticket("Test", "desc")
    update_ticket(t.id, assignee="u1")
    assert check_permission("u1", t.id, "manage") == True
    assert check_permission("u2", t.id, "archive") == True
    assert check_permission("u1", t.id, "archive") == False


# ── Basic functionality tests ──

def test_11_basic_notification():
    """BASIC: Notification fires on normal transition."""
    setup()
    from notifications import notify_transition, get_notifications, reset_notifications, subscribe
    reset_notifications()
    t = create_ticket("Bug", "desc")
    subscribe(t.id, "watcher@test.com")
    notify_transition(t.id, "open", "in_progress")
    notifs = get_notifications()
    assert len(notifs) >= 1, f"Expected notification, got {notifs}"


def test_12_basic_summary():
    """BASIC: ticket_summary counts correctly."""
    setup()
    from analytics import ticket_summary
    create_ticket("A", "desc")
    create_ticket("B", "desc")
    summary = ticket_summary()
    assert summary.get("open", 0) == 2, f"Expected 2 open, got {summary}"


def test_13_basic_can_manage():
    """BASIC: Assigned agent can manage their ticket."""
    setup()
    from permissions import can_manage
    t = create_ticket("Test", "desc")
    update_ticket(t.id, assignee="u1")
    assert can_manage("u1", t.id) == True, "Assigned agent should manage ticket"
    assert can_manage("u2", t.id) == True, "Admin should manage any ticket"


def test_14_subscribe():
    """BASIC: subscribe adds subscriber."""
    setup()
    from notifications import subscribe, get_notifications, notify_transition, reset_notifications
    reset_notifications()
    t = create_ticket("Sub test", "desc")
    subscribe(t.id, "watcher@test.com")
    notify_transition(t.id, "open", "in_progress")
    notifs = get_notifications()
    assert len(notifs) >= 1, f"Expected notification after subscribe, got {notifs}"


def test_15_unassigned_active_only():
    """BASIC: unassigned_tickets returns only unassigned active tickets."""
    setup()
    from analytics import unassigned_tickets
    t1 = create_ticket("Unassigned active", "desc")
    t2 = create_ticket("Assigned active", "desc")
    update_ticket(t2.id, assignee="u1")
    result = unassigned_tickets()
    ids = [t.id for t in result]
    assert t1.id in ids, f"Unassigned active ticket missing: {ids}"
    assert t2.id not in ids, f"Assigned ticket should not be in unassigned: {ids}"


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

INFO_GAP_TESTS = {"test_01", "test_02", "test_03", "test_04",
                  "test_05", "test_06", "test_07", "test_08"}
NUM_TESTS = 15

# ════════════════════════════════════════════════════════════════════
# Daemon + graph infrastructure (from E24a)
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
        backup = checkpoint_path.with_suffix(".json.e24bbak")
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
    sock = socket.socket()
    sock.connect(("localhost", DAEMON_PORT))

    send_rpc(sock, "initialize", {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "e24b-runner", "version": "0.1"},
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

    resp = send_rpc(sock, "tools/call", {"name": "checkpoint", "arguments": {}})
    print(f"    {get_tool_text(resp)}")
    resp = send_rpc(sock, "tools/call", {"name": "status", "arguments": {}})
    print(f"    Graph: {get_tool_text(resp)}")
    sock.close()

    time.sleep(1)
    verify_sock = socket.socket()
    verify_sock.connect(("localhost", DAEMON_PORT))
    send_rpc(verify_sock, "initialize", {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "e24b-verify", "version": "0.1"},
    })
    vr = send_rpc(verify_sock, "tools/call", {
        "name": "query",
        "arguments": {"body": "(current-triple (? e) py-form-kind (? kind))"},
    })
    vt = get_tool_text(vr)
    vcount = sum(1 for l in vt.strip().split("\n") if "?" in l) if vt else 0
    print(f"    Verify: {vcount} entities visible")
    verify_sock.close()


# ════════════════════════════════════════════════════════════════════
# Code extraction
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
    return text.strip()


# ════════════════════════════════════════════════════════════════════
# Agent launching — CNF condition
# ════════════════════════════════════════════════════════════════════

FACADE_TOOL_NAMES = [
    "discover_lifecycle", "discover_all", "discover",
    "dependencies", "verify_references",
]


def write_mcp_config():
    facade_py = str(SCRIPT_DIR / "facade-tools.py")
    config = {
        "mcpServers": {
            "cnf-facade": {
                "command": sys.executable,
                "args": [facade_py, str(DAEMON_PORT)],
            }
        }
    }
    config_path = SCRIPT_DIR / "mcp-config.json"
    config_path.write_text(json.dumps(config, indent=2))
    return str(config_path)


def launch_cnf_agent(agent_spec, mcp_config_path):
    prompt = agent_spec["prompt"].format(
        models=MODELS_PY, core=CORE_PY, discovery_instruction=CNF_DISCOVERY)
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
                    "error": f"No code extracted ({len(output_text)} chars)"}
    except subprocess.TimeoutExpired:
        return {"name": name, "code": None, "elapsed": time.monotonic() - start,
                "raw_output": "", "error": "timeout"}
    except Exception as e:
        return {"name": name, "code": None, "elapsed": time.monotonic() - start,
                "raw_output": "", "error": str(e)}


# ════════════════════════════════════════════════════════════════════
# Agent launching — file condition
# ════════════════════════════════════════════════════════════════════

def setup_worktree(agent_name):
    """Create a temp directory with the full codebase for a file-based agent."""
    wt = Path(tempfile.mkdtemp(prefix=f"e24b-{agent_name}-"))
    for f in ["models.py", "core.py", "workflow.py"]:
        shutil.copy2(SCRIPT_DIR / "codebase" / f, wt / f)
    return wt


def launch_file_agent(agent_spec):
    prompt = agent_spec["prompt"].format(
        models=MODELS_PY, core=CORE_PY, discovery_instruction=FILE_DISCOVERY)
    name = agent_spec["name"]
    wt = setup_worktree(name)

    start = time.monotonic()
    try:
        cmd = ["claude", "-p", "--model", MODEL,
               "--output-format", "json",
               "--add-dir", str(wt)]
        result = subprocess.run(
            cmd, input=prompt, capture_output=True, text=True, timeout=TIMEOUT,
        )
        elapsed = time.monotonic() - start
        output_text = result.stdout or ""
        agent_result = _parse_agent_output(output_text)
        code = extract_code(agent_result)

        # Also check if agent wrote the file directly
        module_path = wt / agent_spec["module"]
        if not code and module_path.exists():
            code = module_path.read_text()

        if code:
            return {"name": name, "code": code, "elapsed": elapsed,
                    "raw_output": output_text, "error": None,
                    "worktree": str(wt)}
        else:
            return {"name": name, "code": None, "elapsed": elapsed,
                    "raw_output": output_text,
                    "error": f"No code extracted ({len(output_text)} chars)",
                    "worktree": str(wt)}
    except subprocess.TimeoutExpired:
        return {"name": name, "code": None, "elapsed": time.monotonic() - start,
                "raw_output": "", "error": "timeout", "worktree": str(wt)}
    except Exception as e:
        return {"name": name, "code": None, "elapsed": time.monotonic() - start,
                "raw_output": "", "error": str(e), "worktree": str(wt)}


def launch_repair_agent(workspace, test_output):
    """Launch a repair agent to fix test failures."""
    files = {}
    for f in ["notifications.py", "analytics.py", "permissions.py"]:
        p = workspace / f
        if p.exists():
            files[f] = p.read_text()
    workflow_src = (SCRIPT_DIR / "codebase" / "workflow.py").read_text()

    prompt = f"""\
Fix the failing tests in this ClaimDesk app. The test output is:

{test_output}

Here are the current source files:

<workflow.py>
{workflow_src}
</workflow.py>

<models.py>
{MODELS_PY}
</models.py>

<core.py>
{CORE_PY}
</core.py>
"""
    for fname, content in files.items():
        prompt += f"\n<{fname}>\n{content}\n</{fname}>\n"

    prompt += """
Fix the failing modules. For each file that needs changes, output:
--- filename.py ---
<complete corrected source>

Output ONLY the corrected files with the --- markers."""

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

        # Parse --- filename.py --- sections
        repairs = {}
        current_file = None
        current_lines = []
        for line in agent_result.split("\n"):
            m = re.match(r'^---\s*(\S+\.py)\s*---', line)
            if m:
                if current_file and current_lines:
                    repairs[current_file] = "\n".join(current_lines).strip()
                current_file = m.group(1)
                current_lines = []
            elif current_file:
                if line.strip() == "```python" or line.strip() == "```":
                    continue
                current_lines.append(line)
        if current_file and current_lines:
            repairs[current_file] = "\n".join(current_lines).strip()

        # Fallback: try extracting single code block
        if not repairs:
            code = extract_code(agent_result)
            if code:
                repairs["unknown"] = code

        return {"repairs": repairs, "elapsed": elapsed, "raw_output": output_text}
    except Exception as e:
        return {"repairs": {}, "elapsed": time.monotonic() - start, "error": str(e)}


def _parse_agent_output(raw):
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return data.get("result", data.get("content", raw))
        return raw
    except (json.JSONDecodeError, TypeError):
        return raw


# ════════════════════════════════════════════════════════════════════
# Test running
# ════════════════════════════════════════════════════════════════════

def assemble_workspace(agent_results):
    ws = Path(tempfile.mkdtemp(prefix="e24b-ws-"))
    (ws / "models.py").write_text(MODELS_PY)
    (ws / "core.py").write_text(CORE_PY)
    (ws / "workflow.py").write_text(WORKFLOW_PY)
    (ws / "test_integration.py").write_text(INTEGRATION_TESTS)
    for r in agent_results:
        if r["code"]:
            (ws / r["module"]).write_text(r["code"])
    return ws


def run_tests(workspace):
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

    if not results:
        for line in out.strip().splitlines():
            line = line.strip()
            if line.startswith("FAIL:"):
                test_name = line.split(":")[1].strip().split(":")[0].strip()
                results[test_name] = "fail"
            elif line.startswith("ERROR:"):
                test_name = line.split(":")[1].strip().split(":")[0].strip()
                results[test_name] = "error"

    all_tests = [f"test_{i:02d}" for i in range(1, NUM_TESTS + 1)]
    for t in all_tests:
        found = any(t in k for k in results)
        if not found:
            results[t] = "pass"

    return results, p, f, e, out


# ════════════════════════════════════════════════════════════════════
# Scoring
# ════════════════════════════════════════════════════════════════════

def extract_run_metrics(raw_output):
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


def check_code_quality(code):
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
# Condition runners
# ════════════════════════════════════════════════════════════════════

def run_cnf_condition():
    w = 72
    print(f"\n{'=' * w}")
    print(f"  E24b: cnf")
    print(f"{'=' * w}")

    mcp_config_path = write_mcp_config()
    print(f"\n  Launching {len(AGENTS)} agents in parallel...", flush=True)
    build_start = time.monotonic()

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(AGENTS)) as pool:
        futures = {
            pool.submit(launch_cnf_agent, agent, mcp_config_path): agent
            for agent in AGENTS
        }
        results = []
        for future in concurrent.futures.as_completed(futures):
            r = future.result()
            agent = futures[future]
            r["module"] = agent["module"]
            status = "ok" if r["code"] else f"FAIL: {r['error']}"
            print(f"    {r['name']:15s} {r['elapsed']:6.1f}s  {status}", flush=True)
            results.append(r)

    build_time = time.monotonic() - build_start
    return _finish_condition("cnf", results, build_time, repair_rounds=0)


def run_file_condition():
    w = 72
    print(f"\n{'=' * w}")
    print(f"  E24b: file")
    print(f"{'=' * w}")

    print(f"\n  Launching {len(AGENTS)} agents in parallel...", flush=True)
    build_start = time.monotonic()

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(AGENTS)) as pool:
        futures = {
            pool.submit(launch_file_agent, agent): agent
            for agent in AGENTS
        }
        results = []
        for future in concurrent.futures.as_completed(futures):
            r = future.result()
            agent = futures[future]
            r["module"] = agent["module"]
            status = "ok" if r["code"] else f"FAIL: {r['error']}"
            print(f"    {r['name']:15s} {r['elapsed']:6.1f}s  {status}", flush=True)
            results.append(r)

    build_time = time.monotonic() - build_start

    # First pass
    out_dir = SCRIPT_DIR / "file"
    out_dir.mkdir(exist_ok=True)
    for r in results:
        if r["code"]:
            (out_dir / r["module"]).write_text(r["code"])
        if r.get("raw_output"):
            (out_dir / f"{r['name']}-output.txt").write_text(r["raw_output"])

    ws = assemble_workspace(results)
    first_pass_results, p, f, e, test_out = run_tests(ws)

    first_pass_info_gap = 0
    for test_name in INFO_GAP_TESTS:
        matched = [k for k in first_pass_results if test_name in k]
        for m in matched:
            if first_pass_results[m] != "pass":
                first_pass_info_gap += 1
        if not matched:
            first_pass_info_gap += 1

    repair_rounds = 0
    if f > 0 or e > 0:
        print(f"\n  First pass: {p} passed, {f} failed, {e} errors"
              f"  (info-gap: {first_pass_info_gap}/8)")
        for tn, st in sorted(first_pass_results.items()):
            if st != "pass":
                ig = " [INFO-GAP]" if any(ig in tn for ig in INFO_GAP_TESTS) else ""
                print(f"    {st.upper()}: {tn}{ig}")
        print(f"  Launching repair agent...", flush=True)
        repair = launch_repair_agent(ws, test_out)
        repair_rounds = 1

        if repair["repairs"]:
            for fname, code in repair["repairs"].items():
                if fname in ("notifications.py", "analytics.py", "permissions.py"):
                    (ws / fname).write_text(code)
                    for r in results:
                        if r["module"] == fname:
                            r["code"] = code
            test_results, p, f, e, test_out = run_tests(ws)
            print(f"  After repair: {p} passed, {f} failed, {e} errors")

    result = _finish_condition("file", results, build_time, repair_rounds)
    result["first_pass_info_gap"] = first_pass_info_gap
    result["first_pass_tests"] = first_pass_results
    return result


def _finish_condition(condition, results, build_time, repair_rounds):
    out_dir = SCRIPT_DIR / condition
    out_dir.mkdir(exist_ok=True)
    for r in results:
        if r["code"]:
            (out_dir / r["module"]).write_text(r["code"])
        if r.get("raw_output"):
            (out_dir / f"{r['name']}-output.txt").write_text(r["raw_output"])

    ws = assemble_workspace(results)
    test_results, p, f, e, test_out = run_tests(ws)
    print(f"  Tests: {p} passed, {f} failed, {e} errors")

    info_gap_bugs = 0
    for test_name in INFO_GAP_TESTS:
        matched = [k for k in test_results if test_name in k]
        for m in matched:
            if test_results[m] != "pass":
                info_gap_bugs += 1
        if not matched:
            info_gap_bugs += 1

    for test_name, status in sorted(test_results.items()):
        marker = " [INFO-GAP]" if any(ig in test_name for ig in INFO_GAP_TESTS) else ""
        if status != "pass":
            print(f"    {status.upper()}: {test_name}{marker}")

    agent_details = {}
    for r in results:
        code_quality = check_code_quality(r.get("code"))
        run_metrics = extract_run_metrics(r.get("raw_output", ""))
        agent_details[r["name"]] = {
            "elapsed": round(r["elapsed"], 1),
            "code_quality": code_quality,
            "turns": run_metrics["turns"],
            "cost": run_metrics["cost"],
            "error": r.get("error"),
        }
        print(f"\n  {r['name']}:")
        print(f"    Turns: {run_metrics['turns']}  Cost: ${run_metrics['cost']}")
        for k, v in code_quality.items():
            if k != "has_code":
                print(f"    {k}: {v}")

    return {
        "condition": condition,
        "build_time": round(build_time, 1),
        "agents": agent_details,
        "tests": test_results,
        "info_gap_total": f"{info_gap_bugs}/8",
        "info_gap_bugs": info_gap_bugs,
        "repair_rounds": repair_rounds,
        "workspace": str(ws),
    }


# ════════════════════════════════════════════════════════════════════
# Aggregation
# ════════════════════════════════════════════════════════════════════

def aggregate_multi(all_runs, condition):
    n = len(all_runs)
    w = 72
    print(f"\n{'=' * w}")
    print(f"  E24b-multi: {condition} — {n} runs")
    print(f"{'=' * w}")

    for agent_name in ["notifications", "analytics", "permissions"]:
        runs_with = [r for r in all_runs if agent_name in r["agents"]]
        if not runs_with:
            continue
        na = len(runs_with)
        cq_keys = ["imports_workflow", "knows_archived", "knows_on_hold",
                    "uses_is_active", "uses_all_statuses", "hardcoded_statuses"]
        print(f"\n  {agent_name} ({na} runs):")
        for k in cq_keys:
            count = sum(1 for r in runs_with
                        if r["agents"][agent_name].get("code_quality", {}).get(k))
            print(f"    {k:25s} {count}/{na}")
        turns = [r["agents"][agent_name].get("turns", 0) for r in runs_with]
        costs = [r["agents"][agent_name].get("cost", 0) for r in runs_with]
        print(f"    {'mean turns':25s} {sum(turns)/na:.1f}")
        print(f"    {'mean cost':25s} ${sum(costs)/na:.4f}")

    all_bugs = [r["info_gap_bugs"] for r in all_runs]
    repairs = [r["repair_rounds"] for r in all_runs]
    total_opp = n * 8
    print(f"\n  AGGREGATE:")
    print(f"    Runs:               {n}")
    print(f"    Info-gap bugs:      {sum(all_bugs)}/{total_opp}"
          f" ({sum(all_bugs)/total_opp:.0%} failure rate)")
    print(f"    Per-run bugs:       {all_bugs}")
    print(f"    Repair rounds:      {repairs}")
    total_cost = sum(
        sum(r["agents"][a].get("cost", 0) for a in r["agents"])
        for r in all_runs)
    print(f"    Total cost:         ${total_cost:.2f}")
    print(f"    Mean cost/run:      ${total_cost/n:.4f}")


# ════════════════════════════════════════════════════════════════════
# Main
# ════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="E24b: Concurrent Facade Agents")
    parser.add_argument("--condition", default="cnf",
                        choices=["cnf", "file"],
                        help="Which condition to run (default: cnf)")
    parser.add_argument("--runs", type=int, default=1,
                        help="Number of runs (default: 1)")
    args = parser.parse_args()

    condition = args.condition
    num_runs = args.runs

    print(f"\nE24b: Concurrent Facade Agents")
    print(f"  3 agents (notifications, analytics, permissions)")
    print(f"  Condition: {condition}")
    print(f"  Runs: {num_runs}")
    print(f"  Info-gap tests: 8")

    daemon_proc = None
    backup = None
    all_runs = []

    try:
        if condition == "cnf":
            print("\n  Starting CNF daemon...", flush=True)
            daemon_proc, backup = start_daemon()
            print("  Parsing base codebase into graph...", flush=True)
            init_graph()

        for run_idx in range(num_runs):
            if num_runs > 1:
                print(f"\n  ──── Run {run_idx + 1}/{num_runs} ────")

            out_dir = SCRIPT_DIR / condition
            if out_dir.exists():
                shutil.rmtree(out_dir)

            if condition == "cnf":
                result = run_cnf_condition()
            else:
                result = run_file_condition()

            all_runs.append(result)

    finally:
        if daemon_proc:
            stop_daemon(daemon_proc, backup)

    if num_runs > 1:
        aggregate_multi(all_runs, condition)

    results_path = SCRIPT_DIR / "results.json"
    output = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "experiment": "E24b",
        "condition": condition,
        "num_runs": num_runs,
        "runs": [{
            "agents": r["agents"],
            "tests": r["tests"],
            "info_gap_total": r["info_gap_total"],
            "info_gap_bugs": r["info_gap_bugs"],
            "repair_rounds": r["repair_rounds"],
            "build_time": r["build_time"],
            "first_pass_info_gap": r.get("first_pass_info_gap"),
        } for r in all_runs],
    }
    if num_runs > 1:
        all_bugs = [r["info_gap_bugs"] for r in all_runs]
        first_pass_bugs = [r.get("first_pass_info_gap", r["info_gap_bugs"])
                           for r in all_runs]
        output["aggregate"] = {
            "total_bugs": sum(all_bugs),
            "total_opportunities": num_runs * 8,
            "failure_rate": round(sum(all_bugs) / (num_runs * 8), 3),
            "per_run_bugs": all_bugs,
            "first_pass_bugs": first_pass_bugs,
            "first_pass_failure_rate": round(
                sum(first_pass_bugs) / (num_runs * 8), 3),
        }
    results_path.write_text(json.dumps(output, indent=2, default=str))
    print(f"\n  Results saved to {results_path}")


if __name__ == "__main__":
    main()

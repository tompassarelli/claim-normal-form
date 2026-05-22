#!/usr/bin/env python3
"""E23: Concurrent Graph-Native Agents

51 functions. Two agents modify the same program concurrently.

Agent A (safety): add safe-div, guard division-heavy functions, verify no crashes.
Agent B (refactor): rename helper → utility, verify all call sites, query history.

The overlap zone: calc-ratio, calc-average, calc-share, calc-rate, calc-pct
call helper AND use raw division. Both agents must touch these functions.

Graph condition: both agents share one CNF daemon via MVCC.
Text condition:  both agents get separate copies, merge afterward.

Hypothesis: the shared claim graph reduces coordination failures by making
semantic identity, dependency cones, transaction history, and runtime outcomes
queryable to each agent.

Usage:
    python runner.py              # Run both conditions
    python runner.py --graph-only # Graph condition only
    python runner.py --text-only  # Text condition only
"""

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
TIMEOUT = 420

STARTING_PROGRAM = (SCRIPT_DIR / "program.cnf").read_text()

# ════════════════════════════════════════════════════════════════════
# Ground truth
# ════════════════════════════════════════════════════════════════════

DIVISION_FUNCTIONS = [
    "ratio", "share", "split-even", "average", "percent",
]

OVERLAP_FUNCTIONS = [
    "calc-ratio", "calc-average", "calc-share", "calc-rate", "calc-pct",
]

HELPER_CALLERS = [
    "compute-a", "compute-b", "compute-c", "compute-d", "compute-e",
    "mixed-a",
]

ALL_HELPER_CALL_SITES = HELPER_CALLERS + OVERLAP_FUNCTIONS + ["mixed-a"]

TRAP_NAMES = ["helper-rate", "tax-helper"]
PARAM_TRAPS = ["process-a", "process-b", "process-c"]


# ════════════════════════════════════════════════════════════════════
# Task prompts
# ════════════════════════════════════════════════════════════════════

SHARED_CONTEXT = """\
You are working on a 51-function program in a tiny functional language.
The language supports: defn, +, -, *, /, =, if, and function calls.

IMPORTANT: Another agent is working on the SAME program concurrently.
- You may see changes that you did not make. This is expected.
- Query the current state before making assumptions.
- Check dependencies and transaction history to understand what changed.
"""

AGENT_A_TASK = SHARED_CONTEXT + """
YOUR TASK: Make division safe across the program.

The program has functions that crash when their divisor is 0:
- ratio(a, b) = (/ a b)
- share(total, parts) = (/ total parts)
- split-even(total, count) = (/ total count)
- percent(value, whole) = (/ (* value 100) whole)
- average(a, b) = (/ (+ a b) 2) — safe (divisor is constant 2)

And OVERLAP functions that also use raw division:
- calc-ratio(a, b) = (/ (helper a b) b)
- calc-average(a, b) = (/ (helper a b) 2) — safe
- calc-share(total, parts) = (/ (helper total parts) parts)
- calc-rate(base, hours) = (/ (helper base hours) hours)
- calc-pct(value, total) = (/ (* (helper value total) 100) total)

Complete these steps IN ORDER:

1. DEMONSTRATE CRASH: Evaluate ratio(10, 0). It should error with division by zero.

2. ADD SAFE-DIV: Add a new function:
   (defn safe-div [x y] (if (= y 0) 0 (/ x y)))

3. GUARD UNSAFE FUNCTIONS: Modify these functions to use safe-div:
   - ratio: (defn ratio [a b] (safe-div a b))
   - share: (defn share [total parts] (safe-div total parts))
   - split-even: (defn split-even [total count] (safe-div total count))
   - percent: (defn percent [value whole] (safe-div (* value 100) whole))
   - calc-ratio: guard the division (check current call — it may reference
     a renamed function if the other agent has already renamed it)
   - calc-share: same
   - calc-rate: same
   - calc-pct: same

   IMPORTANT: Before modifying overlap functions (calc-*), QUERY their current
   body or render them first. The other agent may have renamed "helper" to
   something else. Use whatever name the function currently has.

4. VERIFY SAFETY: Evaluate ratio(10, 0), share(100, 0), calc-ratio(5, 0).
   All should return 0 instead of crashing.

5. VERIFY NON-REGRESSION: Evaluate ratio(10, 2) = 5, share(100, 4) = 25,
   calc-ratio(3, 4) with b≠0 should still work correctly.

6. QUERY AFFECTED: List all functions that depend on the functions you modified.

7. RENDER: Show the full rendered program to confirm coherence.

For each step, report: what you did, result, pass/fail.
"""

AGENT_B_TASK = SHARED_CONTEXT + """
YOUR TASK: Rename the function "helper" to "utility" and verify correctness.

The program has a function named "helper" that is called by many other functions.
Other functions contain "helper" in their names (helper-rate, tax-helper) — do NOT
rename those. Parameters named "helper" in process-a/b/c — do NOT rename those.

Complete these steps IN ORDER:

1. BASELINE: Evaluate helper(3, 4) = 7, compute-a(3, 4) = 14.

2. BREAK AND RECORD: Modify helper to cause a crash:
   (defn helper [x y] (/ x y))
   Evaluate compute-a(3, 0). Record the error.

3. RESTORE: Fix helper back to (defn helper [x y] (+ x y)).
   Verify compute-a(3, 4) = 14.

4. RENAME: Rename "helper" to "utility".
   This should update all call sites (compute-a through compute-e, calc-ratio
   through calc-pct, mixed-a) without touching helper-rate, tax-helper, or
   parameter names.

5. VERIFY RENAME:
   a) Evaluate utility(3, 4) = 7
   b) Evaluate compute-a(3, 4) = 14
   c) Confirm helper-rate still exists (not "utility-rate")
   d) Confirm process-a still has parameter "helper"

6. QUERY DEPENDENCIES: Which functions depend on utility?

7. ERROR HISTORY: Is the failed evaluation from step 2 still queryable?
   Report its status and reason.

   IMPORTANT: Before rendering, be aware that the other agent may have modified
   some function bodies (adding safe-div guards). This is expected.

8. RENDER: Show the full rendered program. It should be coherent even if
   some functions were modified by the other agent.

For each step, report: what you did, result, pass/fail.
"""


# ════════════════════════════════════════════════════════════════════
# Graph condition: shared daemon
# ════════════════════════════════════════════════════════════════════

GRAPH_AGENT_A_PROMPT = AGENT_A_TASK + """
TOOLS: You have MCP tools connected to a SHARED CNF claim graph server.
The program is already loaded — do NOT call reset or parse_program.

Another agent is connected to the SAME graph simultaneously. Your changes
are visible to them in real time, and theirs to you.

First, call set_agent with name "safety-agent" to identify your operations.
Then call status to confirm the graph is loaded.

Key tools:
- set_agent: Identify yourself (call first!)
- evaluate: Run function by name with arguments
- query: Datalog queries (e.g. fn-depends-on)
- add_function: Add a new function to the existing graph
- modify_function: Change a function's body
- render: Render function or full program to text
- inspect: Examine entity claims
- status: Check current graph state
- tx_log: View transaction history (shows both agents' operations)
"""

GRAPH_AGENT_B_PROMPT = AGENT_B_TASK + """
TOOLS: You have MCP tools connected to a SHARED CNF claim graph server.
The program is already loaded — do NOT call reset or parse_program.

Another agent is connected to the SAME graph simultaneously. Your changes
are visible to them in real time, and theirs to you.

First, call set_agent with name "refactor-agent" to identify your operations.
Then call status to confirm the graph is loaded.

Key tools:
- set_agent: Identify yourself (call first!)
- evaluate: Run function by name with arguments
- query: Datalog queries (e.g. fn-depends-on)
- rename: Rename an entity (call sites update automatically)
- modify_function: Change a function's body
- render: Render function or full program to text
- inspect: Examine entity claims
- status: Check current graph state
- tx_log: View transaction history (shows both agents' operations)

For rename: use the rename tool. It operates on the entity, not string matching.
Call sites update automatically. helper-rate, tax-helper, and parameter names
are different entities and won't be affected.
"""


# ════════════════════════════════════════════════════════════════════
# Text condition: separate copies
# ════════════════════════════════════════════════════════════════════

TEXT_AGENT_A_PROMPT = AGENT_A_TASK + """
TOOLS: You have a working directory with:
- program.cnf — the source file
- eval-helper.rkt — evaluation tool:
    racket eval-helper.rkt eval program.cnf <fn-name> <arg1> <arg2> ...
    racket eval-helper.rkt deps program.cnf
    racket eval-helper.rkt render program.cnf

The eval-helper re-parses fresh each invocation. No cross-run state.

Edit program.cnf directly to add safe-div and modify functions.

NOTE: The other agent is editing their OWN COPY of program.cnf.
Your changes will be merged with theirs afterward. Try to make clean,
non-overlapping edits where possible. If you must edit overlap functions
(calc-*), make your changes clearly.

Starting program:
```
""" + STARTING_PROGRAM + """
```
"""

TEXT_AGENT_B_PROMPT = AGENT_B_TASK + """
TOOLS: You have a working directory with:
- program.cnf — the source file
- eval-helper.rkt — evaluation tool:
    racket eval-helper.rkt eval program.cnf <fn-name> <arg1> <arg2> ...
    racket eval-helper.rkt deps program.cnf
    racket eval-helper.rkt render program.cnf

The eval-helper re-parses fresh each invocation. No cross-run state.

For rename: edit program.cnf. Be VERY careful — "helper" appears as a
substring in other function names and as parameter names. A naive
find-and-replace will break the program.

For error history: the eval-helper has no persistent state. Report what
you observed from the step 2 evaluation.

NOTE: The other agent is editing their OWN COPY of program.cnf.
Your changes will be merged with theirs afterward.

Starting program:
```
""" + STARTING_PROGRAM + """
```
"""


REPAIR_AGENT_PROMPT = """\
You are a merge-repair agent. Two agents edited a program concurrently.
Their changes were merged, but {conflicts} functions have conflicts.

WHAT EACH AGENT DID:
- Agent A (safety): Added a safe-div function and replaced raw division
  with safe-div calls in 8 functions. safe-div returns 0 when divisor is 0.
- Agent B (refactor): Renamed the function "helper" to "utility". All call
  sites were updated. "helper-rate", "tax-helper", and parameters named
  "helper" in process-a/b/c were NOT renamed.

THE CONFLICT: In the overlap functions, Agent A wrapped division with
safe-div but still references "helper". Agent B renamed "helper" to
"utility" but didn't add safe-div. The correct resolution combines both:
use safe-div AND use "utility" as the function name.

Also check: the definition of "utility" may be missing from the merge.
If so, add it: (defn utility [x y] (+ x y))

YOUR TASK:
1. Read the conflicted program in program.cnf
2. Resolve ALL conflicts by combining both agents' changes
3. Fix any missing definitions
4. Write the corrected program.cnf
5. Verify with: racket eval-helper.rkt eval program.cnf ratio 10 0
   (should return 0, not crash)
6. Verify with: racket eval-helper.rkt eval program.cnf utility 3 4
   (should return 7)
7. Render: racket eval-helper.rkt render program.cnf
   (should be coherent, no conflicts, no comments)

Write ONLY the final corrected program to program.cnf. No conflict markers,
no comments.
"""


# ════════════════════════════════════════════════════════════════════
# Infrastructure
# ════════════════════════════════════════════════════════════════════

def wait_for_port(port, timeout=30):
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
    """Kill any existing process on the given port."""
    try:
        result = subprocess.run(
            ["ss", "-tlnp"], capture_output=True, text=True)
        for line in result.stdout.splitlines():
            if f":{port}" in line:
                import re as _re
                m = _re.search(r'pid=(\d+)', line)
                if m:
                    pid = int(m.group(1))
                    os.kill(pid, 9)
                    time.sleep(1)
    except Exception:
        pass


def start_daemon():
    kill_port(DAEMON_PORT)

    checkpoint_path = Path.home() / ".cnf" / "checkpoint.json"
    backup = None
    if checkpoint_path.exists():
        backup = checkpoint_path.with_suffix(".json.e23bak")
        shutil.copy2(checkpoint_path, backup)
        checkpoint_path.unlink()

    proc = subprocess.Popen(
        ["racket", str(SERVER_RKT), "--daemon", str(DAEMON_PORT)],
        stderr=subprocess.PIPE, text=True,
    )
    if not wait_for_port(DAEMON_PORT, timeout=30):
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
    """Parse the program into the daemon. Returns (status, fn_ids).

    fn_ids is a list of entity ID strings extracted from parse_program output.
    """
    sock = socket.socket()
    sock.connect(("localhost", DAEMON_PORT))

    send_rpc(sock, "initialize", {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "e23-runner", "version": "0.1"},
    })

    send_rpc(sock, "tools/call", {"name": "reset", "arguments": {}})

    resp = send_rpc(sock, "tools/call", {
        "name": "parse_program",
        "arguments": {"source": STARTING_PROGRAM, "language": "cnf"},
    })
    text = get_tool_text(resp)
    print(f"    Parsed: {text.split(chr(10))[0]}")

    # Extract function entity IDs from parse output (lines like "222: helper (defn)")
    fn_ids = []
    for line in text.split("\n"):
        m = re.match(r'\s*(\d+):\s+\S+\s+\(defn\)', line)
        if m:
            fn_ids.append(m.group(1))
    print(f"    Functions: {len(fn_ids)} entity IDs captured")

    resp = send_rpc(sock, "tools/call", {"name": "status", "arguments": {}})
    status = get_tool_text(resp)
    print(f"    Graph: {status}")

    sock.close()
    return status, fn_ids


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


KEY_FUNCTIONS = [
    "ratio", "share", "split-even", "percent", "average",
    "calc-ratio", "calc-share", "calc-rate", "calc-pct", "calc-average",
    "compute-a", "compute-b",
    "helper-rate", "tax-helper",
    "mixed-a",
    "safe-div", "utility", "helper",
]


def verify_daemon_state(fn_ids, label="verifier"):
    """Open a fresh connection and query status, tx_log, and rendered program.

    fn_ids: entity IDs from init_graph (known function entities).
    Returns dict with raw results. This is the MVCC witness — if this
    connection sees stale state, the experiment is not certified.
    """
    sock = socket.socket()
    sock.connect(("localhost", DAEMON_PORT))

    send_rpc(sock, "initialize", {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": f"e23-{label}", "version": "0.1"},
    })

    # 1. Status: object count, claim count, tx count
    resp = send_rpc(sock, "tools/call", {"name": "status", "arguments": {}})
    status_text = get_tool_text(resp)

    # 2. Tx log (with high limit to see all transactions)
    resp = send_rpc(sock, "tools/call", {
        "name": "tx_log",
        "arguments": {"since_seq": 0, "limit": 9999},
    })
    tx_log_text = get_tool_text(resp)

    # 3. Render using known function IDs
    rendered = ""
    if fn_ids:
        resp = send_rpc(sock, "tools/call", {
            "name": "render",
            "arguments": {"ids": fn_ids},
        })
        rendered = get_tool_text(resp)

    sock.close()
    return {
        "status": status_text,
        "tx_log": tx_log_text,
        "rendered": rendered,
    }


# ════════════════════════════════════════════════════════════════════
# Agent launchers
# ════════════════════════════════════════════════════════════════════

def launch_graph_agent(name, prompt, mcp_config_path):
    print(f"    Launching graph agent: {name}")
    start = time.monotonic()
    try:
        result = subprocess.run(
            ["claude", "-p", "--model", MODEL,
             "--dangerously-skip-permissions",
             "--mcp-config", mcp_config_path],
            input=prompt,
            capture_output=True, text=True, timeout=TIMEOUT,
        )
        elapsed = time.monotonic() - start
        return {
            "name": name,
            "elapsed": elapsed,
            "transcript": result.stdout or "",
            "error": None if result.returncode == 0 else result.stderr[:500],
        }
    except subprocess.TimeoutExpired:
        return {
            "name": name,
            "elapsed": time.monotonic() - start,
            "transcript": "",
            "error": "timeout",
        }


def launch_text_agent(name, prompt, workspace, timeout=None):
    print(f"    Launching text agent: {name} (workspace: {workspace})")
    agent_timeout = timeout or TIMEOUT
    start = time.monotonic()
    try:
        result = subprocess.run(
            ["claude", "-p", "--model", MODEL,
             "--dangerously-skip-permissions"],
            input=prompt,
            capture_output=True, text=True, timeout=agent_timeout,
            cwd=str(workspace),
        )
        elapsed = time.monotonic() - start
        modified = ""
        prog_path = workspace / "program.cnf"
        if prog_path.exists():
            modified = prog_path.read_text()
        return {
            "name": name,
            "elapsed": elapsed,
            "transcript": result.stdout or "",
            "modified_program": modified,
            "error": None if result.returncode == 0 else result.stderr[:500],
        }
    except subprocess.TimeoutExpired:
        elapsed = time.monotonic() - start
        modified = ""
        prog_path = workspace / "program.cnf"
        if prog_path.exists():
            modified = prog_path.read_text()
        return {
            "name": name,
            "elapsed": elapsed,
            "transcript": "",
            "modified_program": modified,
            "error": "timeout",
        }


# ════════════════════════════════════════════════════════════════════
# Verification
# ════════════════════════════════════════════════════════════════════

def _extract_count(text, pattern):
    m = re.search(pattern, text)
    return int(m.group(1)) if m else None


def verify_merged_program(program_text):
    """Verify that both agents' changes are present in a merged program."""
    results = {}

    # Agent A checks: safe-div is used in guarded functions
    # Note: safe-div may be a new entity not in the original parse IDs,
    # so we check for usage rather than definition
    results["a_safe_div_used"] = "safe-div" in program_text

    for fn in ["ratio", "share", "split-even", "percent"]:
        body = _extract_fn_body(program_text, fn)
        results[f"a_guarded_{fn}"] = "safe-div" in body or "if" in body

    # Agent B checks: helper renamed to utility
    results["b_utility_exists"] = "(defn utility " in program_text
    results["b_helper_defn_gone"] = not bool(re.search(r'\(defn helper\s+\[', program_text))

    for name in TRAP_NAMES:
        results[f"b_preserved_{name}"] = name in program_text

    results["b_no_utility_rate"] = "utility-rate" not in program_text
    results["b_no_tax_utility"] = "tax-utility" not in program_text

    for fn in PARAM_TRAPS:
        pattern = rf'\(defn {re.escape(fn)} \[.*?helper.*?\]'
        match = re.search(pattern, program_text)
        if match:
            results[f"b_param_{fn}"] = "utility" not in match.group()
        else:
            results[f"b_param_{fn}"] = False

    return results


def _extract_fn_body(text, fn_name):
    """Extract function body using paren-depth counting."""
    start = text.find(f"(defn {fn_name} ")
    if start < 0:
        return ""
    depth = 0
    end = start
    for i in range(start, len(text)):
        if text[i] == '(':
            depth += 1
        elif text[i] == ')':
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    return text[start:end]


def verify_graph_transcripts(transcript_a, transcript_b):
    """Verify graph agents' transcripts for evidence of correct behavior."""
    results = {}
    ta = transcript_a.lower()
    tb = transcript_b.lower()

    # Agent A checks
    results["a_safe_div_added"] = "safe-div" in ta or "safe_div" in ta
    results["a_crash_demonstrated"] = "division by zero" in ta
    results["a_ratio_guarded"] = ("safe-div" in ta and
                                  ("ratio" in ta or "guard" in ta or "modif" in ta))
    results["a_verified_safe"] = ("0" in ta and
                                  ("ratio(10, 0)" in ta or "ratio(10,0)" in ta
                                   or "no crash" in ta or "returns 0" in ta
                                   or "= 0" in ta))

    # Agent B checks
    results["b_baseline_7"] = "7" in tb and ("helper" in tb or "baseline" in tb)
    results["b_renamed"] = "utility" in tb
    results["b_error_recorded"] = "division by zero" in tb
    results["b_error_history"] = (("history" in tb or "run" in tb or "status" in tb)
                                  and "error" in tb)
    results["b_helper_rate_preserved"] = "helper-rate" in tb

    return results


def attempt_merge(program_a, program_b):
    """Attempt to merge two text agents' modified programs.

    Returns (merged_text, conflicts_count).
    Uses a simple function-level merge: for each function, take the version
    that differs from the original. If both differ, flag as conflict.
    """
    original_fns = _parse_functions(STARTING_PROGRAM)
    a_fns = _parse_functions(program_a)
    b_fns = _parse_functions(program_b)

    merged_parts = []
    conflicts = 0
    new_fns = set()

    # Collect functions added by A but not in original
    for name in a_fns:
        if name not in original_fns:
            new_fns.add(name)

    all_names = list(original_fns.keys())

    for name in all_names:
        orig = original_fns.get(name, "")
        a_ver = a_fns.get(name, "")
        b_ver = b_fns.get(name, "")

        a_changed = a_ver != orig
        b_changed = b_ver != orig

        if a_changed and b_changed:
            conflicts += 1
            merged_parts.append(f";; CONFLICT: {name}")
            merged_parts.append(f";; --- Agent A version ---")
            merged_parts.append(a_ver)
            merged_parts.append(f";; --- Agent B version ---")
            merged_parts.append(b_ver)
        elif a_changed:
            merged_parts.append(a_ver)
        elif b_changed:
            merged_parts.append(b_ver)
        else:
            merged_parts.append(orig)

    # Add new functions from A (e.g., safe-div)
    for name in sorted(new_fns):
        if name in a_fns:
            merged_parts.append(a_fns[name])

    return "\n\n".join(merged_parts), conflicts


def _parse_functions(text):
    """Parse program text into {name: full_defn_text} dict."""
    fns = {}
    i = 0
    while i < len(text):
        match = re.search(r'\(defn (\S+)\s+\[', text[i:])
        if not match:
            break
        start = i + match.start()
        name = match.group(1)
        depth = 0
        end = start
        for j in range(start, len(text)):
            if text[j] == '(':
                depth += 1
            elif text[j] == ')':
                depth -= 1
                if depth == 0:
                    end = j + 1
                    break
        fns[name] = text[start:end]
        i = end
    return fns


# ════════════════════════════════════════════════════════════════════
# Main runners
# ════════════════════════════════════════════════════════════════════

def run_graph_condition():
    """Run both graph agents on a shared daemon (MVCC).

    One daemon, one parsed program, two agents connecting via bridges.
    Both agents see each other's changes in real time through the
    shared claim graph.
    """
    print("\n  ── GRAPH CONDITION: shared daemon (MVCC) ──")

    daemon_proc, daemon_backup = start_daemon()
    try:
        print("  Parsing program into shared daemon...")
        _, fn_ids = init_graph()

        # PRE-CHECK: verifier sees parsed program before agents start
        print("  Pre-check: verifier connection sees parsed state...")
        pre = verify_daemon_state(fn_ids, "pre-check")
        pre_objects = _extract_count(pre["status"], r'Objects:\s*(\d+)')
        pre_txs = _extract_count(pre["status"], r'Transactions:\s*(\d+)')
        print(f"    Pre-check: {pre_objects} objects, {pre_txs} txs, {len(fn_ids)} functions")
        if not pre_objects or pre_objects < 2000:
            print(f"    ABORT: Pre-check sees only {pre_objects} objects (expected ~2474)")
            print(f"    Status: {pre['status']}")
            return None

        mcp_config_path = write_mcp_config()

        print("  Launching both agents concurrently...")
        start = time.monotonic()

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            future_a = pool.submit(
                launch_graph_agent, "safety-agent",
                GRAPH_AGENT_A_PROMPT, mcp_config_path)
            future_b = pool.submit(
                launch_graph_agent, "refactor-agent",
                GRAPH_AGENT_B_PROMPT, mcp_config_path)

            result_a = future_a.result()
            result_b = future_b.result()

        total_elapsed = time.monotonic() - start
        print(f"  Both agents done. Wall time: {total_elapsed:.1f}s")
        print(f"    Agent A (safety):  {result_a['elapsed']:.1f}s")
        print(f"    Agent B (refactor): {result_b['elapsed']:.1f}s")

        # POST-CHECK: fresh verifier connection sees agents' changes
        print("  Post-check: verifier connection sees final state...")
        post = verify_daemon_state(fn_ids, "post-check")
        post_objects = _extract_count(post["status"], r'Objects:\s*(\d+)')
        post_txs = _extract_count(post["status"], r'Transactions:\s*(\d+)')
        rendered = post["rendered"]
        tx_log = post["tx_log"]
        print(f"    Post-check: {post_objects} objects, {post_txs} txs")
        print(f"    Object delta: {(post_objects or 0) - (pre_objects or 0)}")
        print(f"    Tx delta: {(post_txs or 0) - (pre_txs or 0)}")

        (SCRIPT_DIR / "graph-rendered.cnf").write_text(rendered)
        (SCRIPT_DIR / "graph-tx-log.txt").write_text(tx_log)

        # Verify from transcripts
        verification = verify_graph_transcripts(
            result_a.get("transcript", ""),
            result_b.get("transcript", ""))

        # Verify from rendered program (the real witness)
        if rendered:
            rendered_checks = verify_merged_program(rendered)
            for k, v in rendered_checks.items():
                verification[f"rendered_{k}"] = v

        # MVCC witness: post-run state is richer than pre-run
        verification["mvcc_objects_grew"] = (
            post_objects is not None and pre_objects is not None
            and post_objects > pre_objects)
        verification["mvcc_txs_grew"] = (
            post_txs is not None and pre_txs is not None
            and post_txs > pre_txs)
        verification["mvcc_render_nonempty"] = bool(rendered and len(rendered) > 100)

        return {
            "condition": "graph",
            "total_elapsed": total_elapsed,
            "agent_a": {
                "elapsed": result_a["elapsed"],
                "error": result_a["error"],
            },
            "agent_b": {
                "elapsed": result_b["elapsed"],
                "error": result_b["error"],
            },
            "verification": verification,
            "conflicts": 0,
            "repair_rounds": 0,
            "transcripts": {
                "agent_a": result_a["transcript"],
                "agent_b": result_b["transcript"],
            },
            "rendered_program": rendered,
            "tx_log": tx_log,
            "pre_check": {
                "objects": pre_objects,
                "txs": pre_txs,
                "fn_count": len(fn_ids),
            },
            "post_check": {
                "objects": post_objects,
                "txs": post_txs,
            },
        }
    finally:
        stop_daemon(daemon_proc, daemon_backup)


def run_text_condition():
    print("\n  ── TEXT CONDITION: separate copies ──")

    ws_a = Path(tempfile.mkdtemp(prefix="e23-text-a-"))
    ws_b = Path(tempfile.mkdtemp(prefix="e23-text-b-"))

    for ws in [ws_a, ws_b]:
        shutil.copy(SCRIPT_DIR / "program.cnf", ws / "program.cnf")
        shutil.copy(SCRIPT_DIR / "eval-helper.rkt", ws / "eval-helper.rkt")

    print(f"  Workspaces: A={ws_a}, B={ws_b}")
    print("  Launching both agents concurrently...")
    start = time.monotonic()

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        future_a = pool.submit(
            launch_text_agent, "safety-agent",
            TEXT_AGENT_A_PROMPT, ws_a)
        future_b = pool.submit(
            launch_text_agent, "refactor-agent",
            TEXT_AGENT_B_PROMPT, ws_b)

        result_a = future_a.result()
        result_b = future_b.result()

    total_elapsed = time.monotonic() - start
    print(f"  Both agents done. Wall time: {total_elapsed:.1f}s")
    print(f"    Agent A (safety):  {result_a['elapsed']:.1f}s")
    print(f"    Agent B (refactor): {result_b['elapsed']:.1f}s")

    # Attempt merge
    merged, conflicts = attempt_merge(
        result_a.get("modified_program", ""),
        result_b.get("modified_program", ""),
    )
    print(f"  Merge: {conflicts} conflicts")

    verification = verify_merged_program(merged)

    result = {
        "condition": "text",
        "total_elapsed": total_elapsed,
        "agent_a": {
            "elapsed": result_a["elapsed"],
            "error": result_a["error"],
        },
        "agent_b": {
            "elapsed": result_b["elapsed"],
            "error": result_b["error"],
        },
        "merged_program": merged,
        "verification": verification,
        "conflicts": conflicts,
        "repair_rounds": 0,
        "transcripts": {
            "agent_a": result_a["transcript"],
            "agent_b": result_b["transcript"],
        },
    }

    if conflicts > 0 and "--no-repair" not in sys.argv:
        repair = run_text_repair(merged, conflicts)
        if repair:
            result["repair"] = repair
            result["repair_rounds"] = 1
            result["repaired_program"] = repair["repaired_program"]
            result["repair_verification"] = repair["verification"]
            result["total_with_repair"] = total_elapsed + repair["elapsed"]

    return result


def run_text_repair(merged_program, conflicts):
    """Launch a repair agent to resolve conflicts in the merged program."""
    print(f"\n  ── TEXT REPAIR: resolving {conflicts} conflicts ──")

    ws = Path(tempfile.mkdtemp(prefix="e23-text-repair-"))
    (ws / "program.cnf").write_text(merged_program)
    shutil.copy(SCRIPT_DIR / "eval-helper.rkt", ws / "eval-helper.rkt")

    prompt = REPAIR_AGENT_PROMPT.format(conflicts=conflicts)
    print(f"  Workspace: {ws}")

    repair_result = launch_text_agent(
        "repair-agent", prompt, ws, timeout=180)

    print(f"  Repair agent done. Time: {repair_result['elapsed']:.1f}s")

    repaired = repair_result.get("modified_program", "")
    if not repaired:
        print("  WARN: Repair agent produced no output")
        return None

    (SCRIPT_DIR / "text-repaired.cnf").write_text(repaired)

    verification = verify_merged_program(repaired)

    v_pass = sum(1 for v in verification.values() if v)
    v_total = len(verification)
    print(f"  Repair verification: {v_pass}/{v_total}")
    for k, v in verification.items():
        if not v:
            print(f"    FAIL: {k}")

    return {
        "elapsed": repair_result["elapsed"],
        "error": repair_result["error"],
        "repaired_program": repaired,
        "verification": verification,
        "transcript": repair_result["transcript"],
    }


def print_results(graph_result, text_result):
    w = 76
    print()
    print("═" * w)
    print("  E23b: CONCURRENT AGENTS (SHARED DAEMON) — RESULTS")
    print("═" * w)

    for label, result in [("GRAPH", graph_result), ("TEXT", text_result)]:
        if not result:
            continue
        print(f"\n  ── {label} CONDITION ──")
        print(f"  Wall time:      {result['total_elapsed']:.1f}s")
        print(f"  Agent A:        {result['agent_a']['elapsed']:.1f}s"
              f"  {'error: ' + str(result['agent_a']['error']) if result['agent_a']['error'] else 'OK'}")
        print(f"  Agent B:        {result['agent_b']['elapsed']:.1f}s"
              f"  {'error: ' + str(result['agent_b']['error']) if result['agent_b']['error'] else 'OK'}")
        print(f"  Conflicts:      {result['conflicts']}")
        print(f"  Repair rounds:  {result['repair_rounds']}")

        v = result["verification"]
        a_checks = sum(1 for k, val in v.items()
                       if k.startswith("a_") and val)
        a_total = sum(1 for k in v if k.startswith("a_"))

        b_checks = sum(1 for k, val in v.items()
                       if k.startswith("b_") and val)
        b_total = sum(1 for k in v if k.startswith("b_"))

        other_checks = sum(1 for k, val in v.items()
                           if not k.startswith("a_") and not k.startswith("b_") and val)
        other_total = sum(1 for k in v
                          if not k.startswith("a_") and not k.startswith("b_"))

        print(f"\n  Verification:")
        print(f"    Agent A (safety):    {a_checks}/{a_total}")
        print(f"    Agent B (refactor):  {b_checks}/{b_total}")
        if other_total > 0:
            print(f"    Other checks:        {other_checks}/{other_total}")

        for k, val in sorted(v.items()):
            if not val:
                print(f"    FAIL: {k}")

        if result.get("repair"):
            rep = result["repair"]
            rv = rep["verification"]
            r_pass = sum(1 for val in rv.values() if val)
            print(f"\n  Repair:")
            print(f"    Time:           {rep['elapsed']:.1f}s")
            print(f"    Total (initial + repair): {result['total_with_repair']:.1f}s")
            print(f"    Verification:   {r_pass}/{len(rv)}")
            for k, val in sorted(rv.items()):
                if not val:
                    print(f"    FAIL: {k}")

    # Coordination comparison
    if graph_result and text_result:
        print(f"\n  ── COMPARISON ──")
        print(f"  {'':30} {'Graph':>10} {'Text':>10}")
        print(f"  {'Wall time':30} {graph_result['total_elapsed']:>9.1f}s {text_result['total_elapsed']:>9.1f}s")
        print(f"  {'Conflicts':30} {graph_result['conflicts']:>10} {text_result['conflicts']:>10}")
        print(f"  {'Repair rounds':30} {graph_result['repair_rounds']:>10} {text_result['repair_rounds']:>10}")

        gv = graph_result['verification']
        tv = text_result['verification']
        g_pass = sum(1 for v in gv.values() if v)
        t_pass = sum(1 for v in tv.values() if v)
        print(f"  {'Verification checks passed':30} {g_pass}/{len(gv):>5} {t_pass}/{len(tv):>5}")

    print()


def main():
    w = 76
    print("═" * w)
    print("  E23b: Concurrent Agents — Shared Daemon")
    print()
    print(f"  51 functions, model: {MODEL}")
    print("  Agent A: make division safe")
    print("  Agent B: rename helper → utility")
    print("  Overlap: 5 functions touched by both agents")
    print("═" * w)

    graph_result = None
    text_result = None

    if "--repair-only" in sys.argv:
        merged_path = SCRIPT_DIR / "text-merged.cnf"
        if not merged_path.exists():
            print("  ERROR: text-merged.cnf not found. Run text condition first.")
            sys.exit(1)
        merged = merged_path.read_text()
        conflicts = merged.count(";; CONFLICT:")
        print(f"\n  ── REPAIR ONLY: {conflicts} conflicts from existing merge ──")
        repair = run_text_repair(merged, conflicts)
        if repair:
            rv = repair["verification"]
            r_pass = sum(1 for v in rv.values() if v)
            print(f"\n  Repair result: {r_pass}/{len(rv)} in {repair['elapsed']:.1f}s")
            for k, v in sorted(rv.items()):
                if not v:
                    print(f"    FAIL: {k}")
        return

    if "--text-only" not in sys.argv:
        graph_result = run_graph_condition()

    if "--graph-only" not in sys.argv:
        text_result = run_text_condition()

    print_results(graph_result, text_result)

    # Save results
    output = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "model": MODEL,
        "timeout": TIMEOUT,
        "functions": 51,
        "overlap_functions": len(OVERLAP_FUNCTIONS),
    }
    if graph_result:
        output["graph"] = {
            "total_elapsed": graph_result["total_elapsed"],
            "agent_a_elapsed": graph_result["agent_a"]["elapsed"],
            "agent_b_elapsed": graph_result["agent_b"]["elapsed"],
            "agent_a_error": graph_result["agent_a"]["error"],
            "agent_b_error": graph_result["agent_b"]["error"],
            "conflicts": graph_result["conflicts"],
            "repair_rounds": graph_result["repair_rounds"],
            "verification": graph_result["verification"],
            "note": "Shared daemon (MVCC). Both agents connected via bridge to same daemon.",
        }
        (SCRIPT_DIR / "graph-agent-a-transcript.md").write_text(
            graph_result["transcripts"]["agent_a"])
        (SCRIPT_DIR / "graph-agent-b-transcript.md").write_text(
            graph_result["transcripts"]["agent_b"])
    if text_result:
        output["text"] = {
            "total_elapsed": text_result["total_elapsed"],
            "agent_a_elapsed": text_result["agent_a"]["elapsed"],
            "agent_b_elapsed": text_result["agent_b"]["elapsed"],
            "agent_a_error": text_result["agent_a"]["error"],
            "agent_b_error": text_result["agent_b"]["error"],
            "conflicts": text_result["conflicts"],
            "repair_rounds": text_result["repair_rounds"],
            "verification": text_result["verification"],
            "note": "Isolated workspaces (cwd per agent). Merge afterward.",
        }
        (SCRIPT_DIR / "text-agent-a-transcript.md").write_text(
            text_result["transcripts"]["agent_a"])
        (SCRIPT_DIR / "text-agent-b-transcript.md").write_text(
            text_result["transcripts"]["agent_b"])
        if text_result.get("merged_program"):
            (SCRIPT_DIR / "text-merged.cnf").write_text(
                text_result["merged_program"])
        if text_result.get("repair"):
            rep = text_result["repair"]
            output["text"]["repair"] = {
                "elapsed": rep["elapsed"],
                "error": rep["error"],
                "verification": rep["verification"],
                "total_with_repair": text_result.get("total_with_repair"),
            }
            (SCRIPT_DIR / "text-repair-transcript.md").write_text(
                rep.get("transcript", ""))
            if text_result.get("repaired_program"):
                (SCRIPT_DIR / "text-repaired.cnf").write_text(
                    text_result["repaired_program"])

    results_file = SCRIPT_DIR / "results.json"
    with open(results_file, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"  Results: {results_file}")


if __name__ == "__main__":
    main()

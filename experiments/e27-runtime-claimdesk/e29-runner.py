#!/usr/bin/env python3
"""
E29: Concurrent graph-native agents vs file-native agents.

Task: Add "suspended" status to ClaimDesk — a blocked state that creates
cross-domain obligation pressure.

Four conditions:
  graph_concurrent: 3 agents edit shared graph through MCP tools
  file_concurrent:  3 agents edit files in separate git worktrees
  graph_single:     1 agent edits graph through MCP tools
  file_single:      1 agent edits files directly
"""

import subprocess
import sys
import os
import json
import time
import tempfile
import shutil
import re
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

SCRIPT_DIR = Path(__file__).parent
E24B_DIR = SCRIPT_DIR.parent / "e24b-facade-concurrent"
MCP_SERVER = SCRIPT_DIR / "claimdesk-mcp.rkt"

NUM_RUNS = 3

# ── Task description (same for all conditions) ──────────────

SUSPENDED_DESCRIPTION = """\
Add "suspended" as a new status to ClaimDesk.

Suspended tickets are paused/frozen — they are not being actively worked
on, but they are not closed or resolved either. They can be resumed later.

Business rules:
- Tickets can be suspended from in_progress or on_hold
- Suspended tickets can be resumed back to in_progress, or closed directly
- Suspended tickets are NOT active work and should NOT be counted in
  active workload metrics
- Suspended tickets are NOT terminal — they can come back
"""

PARALLEL_AWARENESS = """\
You are one of several agents working in parallel on related parts of the
same feature. Other agents may be modifying related modules at the same
time. Make your changes narrowly, preserve compatibility, and encode any
assumptions about workflow states clearly in code rather than leaving them
implicit.
"""


# ── Integration tests ────────────────────────────────────────

INTEGRATION_TESTS = '''\
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from workflow import *

passed = failed = errors = 0

def check(name, condition, detail=""):
    global passed, failed
    if condition:
        print(f"PASS: {name}")
        passed += 1
    else:
        print(f"FAIL: {name} {detail}")
        failed += 1

# --- Status membership ---

def test_01_suspended_exists():
    check("test_01", "suspended" in ALL_STATUSES,
          f"ALL_STATUSES={list(ALL_STATUSES)}")

def test_02_suspended_not_active():
    check("test_02", "suspended" not in ACTIVE_STATUSES,
          f"ACTIVE_STATUSES={list(ACTIVE_STATUSES)}")

def test_03_suspended_not_terminal():
    check("test_03", "suspended" not in TERMINAL_STATUSES,
          f"TERMINAL_STATUSES={list(TERMINAL_STATUSES)}")

# --- Transitions ---

def test_04_in_progress_to_suspended():
    trans = VALID_TRANSITIONS.get("in_progress", [])
    check("test_04", "suspended" in list(trans),
          f"in_progress transitions={list(trans)}")

def test_05_on_hold_to_suspended():
    trans = VALID_TRANSITIONS.get("on_hold", [])
    check("test_05", "suspended" in list(trans),
          f"on_hold transitions={list(trans)}")

def test_06_suspended_to_in_progress():
    trans = VALID_TRANSITIONS.get("suspended", [])
    check("test_06", "in_progress" in list(trans),
          f"suspended transitions={list(trans)}")

def test_07_suspended_to_closed():
    trans = VALID_TRANSITIONS.get("suspended", [])
    check("test_07", "closed" in list(trans),
          f"suspended transitions={list(trans)}")

def test_08_no_open_to_suspended():
    trans = VALID_TRANSITIONS.get("open", [])
    check("test_08", "suspended" not in list(trans),
          f"open transitions={list(trans)}")

# --- Cross-domain: workflow structure ---

def test_09_blocked_statuses_exists():
    """OBLIGATION: workflow must export BLOCKED_STATUSES for the third group"""
    has_blocked = hasattr(sys.modules[__name__], 'BLOCKED_STATUSES') or \\
                  'BLOCKED_STATUSES' in dir(sys.modules['workflow'])
    if has_blocked:
        from workflow import BLOCKED_STATUSES
        check("test_09", "suspended" in BLOCKED_STATUSES,
              f"BLOCKED_STATUSES={list(BLOCKED_STATUSES)}")
    else:
        check("test_09", False, "BLOCKED_STATUSES not defined in workflow")

def test_10_is_blocked_helper():
    """OBLIGATION: workflow must provide is_blocked() helper"""
    try:
        from workflow import is_blocked
        check("test_10", is_blocked("suspended") == True,
              "is_blocked('suspended') should be True")
    except ImportError:
        check("test_10", False, "is_blocked not defined in workflow")

# --- Cross-domain: notifications ---

def test_11_notifications_for_suspended():
    """Notifications should fire when entering suspended (ticket frozen)"""
    try:
        from notifications import notify_transition, subscribe
        subscribe("t1", "watcher@test.com")
        result = notify_transition("t1", "in_progress", "suspended")
        check("test_11", result is not None and len(result) > 0,
              f"notify_transition returned {result}")
    except ImportError:
        check("test_11", False, "notifications module not found")
    except Exception as e:
        check("test_11", False, str(e))

def test_12_notifications_for_resume():
    """Notifications should fire when resuming from suspended"""
    try:
        from notifications import notify_transition, subscribe
        subscribe("t2", "watcher@test.com")
        result = notify_transition("t2", "suspended", "in_progress")
        check("test_12", result is not None and len(result) > 0,
              f"notify_transition returned {result}")
    except ImportError:
        check("test_12", False, "notifications module not found")
    except Exception as e:
        check("test_12", False, str(e))

# --- Cross-domain: analytics ---

def test_13_analytics_active_excludes_suspended():
    """OBLIGATION: active_ticket_count must exclude suspended"""
    try:
        from analytics import active_ticket_count
        count = active_ticket_count(["open", "suspended", "closed", "in_progress"])
        check("test_13", count == 2,
              f"expected 2 active, got {count}")
    except ImportError:
        check("test_13", False, "analytics module not found")
    except Exception as e:
        check("test_13", False, str(e))

def test_14_analytics_tags_blocked():
    """OBLIGATION: analytics must tag blocked transitions"""
    try:
        from analytics import track_transition
        event = track_transition("t1", "in_progress", "suspended")
        if isinstance(event, dict):
            has_blocked = event.get("is_blocked") == True
            not_terminal = event.get("is_terminal") != True
            check("test_14", has_blocked and not_terminal,
                  f"event={event}")
        else:
            check("test_14", False, f"track_transition returned {type(event)}")
    except ImportError:
        check("test_14", False, "analytics module not found")
    except Exception as e:
        check("test_14", False, str(e))

# --- Cross-domain: permissions ---

def test_15_suspend_permission_exists():
    """OBLIGATION: permissions must define suspend action"""
    try:
        from permissions import PERMISSION_RULES
        check("test_15", "suspend" in PERMISSION_RULES,
              f"PERMISSION_RULES keys={list(PERMISSION_RULES.keys())}")
    except ImportError:
        check("test_15", False, "permissions module not found")
    except Exception as e:
        check("test_15", False, str(e))

def test_16_resume_permission_exists():
    """OBLIGATION: permissions must define resume action"""
    try:
        from permissions import PERMISSION_RULES
        check("test_16", "resume" in PERMISSION_RULES,
              f"PERMISSION_RULES keys={list(PERMISSION_RULES.keys())}")
    except ImportError:
        check("test_16", False, "permissions module not found")
    except Exception as e:
        check("test_16", False, str(e))

# --- Regression ---

def test_17_existing_preserved():
    original = {"open", "in_progress", "on_hold", "closed", "resolved", "archived"}
    all_s = set(ALL_STATUSES)
    missing = original - all_s
    check("test_17", len(missing) == 0, f"missing: {missing}")

for name, fn in sorted(list(globals().items())):
    if name.startswith("test_") and callable(fn):
        try:
            fn()
        except Exception as e:
            print(f"ERROR: {name}: {e}")
            errors += 1

print(f"\\npassed {passed}, failed {failed}, errors {errors}")
'''

STRUCTURAL_TESTS = ["test_01", "test_02", "test_03", "test_04", "test_05",
                    "test_06", "test_07", "test_08", "test_17"]
OBLIGATION_TESTS = ["test_09", "test_10", "test_11", "test_12",
                    "test_13", "test_14", "test_15", "test_16"]


# ── Graph condition ──────────────────────────────────────────

GRAPH_SINGLE_PROMPT = f"""\
{SUSPENDED_DESCRIPTION}

You are modifying the ClaimDesk domain by editing its claim graph.
The graph already contains the base domain (statuses, transitions,
roles, permissions, effects).

Use the available tools to explore the current domain, make all necessary
changes, check obligations across all modules, and project the results.

You MUST call project_all_to_disk at the end to save the updated Python.
Do NOT write Python code. Edit the graph; Python is projected automatically.
"""

GRAPH_WORKFLOW_PROMPT = f"""\
{SUSPENDED_DESCRIPTION}

{PARALLEL_AWARENESS}

Your scope: WORKFLOW — status definitions and transitions.

You are modifying the ClaimDesk domain by editing its claim graph.
Add the suspended status and define its transitions. Check the current
domain first, then make changes.

You MUST call project_all_to_disk at the end.
Do NOT write Python code. Edit the graph; Python is projected automatically.
"""

GRAPH_PERMISSIONS_PROMPT = f"""\
{SUSPENDED_DESCRIPTION}

{PARALLEL_AWARENESS}

Your scope: PERMISSIONS — access control rules for suspended tickets.

You are modifying the ClaimDesk domain by editing its claim graph.
Explore the current domain, check what permission actions exist, then add
any new permission rules needed for the suspended status. Check obligations
after making changes.

You MUST call project_all_to_disk at the end.
Do NOT write Python code. Edit the graph; Python is projected automatically.
"""

GRAPH_ANALYTICS_PROMPT = f"""\
{SUSPENDED_DESCRIPTION}

{PARALLEL_AWARENESS}

Your scope: ANALYTICS and NOTIFICATIONS — event tracking and notification
behavior for suspended tickets.

You are modifying the ClaimDesk domain by editing its claim graph.
Explore the current domain, check what effects exist, then add any new
effect declarations needed for the suspended status. Check obligations
after making changes.

You MUST call project_all_to_disk at the end.
Do NOT write Python code. Edit the graph; Python is projected automatically.
"""


def make_mcp_config(output_dir):
    projected_dir = output_dir / "projected"
    projected_dir.mkdir(exist_ok=True)
    config = {
        "mcpServers": {
            "claimdesk": {
                "command": "racket",
                "args": [str(MCP_SERVER), "--output-dir", str(projected_dir)],
            }
        }
    }
    path = output_dir / "mcp-config.json"
    path.write_text(json.dumps(config))
    return path, projected_dir


GRAPH_TOOLS = [
    "mcp__claimdesk__list_statuses",
    "mcp__claimdesk__list_transitions",
    "mcp__claimdesk__list_roles",
    "mcp__claimdesk__list_permissions",
    "mcp__claimdesk__list_effects",
    "mcp__claimdesk__add_status",
    "mcp__claimdesk__add_transition",
    "mcp__claimdesk__add_role",
    "mcp__claimdesk__add_permission",
    "mcp__claimdesk__add_effect",
    "mcp__claimdesk__check_obligations",
    "mcp__claimdesk__project_module",
    "mcp__claimdesk__project_all_to_disk",
    "mcp__claimdesk__query_domain",
]


def launch_graph_agent(prompt, output_dir, label):
    mcp_config_path, projected_dir = make_mcp_config(output_dir)
    start = time.time()
    result = subprocess.run(
        ["claude", "-p", "--model", "sonnet", "--output-format", "json",
         "--tools", "", "--allowedTools", ",".join(GRAPH_TOOLS),
         "--mcp-config", str(mcp_config_path)],
        input=prompt, capture_output=True, text=True, timeout=300,
    )
    elapsed = time.time() - start
    agent_output = {}
    try:
        agent_output = json.loads(result.stdout)
    except json.JSONDecodeError:
        agent_output = {"raw": result.stdout[:2000]}
    (output_dir / f"agent-{label}.json").write_text(json.dumps(agent_output, indent=2))

    modules = {}
    for mod in ["workflow", "notifications", "analytics", "permissions"]:
        path = projected_dir / f"{mod}.py"
        if path.exists():
            modules[mod] = path.read_text()

    return {
        "label": label,
        "elapsed": elapsed,
        "cost": agent_output.get("total_cost_usd", 0),
        "turns": agent_output.get("num_turns", 0),
        "modules": modules,
    }


def run_graph_single(run_id):
    output_dir = SCRIPT_DIR / "output" / f"graph_single-{run_id}"
    output_dir.mkdir(parents=True, exist_ok=True)
    result = launch_graph_agent(GRAPH_SINGLE_PROMPT, output_dir, "single")
    return result


def run_graph_concurrent(run_id):
    output_dir = SCRIPT_DIR / "output" / f"graph_concurrent-{run_id}"
    output_dir.mkdir(parents=True, exist_ok=True)

    prompts = [
        (GRAPH_WORKFLOW_PROMPT, "workflow"),
        (GRAPH_PERMISSIONS_PROMPT, "permissions"),
        (GRAPH_ANALYTICS_PROMPT, "analytics"),
    ]

    agent_results = []
    # Each graph agent gets its own MCP server instance (independent state)
    # This simulates concurrent work — each sees the base domain
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {}
        for prompt, label in prompts:
            agent_dir = output_dir / label
            agent_dir.mkdir(exist_ok=True)
            f = pool.submit(launch_graph_agent, prompt, agent_dir, label)
            futures[f] = label

        for f in as_completed(futures):
            label = futures[f]
            try:
                r = f.result()
                agent_results.append(r)
                print(f"    {label}: {r['elapsed']:.1f}s, ${r['cost']:.3f}")
            except Exception as e:
                print(f"    {label}: ERROR {e}")
                agent_results.append({"label": label, "error": str(e), "modules": {}})

    # Merge: take each agent's projected modules
    # The workflow agent projects workflow.py, permissions agent projects permissions.py, etc.
    # But each agent actually projects ALL modules from their own graph state.
    # Use workflow.py from workflow agent, permissions.py from permissions agent, etc.
    merged = {}
    module_source = {"workflow": "workflow", "permissions": "permissions",
                     "notifications": "analytics", "analytics": "analytics"}
    for mod, source_label in module_source.items():
        for r in agent_results:
            if r.get("label") == source_label and mod in r.get("modules", {}):
                merged[mod] = r["modules"][mod]
                break

    total_elapsed = max((r.get("elapsed", 0) for r in agent_results), default=0)
    total_cost = sum(r.get("cost", 0) for r in agent_results)

    return {
        "elapsed": total_elapsed,
        "cost": total_cost,
        "turns": sum(r.get("turns", 0) for r in agent_results),
        "modules": merged,
        "agents": agent_results,
    }


# ── File condition ───────────────────────────────────────────

FILE_SINGLE_PROMPT = f"""\
{SUSPENDED_DESCRIPTION}

You are modifying the ClaimDesk helpdesk application. The workspace
contains the Python source files: workflow.py, permissions.py,
notifications.py, analytics.py (plus models.py and core.py).

Read the existing code to understand the architecture, then make all
necessary changes across the codebase. Make sure suspended is handled
consistently everywhere that status matters.
"""

FILE_WORKFLOW_PROMPT = f"""\
{SUSPENDED_DESCRIPTION}

{PARALLEL_AWARENESS}

Your scope: workflow.py — status definitions and transitions.

Read the existing code to understand the architecture, then update
workflow.py to add the suspended status. You may read other files to
understand patterns but focus your edits on workflow.py.
"""

FILE_PERMISSIONS_PROMPT = f"""\
{SUSPENDED_DESCRIPTION}

{PARALLEL_AWARENESS}

Your scope: permissions.py — access control rules for suspended tickets.

Read the existing code (especially workflow.py) to understand the status
model, then update permissions.py with any new permission rules needed
for the suspended status.
"""

FILE_ANALYTICS_PROMPT = f"""\
{SUSPENDED_DESCRIPTION}

{PARALLEL_AWARENESS}

Your scope: analytics.py and notifications.py — event tracking and
notification behavior for suspended tickets.

Read the existing code (especially workflow.py) to understand the status
model, then update analytics.py and notifications.py to handle suspended
tickets correctly.
"""


def setup_file_workspace(workspace_dir):
    """Create workspace with baseline modules projected from the graph."""
    codebase = E24B_DIR / "codebase"
    for f in ["models.py", "core.py", "workflow.py"]:
        shutil.copy(codebase / f, workspace_dir / f)

    # Project baseline modules from graph
    result = subprocess.run(
        ["racket", "-e", '''
(require "claimdesk.rkt"
         "../../cnf-lib/private/kernel.rkt"
         "../../cnf-lib/private/datalog.rkt"
         "../../cnf-lib/private/schema.rkt")
(setup-claimdesk!)
(display "===NOTIFICATIONS===\n")
(display (project-notifications-py))
(display "===ANALYTICS===\n")
(display (project-analytics-py))
(display "===PERMISSIONS===\n")
(display (project-permissions-py))
'''],
        capture_output=True, text=True, cwd=str(SCRIPT_DIR),
    )
    parts = result.stdout.split("===")
    for i in range(1, len(parts), 2):
        name = parts[i].strip().lower()
        content = parts[i + 1] if i + 1 < len(parts) else ""
        if name in ("notifications", "analytics", "permissions"):
            (workspace_dir / f"{name}.py").write_text(content)


def launch_file_agent(prompt, workspace_dir, label):
    start = time.time()
    result = subprocess.run(
        ["claude", "-p", "--model", "sonnet", "--output-format", "json",
         "--dangerously-skip-permissions"],
        input=prompt, capture_output=True, text=True,
        timeout=300, cwd=str(workspace_dir),
    )
    elapsed = time.time() - start
    agent_output = {}
    try:
        agent_output = json.loads(result.stdout)
    except json.JSONDecodeError:
        agent_output = {"raw": result.stdout[:2000]}

    modules = {}
    for mod in ["workflow", "notifications", "analytics", "permissions"]:
        path = workspace_dir / f"{mod}.py"
        if path.exists():
            modules[mod] = path.read_text()

    return {
        "label": label,
        "elapsed": elapsed,
        "cost": agent_output.get("total_cost_usd", 0),
        "turns": agent_output.get("num_turns", 0),
        "modules": modules,
    }


def run_file_single(run_id):
    output_dir = SCRIPT_DIR / "output" / f"file_single-{run_id}"
    output_dir.mkdir(parents=True, exist_ok=True)
    workspace = output_dir / "workspace"
    workspace.mkdir(exist_ok=True)
    setup_file_workspace(workspace)
    return launch_file_agent(FILE_SINGLE_PROMPT, workspace, "single")


def run_file_concurrent(run_id):
    output_dir = SCRIPT_DIR / "output" / f"file_concurrent-{run_id}"
    output_dir.mkdir(parents=True, exist_ok=True)

    prompts = [
        (FILE_WORKFLOW_PROMPT, "workflow"),
        (FILE_PERMISSIONS_PROMPT, "permissions"),
        (FILE_ANALYTICS_PROMPT, "analytics"),
    ]

    agent_results = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {}
        for prompt, label in prompts:
            ws = output_dir / f"worktree-{label}"
            ws.mkdir(exist_ok=True)
            setup_file_workspace(ws)
            f = pool.submit(launch_file_agent, prompt, ws, label)
            futures[f] = (label, ws)

        for f in as_completed(futures):
            label, ws = futures[f]
            try:
                r = f.result()
                agent_results.append(r)
                print(f"    {label}: {r['elapsed']:.1f}s, ${r['cost']:.3f}")
            except Exception as e:
                print(f"    {label}: ERROR {e}")
                agent_results.append({"label": label, "error": str(e), "modules": {}})

    # Merge: each agent edited their assigned module(s)
    merged = {}
    module_source = {"workflow": "workflow", "permissions": "permissions",
                     "notifications": "analytics", "analytics": "analytics"}
    for mod, source_label in module_source.items():
        for r in agent_results:
            if r.get("label") == source_label and mod in r.get("modules", {}):
                merged[mod] = r["modules"][mod]
                break

    total_elapsed = max((r.get("elapsed", 0) for r in agent_results), default=0)
    total_cost = sum(r.get("cost", 0) for r in agent_results)

    return {
        "elapsed": total_elapsed,
        "cost": total_cost,
        "turns": sum(r.get("turns", 0) for r in agent_results),
        "modules": merged,
        "agents": agent_results,
    }


# ── Test runner ──────────────────────────────────────────────

def run_tests(modules, label):
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        for mod_name, mod_code in modules.items():
            (tmpdir / f"{mod_name}.py").write_text(mod_code)
        (tmpdir / "test_integration.py").write_text(INTEGRATION_TESTS)
        codebase = E24B_DIR / "codebase"
        for f in ["models.py", "core.py"]:
            shutil.copy(codebase / f, tmpdir / f)

        result = subprocess.run(
            [sys.executable, "test_integration.py"],
            capture_output=True, text=True, cwd=str(tmpdir), timeout=30,
        )
        return parse_test_results(result.stdout + result.stderr)


def parse_test_results(output):
    results = {}
    for line in output.split("\n"):
        line = line.strip()
        if line.startswith("PASS:"):
            test_name = line.split(":")[1].strip().split()[0]
            results[test_name] = "pass"
        elif line.startswith("FAIL:"):
            test_name = line.split(":")[1].strip().split()[0]
            results[test_name] = "fail"
        elif line.startswith("ERROR:"):
            test_name = line.split(":")[1].strip().split()[0]
            results[test_name] = "error"

    structural_bugs = sum(1 for t in STRUCTURAL_TESTS if results.get(t) != "pass")
    obligation_bugs = sum(1 for t in OBLIGATION_TESTS if results.get(t) != "pass")
    return {
        "tests": results,
        "passed": sum(1 for v in results.values() if v == "pass"),
        "total": len(results),
        "structural_bugs": structural_bugs,
        "obligation_bugs": obligation_bugs,
        "raw_output": output,
    }


# ── Main ─────────────────────────────────────────────────────

CONDITION_RUNNERS = {
    "graph_single": run_graph_single,
    "graph_concurrent": run_graph_concurrent,
    "file_single": run_file_single,
    "file_concurrent": run_file_concurrent,
}


def run_experiment(condition, num_runs):
    print(f"\n{'='*60}")
    print(f"  E29: {condition} — {num_runs} runs")
    print(f"{'='*60}\n")

    runner = CONDITION_RUNNERS[condition]
    all_results = []

    for i in range(num_runs):
        run_id = f"run-{i+1}"
        print(f"--- {condition} {run_id} ---")

        try:
            run_result = runner(run_id)
        except subprocess.TimeoutExpired:
            print(f"  TIMEOUT")
            all_results.append({"run_id": run_id, "error": "timeout",
                                "structural_bugs": len(STRUCTURAL_TESTS),
                                "obligation_bugs": len(OBLIGATION_TESTS)})
            continue
        except Exception as e:
            print(f"  ERROR: {e}")
            all_results.append({"run_id": run_id, "error": str(e),
                                "structural_bugs": len(STRUCTURAL_TESTS),
                                "obligation_bugs": len(OBLIGATION_TESTS)})
            continue

        modules = run_result.get("modules", {})
        missing = [m for m in ["workflow", "notifications", "analytics", "permissions"]
                   if m not in modules]
        if missing:
            print(f"  WARNING: missing modules: {missing}")

        if modules:
            test_result = run_tests(modules, f"{condition}-{run_id}")
        else:
            test_result = {"tests": {}, "passed": 0, "total": 0,
                           "structural_bugs": len(STRUCTURAL_TESTS),
                           "obligation_bugs": len(OBLIGATION_TESTS),
                           "raw_output": "no modules"}

        run_data = {
            "run_id": run_id,
            "elapsed": run_result.get("elapsed"),
            "cost": run_result.get("cost"),
            "turns": run_result.get("turns"),
            "modules_produced": list(modules.keys()),
            **test_result,
        }
        all_results.append(run_data)

        total_tests = len(STRUCTURAL_TESTS) + len(OBLIGATION_TESTS) + 1  # +1 for regression
        print(f"  elapsed: {run_result.get('elapsed', 0):.1f}s  cost: ${run_result.get('cost', 0):.3f}")
        print(f"  tests: {test_result['passed']}/{test_result['total']}")
        print(f"  structural bugs: {test_result['structural_bugs']}/{len(STRUCTURAL_TESTS)}")
        print(f"  obligation bugs: {test_result['obligation_bugs']}/{len(OBLIGATION_TESTS)}")
        print()

    # Aggregate
    total_struct = sum(r.get("structural_bugs", 0) for r in all_results)
    total_oblig = sum(r.get("obligation_bugs", 0) for r in all_results)

    summary = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "experiment": "E29",
        "condition": condition,
        "num_runs": num_runs,
        "runs": all_results,
        "aggregate": {
            "total_structural_bugs": total_struct,
            "total_obligation_bugs": total_oblig,
            "structural_opportunities": num_runs * len(STRUCTURAL_TESTS),
            "obligation_opportunities": num_runs * len(OBLIGATION_TESTS),
            "mean_elapsed": sum(r.get("elapsed", 0) for r in all_results) / max(len(all_results), 1),
            "mean_cost": sum(r.get("cost", 0) for r in all_results) / max(len(all_results), 1),
        },
    }

    outfile = SCRIPT_DIR / f"results-e29-{condition}.json"
    outfile.write_text(json.dumps(summary, indent=2, default=str))
    print(f"Results: {outfile}")
    print(f"Structural: {total_struct}/{num_runs * len(STRUCTURAL_TESTS)}")
    print(f"Obligation: {total_oblig}/{num_runs * len(OBLIGATION_TESTS)}")

    return summary


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="E29 experiment runner")
    parser.add_argument("condition",
                        choices=list(CONDITION_RUNNERS.keys()) + ["all"],
                        help="Which condition(s) to run")
    parser.add_argument("--runs", type=int, default=NUM_RUNS)
    args = parser.parse_args()

    if args.condition == "all":
        for cond in CONDITION_RUNNERS:
            run_experiment(cond, args.runs)
    else:
        run_experiment(args.condition, args.runs)

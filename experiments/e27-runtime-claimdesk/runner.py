#!/usr/bin/env python3
"""
E28 experiment runner: graph-native editing vs file-native editing.

Task: "Add 'duplicate' as a terminal status to ClaimDesk."
  - Add the status
  - Add transitions from open and in_progress to duplicate
  - Ensure all modules handle duplicate correctly
  - Notifications must suppress for duplicate
  - Analytics must tag duplicate as terminal
  - Permissions: archiving duplicate tickets requires admin

Two conditions:
  graph: Agent uses ClaimDesk MCP tools to edit claims. Python projected from graph.
  file:  Agent edits Python files directly.
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

# ── Integration tests ────────────────────────────────────────

INTEGRATION_TESTS = '''\
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from workflow import TERMINAL_STATUSES, ACTIVE_STATUSES, ALL_STATUSES, VALID_TRANSITIONS

passed = failed = errors = 0

def check(name, condition, detail=""):
    global passed, failed
    if condition:
        print(f"PASS: {name}")
        passed += 1
    else:
        print(f"FAIL: {name} {detail}")
        failed += 1

def test_01_duplicate_in_terminal():
    ts = list(TERMINAL_STATUSES) if not isinstance(TERMINAL_STATUSES, list) else TERMINAL_STATUSES
    check("test_01", "duplicate" in ts, f"TERMINAL_STATUSES={ts}")

def test_02_duplicate_in_all():
    a = list(ALL_STATUSES) if not isinstance(ALL_STATUSES, list) else ALL_STATUSES
    check("test_02", "duplicate" in a, f"ALL_STATUSES={a}")

def test_03_duplicate_not_active():
    a = list(ACTIVE_STATUSES) if not isinstance(ACTIVE_STATUSES, list) else ACTIVE_STATUSES
    check("test_03", "duplicate" not in a, f"ACTIVE_STATUSES={a}")

def test_04_transition_open_to_duplicate():
    trans = VALID_TRANSITIONS.get("open", [])
    t = list(trans) if not isinstance(trans, list) else trans
    check("test_04", "duplicate" in t, f"open transitions={t}")

def test_05_transition_in_progress_to_duplicate():
    trans = VALID_TRANSITIONS.get("in_progress", [])
    t = list(trans) if not isinstance(trans, list) else trans
    check("test_05", "duplicate" in t, f"in_progress transitions={t}")

def test_06_duplicate_is_terminal():
    ts = set(TERMINAL_STATUSES) if not isinstance(TERMINAL_STATUSES, set) else TERMINAL_STATUSES
    check("test_06", "duplicate" in ts, f"TERMINAL_STATUSES={ts}")

def test_07_duplicate_not_active():
    a = set(ACTIVE_STATUSES) if not isinstance(ACTIVE_STATUSES, set) else ACTIVE_STATUSES
    check("test_07", "duplicate" not in a, f"ACTIVE_STATUSES={a}")

def test_08_notifications_suppress_duplicate():
    try:
        from notifications import notify_transition, subscribe
        subscribe("t1", "test@test.com")
        result = notify_transition("t1", "open", "duplicate")
        check("test_08", result == [] or result is None or
              (hasattr(result, '__len__') and len(result) == 0),
              f"notify_transition returned {result}")
    except ImportError:
        check("test_08", False, "notifications module not found")
    except Exception as e:
        check("test_08", False, str(e))

def test_09_analytics_tags_duplicate():
    try:
        from analytics import track_transition
        event = track_transition("t1", "open", "duplicate")
        if isinstance(event, dict):
            check("test_09", event.get("is_terminal") == True,
                  f"event={event}")
        else:
            check("test_09", False, f"track_transition returned {type(event)}")
    except ImportError:
        check("test_09", False, "analytics module not found")
    except Exception as e:
        check("test_09", False, str(e))

def test_10_analytics_active_count():
    try:
        from analytics import active_ticket_count
        count = active_ticket_count(["open", "closed", "duplicate", "in_progress"])
        check("test_10", count == 2, f"expected 2, got {count}")
    except ImportError:
        check("test_10", False, "analytics module not found")
    except Exception as e:
        check("test_10", False, str(e))

def test_11_permissions_archive():
    try:
        from permissions import PERMISSION_RULES
        archive_rule = PERMISSION_RULES.get("archive")
        if isinstance(archive_rule, set):
            check("test_11", "admin" in archive_rule, f"rule={archive_rule}")
        elif isinstance(archive_rule, str):
            check("test_11", archive_rule == "admin", f"rule={archive_rule}")
        else:
            check("test_11", archive_rule is not None, f"rule={archive_rule}")
    except ImportError:
        check("test_11", False, "permissions module not found")
    except Exception as e:
        check("test_11", False, str(e))

def test_12_existing_statuses_preserved():
    original = {"open", "in_progress", "on_hold", "closed", "resolved", "archived"}
    all_s = set(ALL_STATUSES)
    missing = original - all_s
    check("test_12", len(missing) == 0, f"missing: {missing}")

for name, fn in sorted(list(globals().items())):
    if name.startswith("test_") and callable(fn):
        try:
            fn()
        except Exception as e:
            print(f"ERROR: {name}: {e}")
            errors += 1

print(f"\\npassed {passed}, failed {failed}, errors {errors}")
'''

INFO_GAP_TESTS = [
    "test_01", "test_02", "test_03", "test_04", "test_05",
    "test_06", "test_07", "test_08", "test_09", "test_10",
    "test_11", "test_12",
]


# ── Graph condition ──────────────────────────────────────────

GRAPH_PROMPT = """\
You are modifying the ClaimDesk helpdesk application by editing its
claim graph. The graph contains the domain model: statuses, transitions,
roles, permissions, and effects.

YOUR TASK: Add "duplicate" as a new terminal status to ClaimDesk.

A ticket marked as duplicate means it's a copy of another ticket. Like
"closed" and "archived", duplicate tickets are no longer active. Tickets
can be marked as duplicate from the "open" or "in_progress" states.

Use the available tools to explore the current domain, make changes,
check obligations, and project the results. You MUST call
project_all_to_disk at the end to save the updated Python modules.

Do NOT write Python code. Edit the graph; Python is projected automatically.
"""

def run_graph_condition(run_id):
    """Launch agent with ClaimDesk MCP tools."""
    output_dir = SCRIPT_DIR / "output" / f"graph-{run_id}"
    output_dir.mkdir(parents=True, exist_ok=True)

    projected_dir = output_dir / "projected"
    projected_dir.mkdir(exist_ok=True)

    mcp_config = {
        "mcpServers": {
            "claimdesk": {
                "command": "racket",
                "args": [str(MCP_SERVER), "--output-dir", str(projected_dir)],
            }
        }
    }
    mcp_config_path = output_dir / "mcp-config.json"
    mcp_config_path.write_text(json.dumps(mcp_config))

    tool_names = [
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

    start = time.time()
    result = subprocess.run(
        [
            "claude", "-p",
            "--model", "sonnet",
            "--output-format", "json",
            "--tools", "",
            "--allowedTools", ",".join(tool_names),
            "--mcp-config", str(mcp_config_path),
        ],
        input=GRAPH_PROMPT,
        capture_output=True,
        text=True,
        timeout=300,
    )
    elapsed = time.time() - start

    # Parse agent output
    agent_output = {}
    try:
        agent_output = json.loads(result.stdout)
    except json.JSONDecodeError:
        agent_output = {"raw": result.stdout[:2000]}

    # Save agent output
    (output_dir / "agent-output.json").write_text(json.dumps(agent_output, indent=2))

    # Read projected Python files written by project_all_to_disk
    modules = {}
    for mod in ["workflow", "notifications", "analytics", "permissions"]:
        path = projected_dir / f"{mod}.py"
        if path.exists():
            modules[mod] = path.read_text()

    return {
        "condition": "graph",
        "run_id": run_id,
        "elapsed": elapsed,
        "agent_output": agent_output,
        "modules": modules,
        "cost": agent_output.get("cost_usd", agent_output.get("total_cost_usd", 0)),
        "turns": agent_output.get("num_turns", 0),
    }


def extract_projected_modules(agent_output):
    """Extract projected Python code from agent's tool call results."""
    modules = {}
    result_text = json.dumps(agent_output)

    # Look for project_module results in the conversation
    # The MCP server returns the Python code as tool result text
    for module_name in ["workflow", "notifications", "analytics", "permissions"]:
        # Try to find the projected code in the agent output
        # Pattern: the agent called project_module and got Python back
        patterns = [
            # Look for the auto-generated header
            rf'# Auto-generated from CNF claim graph.*?(?=# Auto-generated|$)',
        ]
        # Search in the full output text
        # Find all "Auto-generated" blocks
        blocks = re.findall(
            r'# Auto-generated from CNF claim graph\n# DO NOT EDIT.*?\n\n(.*?)(?=\\n# Auto-generated|"|\Z)',
            result_text,
            re.DOTALL,
        )

    # Better approach: parse the agent's result structure
    # Claude --output-format json includes the conversation messages
    messages = agent_output.get("messages", [])
    if not messages:
        # Try alternate structure
        messages = agent_output.get("result", {}).get("messages", [])

    for msg in messages:
        if msg.get("role") == "tool":
            content = msg.get("content", "")
            if isinstance(content, list):
                for c in content:
                    text = c.get("text", "") if isinstance(c, dict) else str(c)
                    _extract_module_from_text(text, modules)
            elif isinstance(content, str):
                _extract_module_from_text(content, modules)

    return modules


def _extract_module_from_text(text, modules):
    """Try to identify which module this projected Python belongs to."""
    if "# Auto-generated from CNF claim graph" not in text:
        return
    # Unescape JSON string escapes
    text = text.replace("\\n", "\n").replace('\\"', '"')
    if "VALID_TRANSITIONS" in text:
        modules["workflow"] = text
    elif "PERMISSION_RULES" in text:
        modules["permissions"] = text
    elif "subscribers" in text or "notify_transition" in text:
        modules["notifications"] = text
    elif "track_transition" in text or "events" in text:
        modules["analytics"] = text


def extract_file_modules(text):
    """Extract Python code blocks for each module from agent's response text."""
    modules = {}
    # Look for patterns like **workflow.py** followed by ```python ... ```
    # or --- workflow.py --- followed by code
    for mod in ["workflow", "notifications", "analytics", "permissions"]:
        patterns = [
            # **workflow.py** followed by ```python...```
            rf'(?:\*\*{mod}\.py\*\*|---\s*{mod}\.py\s*---|{mod}\.py:?)\s*\n```(?:python)?\n(.*?)```',
        ]
        for pat in patterns:
            m = re.search(pat, text, re.DOTALL | re.IGNORECASE)
            if m:
                modules[mod] = m.group(1).strip() + "\n"
                break

    # Fallback: split on file headers and extract
    if len(modules) < 4:
        parts = re.split(r'(?:\*\*|---\s*)([\w]+\.py)(?:\*\*|---)', text)
        i = 1
        while i < len(parts) - 1:
            fname = parts[i].replace(".py", "")
            content = parts[i + 1]
            if fname in ["workflow", "notifications", "analytics", "permissions"]:
                code_match = re.search(r'```(?:python)?\n(.*?)```', content, re.DOTALL)
                if code_match and fname not in modules:
                    modules[fname] = code_match.group(1).strip() + "\n"
            i += 2

    return modules


# ── File condition ───────────────────────────────────────────

FILE_PROMPT = """\
You are modifying the ClaimDesk helpdesk application. The workspace contains
the Python source files.

YOUR TASK: Add "duplicate" as a new terminal status to ClaimDesk.

A ticket marked as duplicate means it's a copy of another ticket. Like
"closed" and "archived", duplicate tickets are no longer active. Tickets
can be marked as duplicate from the "open" or "in_progress" states.

Read the existing code to understand the architecture, then make all
necessary changes across the codebase. Make sure duplicate is handled
consistently everywhere that status matters.
"""


def setup_file_workspace(workspace_dir):
    """Copy base codebase + projected baseline modules."""
    codebase = E24B_DIR / "codebase"
    for f in ["models.py", "core.py", "workflow.py"]:
        shutil.copy(codebase / f, workspace_dir / f)

    # Write baseline notifications, analytics, permissions from E24b reference
    # or project from graph baseline
    result = subprocess.run(
        ["racket", "-e", '''
(require "claimdesk.rkt"
         "../../cnf-lib/private/kernel.rkt"
         "../../cnf-lib/private/datalog.rkt"
         "../../cnf-lib/private/schema.rkt")
(setup-claimdesk!)
(display "===NOTIFICATIONS===\\n")
(display (project-notifications-py))
(display "===ANALYTICS===\\n")
(display (project-analytics-py))
(display "===PERMISSIONS===\\n")
(display (project-permissions-py))
'''],
        capture_output=True, text=True,
        cwd=str(SCRIPT_DIR),
    )

    parts = result.stdout.split("===")
    for i in range(1, len(parts), 2):
        name = parts[i].strip().lower()
        content = parts[i + 1] if i + 1 < len(parts) else ""
        if name == "notifications":
            (workspace_dir / "notifications.py").write_text(content)
        elif name == "analytics":
            (workspace_dir / "analytics.py").write_text(content)
        elif name == "permissions":
            (workspace_dir / "permissions.py").write_text(content)


def run_file_condition(run_id):
    """Launch agent with file access."""
    output_dir = SCRIPT_DIR / "output" / f"file-{run_id}"
    output_dir.mkdir(parents=True, exist_ok=True)
    workspace = output_dir / "workspace"
    workspace.mkdir(exist_ok=True)

    setup_file_workspace(workspace)

    start = time.time()
    result = subprocess.run(
        [
            "claude", "-p",
            "--model", "sonnet",
            "--output-format", "json",
            "--dangerously-skip-permissions",
        ],
        input=FILE_PROMPT,
        capture_output=True,
        text=True,
        timeout=300,
        cwd=str(workspace),
    )
    elapsed = time.time() - start

    agent_output = {}
    try:
        agent_output = json.loads(result.stdout)
    except json.JSONDecodeError:
        agent_output = {"raw": result.stdout[:2000]}

    (output_dir / "agent-output.json").write_text(json.dumps(agent_output, indent=2))

    # Read workspace files (agent edits them in place with --dangerously-skip-permissions)
    modules = {}
    for mod in ["workflow", "notifications", "analytics", "permissions"]:
        path = workspace / f"{mod}.py"
        if path.exists():
            modules[mod] = path.read_text()

    return {
        "condition": "file",
        "run_id": run_id,
        "elapsed": elapsed,
        "agent_output": agent_output,
        "modules": modules,
        "cost": agent_output.get("cost_usd", agent_output.get("total_cost_usd", 0)),
        "turns": agent_output.get("num_turns", 0),
    }


# ── Test runner ──────────────────────────────────────────────

def run_tests(modules, run_label):
    """Write modules to temp dir, run integration tests, return results."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        for mod_name, mod_code in modules.items():
            (tmpdir / f"{mod_name}.py").write_text(mod_code)

        # Write test file
        (tmpdir / "test_integration.py").write_text(INTEGRATION_TESTS)

        # Copy models.py and core.py (needed by imports)
        codebase = E24B_DIR / "codebase"
        for f in ["models.py", "core.py"]:
            shutil.copy(codebase / f, tmpdir / f)

        result = subprocess.run(
            [sys.executable, "test_integration.py"],
            capture_output=True, text=True,
            cwd=str(tmpdir),
            timeout=30,
        )

        output = result.stdout + result.stderr
        return parse_test_results(output, run_label)


def parse_test_results(output, label):
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

    info_gap_bugs = sum(1 for t in INFO_GAP_TESTS if results.get(t) != "pass")
    return {
        "tests": results,
        "passed": sum(1 for v in results.values() if v == "pass"),
        "failed": sum(1 for v in results.values() if v == "fail"),
        "errors": sum(1 for v in results.values() if v == "error"),
        "info_gap_bugs": info_gap_bugs,
        "raw_output": output,
    }


# ── Main ─────────────────────────────────────────────────────

def run_experiment(condition, num_runs):
    print(f"\n{'='*60}")
    print(f"  E28: {condition} condition — {num_runs} runs")
    print(f"{'='*60}\n")

    all_results = []

    for i in range(num_runs):
        run_id = f"run-{i+1}"
        print(f"--- {condition} {run_id} ---")

        try:
            if condition == "graph":
                run_result = run_graph_condition(run_id)
            else:
                run_result = run_file_condition(run_id)
        except subprocess.TimeoutExpired:
            print(f"  TIMEOUT: {run_id}")
            all_results.append({
                "run_id": run_id,
                "error": "timeout",
                "tests": {},
                "info_gap_bugs": len(INFO_GAP_TESTS),
            })
            continue
        except Exception as e:
            print(f"  ERROR: {run_id}: {e}")
            all_results.append({
                "run_id": run_id,
                "error": str(e),
                "tests": {},
                "info_gap_bugs": len(INFO_GAP_TESTS),
            })
            continue

        modules = run_result["modules"]
        missing = [m for m in ["workflow", "notifications", "analytics", "permissions"]
                   if m not in modules]
        if missing:
            print(f"  WARNING: missing modules: {missing}")

        if modules:
            test_result = run_tests(modules, f"{condition}-{run_id}")
        else:
            test_result = {
                "tests": {},
                "passed": 0, "failed": 0, "errors": 0,
                "info_gap_bugs": len(INFO_GAP_TESTS),
                "raw_output": "no modules to test",
            }

        run_data = {
            "run_id": run_id,
            "elapsed": run_result.get("elapsed"),
            "cost": run_result.get("cost"),
            "turns": run_result.get("turns"),
            "modules_produced": list(modules.keys()),
            **test_result,
        }
        all_results.append(run_data)

        print(f"  elapsed: {run_result.get('elapsed', 0):.1f}s")
        print(f"  modules: {list(modules.keys())}")
        print(f"  tests: {test_result['passed']}/{test_result['passed'] + test_result['failed'] + test_result['errors']}")
        print(f"  info-gap bugs: {test_result['info_gap_bugs']}/{len(INFO_GAP_TESTS)}")
        print()

    # Aggregate
    total_bugs = sum(r.get("info_gap_bugs", 0) for r in all_results)
    total_opps = num_runs * len(INFO_GAP_TESTS)
    failure_rate = total_bugs / total_opps if total_opps > 0 else 0

    summary = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "experiment": "E28",
        "condition": condition,
        "num_runs": num_runs,
        "runs": all_results,
        "aggregate": {
            "total_bugs": total_bugs,
            "total_opportunities": total_opps,
            "failure_rate": failure_rate,
            "per_run_bugs": [r.get("info_gap_bugs", 0) for r in all_results],
            "mean_elapsed": sum(r.get("elapsed", 0) for r in all_results) / max(len(all_results), 1),
            "mean_cost": sum(r.get("cost", 0) for r in all_results) / max(len(all_results), 1),
        },
    }

    outfile = SCRIPT_DIR / f"results-{condition}.json"
    outfile.write_text(json.dumps(summary, indent=2, default=str))
    print(f"\nResults saved to {outfile}")
    print(f"Failure rate: {total_bugs}/{total_opps} ({failure_rate:.0%})")

    return summary


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="E28 experiment runner")
    parser.add_argument("condition", choices=["graph", "file", "both"],
                        help="Which condition to run")
    parser.add_argument("--runs", type=int, default=NUM_RUNS,
                        help="Number of runs per condition")
    args = parser.parse_args()

    if args.condition == "both":
        run_experiment("graph", args.runs)
        run_experiment("file", args.runs)
    else:
        run_experiment(args.condition, args.runs)

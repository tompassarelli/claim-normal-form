#!/usr/bin/env python3
"""
E31: Novel Group Synthesis — Does Property-Derived Classification Generalize?

Task: add "escalated" to ClaimDesk. Escalated tickets are still active work
(counts_as_work=true) but have high priority — different from regular active.
The two-property model (counts_as_work, terminal) maps this to "active", but
the three-property model (+ priority) distinguishes "escalated" as a fourth group.

Same 4 conditions as E30:
  graph_label:      agent picks group directly (now includes "escalated" in enum)
  graph_validated:  agent picks group + declares properties (+ optional priority)
  graph_properties: agent declares properties only, graph derives group
  file_single:      file baseline
"""

import subprocess
import sys
import json
import time
import tempfile
import shutil
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
E24B_DIR = SCRIPT_DIR.parent / "e24b-facade-concurrent"
MCP_SERVER = SCRIPT_DIR / "claimdesk-mcp.rkt"

NUM_RUNS = 3

# ── Task description (same for all conditions) ──────────────

ESCALATED_DESCRIPTION = """\
Add "escalated" as a new status to ClaimDesk.

Escalated tickets have been flagged for urgent attention. They are still
active work — they count toward workload and are not terminal — but they
have high priority and require different handling than normal active tickets.

Business rules:
- Tickets can be escalated from in_progress
- Escalated tickets can be de-escalated back to in_progress, or closed directly
- Escalated tickets ARE active work and SHOULD be counted in workload metrics
- Escalated tickets are NOT terminal — they can be de-escalated or closed
- Notifications for escalated transitions should be differentiated from normal
  (e.g. urgent/escalated notification, not the same text as regular transitions)
- Analytics should track escalated status separately (is_escalated flag)
- There should be "escalate" and "de_escalate" permission actions
"""

# ── Integration tests ──────────────────────────────────────

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

def test_01_escalated_exists():
    check("test_01", "escalated" in ALL_STATUSES,
          f"ALL_STATUSES={list(ALL_STATUSES)}")

def test_02_escalated_not_in_active():
    check("test_02", "escalated" not in ACTIVE_STATUSES,
          f"ACTIVE_STATUSES={list(ACTIVE_STATUSES)}")

def test_03_escalated_not_terminal():
    check("test_03", "escalated" not in TERMINAL_STATUSES,
          f"TERMINAL_STATUSES={list(TERMINAL_STATUSES)}")

def test_04_in_progress_to_escalated():
    trans = VALID_TRANSITIONS.get("in_progress", [])
    check("test_04", "escalated" in list(trans),
          f"in_progress transitions={list(trans)}")

def test_05_escalated_to_in_progress():
    trans = VALID_TRANSITIONS.get("escalated", [])
    check("test_05", "in_progress" in list(trans),
          f"escalated transitions={list(trans)}")

def test_06_escalated_to_closed():
    trans = VALID_TRANSITIONS.get("escalated", [])
    check("test_06", "closed" in list(trans),
          f"escalated transitions={list(trans)}")

def test_07_is_active_false():
    check("test_07", is_active("escalated") == False,
          "is_active('escalated') should be False (escalated is its own group)")

def test_08_is_terminal_false():
    check("test_08", is_terminal("escalated") == False,
          "is_terminal('escalated') should be False")

def test_09_existing_preserved():
    original = {"open", "in_progress", "on_hold", "closed", "resolved", "archived"}
    all_s = set(ALL_STATUSES)
    missing = original - all_s
    check("test_09", len(missing) == 0, f"missing: {missing}")

def test_10_escalated_statuses_exists():
    has_esc = hasattr(sys.modules[__name__], 'ESCALATED_STATUSES') or \\
              'ESCALATED_STATUSES' in dir(sys.modules['workflow'])
    if has_esc:
        from workflow import ESCALATED_STATUSES
        check("test_10", "escalated" in ESCALATED_STATUSES,
              f"ESCALATED_STATUSES={list(ESCALATED_STATUSES)}")
    else:
        check("test_10", False, "ESCALATED_STATUSES not defined in workflow")

def test_11_is_escalated_helper():
    try:
        from workflow import is_escalated
        check("test_11", is_escalated("escalated") == True,
              "is_escalated('escalated') should be True")
    except ImportError:
        check("test_11", False, "is_escalated not defined in workflow")

def test_12_notifications_escalated_differentiated():
    try:
        from notifications import notify_transition, subscribe
        subscribe("t1", "watcher@test.com")
        result = notify_transition("t1", "in_progress", "escalated")
        if result is not None and len(result) > 0:
            msg = result[0].lower()
            is_differentiated = ("escalat" in msg or "urgent" in msg or
                                 "priority" in msg or "high" in msg)
            check("test_12", is_differentiated,
                  f"notification not differentiated: {result[0]}")
        else:
            check("test_12", False, f"no notification returned: {result}")
    except ImportError:
        check("test_12", False, "notifications module not found")
    except Exception as e:
        check("test_12", False, str(e))

def test_13_notifications_deescalate():
    try:
        from notifications import notify_transition, subscribe
        subscribe("t2", "watcher@test.com")
        result = notify_transition("t2", "escalated", "in_progress")
        check("test_13", result is not None and len(result) > 0,
              f"notify_transition returned {result}")
    except ImportError:
        check("test_13", False, "notifications module not found")
    except Exception as e:
        check("test_13", False, str(e))

def test_14_analytics_tags_escalated():
    try:
        from analytics import track_transition
        event = track_transition("t1", "in_progress", "escalated")
        if isinstance(event, dict):
            has_esc = event.get("is_escalated") == True
            not_terminal = event.get("is_terminal") != True
            check("test_14", has_esc and not_terminal,
                  f"event={event}")
        else:
            check("test_14", False, f"track_transition returned {type(event)}")
    except ImportError:
        check("test_14", False, "analytics module not found")
    except Exception as e:
        check("test_14", False, str(e))

def test_15_escalate_permission_exists():
    try:
        from permissions import PERMISSION_RULES
        check("test_15", "escalate" in PERMISSION_RULES,
              f"PERMISSION_RULES keys={list(PERMISSION_RULES.keys())}")
    except ImportError:
        check("test_15", False, "permissions module not found")
    except Exception as e:
        check("test_15", False, str(e))

def test_16_de_escalate_permission_exists():
    try:
        from permissions import PERMISSION_RULES
        check("test_16", "de_escalate" in PERMISSION_RULES,
              f"PERMISSION_RULES keys={list(PERMISSION_RULES.keys())}")
    except ImportError:
        check("test_16", False, "permissions module not found")
    except Exception as e:
        check("test_16", False, str(e))

def test_17_escalated_counts_as_work():
    try:
        from analytics import active_ticket_count
        count = active_ticket_count(["open", "escalated", "closed", "in_progress"])
        check("test_17", count >= 2,
              f"expected >=2 work tickets (open + escalated + in_progress), got {count}")
    except ImportError:
        check("test_17", False, "analytics module not found")
    except Exception as e:
        check("test_17", False, str(e))

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
                    "test_06", "test_07", "test_08", "test_09"]
OBLIGATION_TESTS = ["test_10", "test_11", "test_12", "test_13",
                    "test_14", "test_15", "test_16", "test_17"]


# ── Graph conditions ────────────────────────────────────────

GRAPH_PROMPT_BASE = f"""\
{ESCALATED_DESCRIPTION}

You are modifying the ClaimDesk domain by editing its claim graph.
The graph already contains the base domain (statuses, transitions,
roles, permissions, effects).

Use the available tools to explore the current domain, make all necessary
changes, check obligations across all modules, and project the results.

You MUST call project_all_to_disk at the end to save the updated Python.
Do NOT write Python code. Edit the graph; Python is projected automatically.
"""

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


def make_mcp_config(output_dir, mode="label"):
    projected_dir = output_dir / "projected"
    projected_dir.mkdir(exist_ok=True)
    config = {
        "mcpServers": {
            "claimdesk": {
                "command": "racket",
                "args": [str(MCP_SERVER), "--output-dir", str(projected_dir),
                         "--mode", mode],
            }
        }
    }
    path = output_dir / "mcp-config.json"
    path.write_text(json.dumps(config))
    return path, projected_dir


def launch_graph_agent(prompt, output_dir, label, mode="label"):
    mcp_config_path, projected_dir = make_mcp_config(output_dir, mode)
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
    (output_dir / f"agent-{label}.json").write_text(
        json.dumps(agent_output, indent=2))

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
        "agent_result": agent_output.get("result", "")[:500],
    }


def run_graph_label(run_id):
    output_dir = SCRIPT_DIR / "output" / f"e31-graph_label-{run_id}"
    output_dir.mkdir(parents=True, exist_ok=True)
    return launch_graph_agent(GRAPH_PROMPT_BASE, output_dir, "single",
                              mode="label")


def run_graph_validated(run_id):
    output_dir = SCRIPT_DIR / "output" / f"e31-graph_validated-{run_id}"
    output_dir.mkdir(parents=True, exist_ok=True)
    return launch_graph_agent(GRAPH_PROMPT_BASE, output_dir, "single",
                              mode="validated")


def run_graph_properties(run_id):
    output_dir = SCRIPT_DIR / "output" / f"e31-graph_properties-{run_id}"
    output_dir.mkdir(parents=True, exist_ok=True)
    return launch_graph_agent(GRAPH_PROMPT_BASE, output_dir, "single",
                              mode="properties")


# ── File condition ──────────────────────────────────────────

FILE_SINGLE_PROMPT = f"""\
{ESCALATED_DESCRIPTION}

You are modifying the ClaimDesk helpdesk application. The workspace
contains the Python source files: workflow.py, permissions.py,
notifications.py, analytics.py (plus models.py and core.py).

Read the existing code to understand the architecture, then make all
necessary changes across the codebase. Make sure escalated is handled
consistently everywhere that status matters.
"""


def setup_file_workspace(workspace_dir):
    codebase = E24B_DIR / "codebase"
    for f in ["models.py", "core.py", "workflow.py"]:
        shutil.copy(codebase / f, workspace_dir / f)

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
    output_dir = SCRIPT_DIR / "output" / f"e31-file_single-{run_id}"
    output_dir.mkdir(parents=True, exist_ok=True)
    workspace = output_dir / "workspace"
    workspace.mkdir(exist_ok=True)
    setup_file_workspace(workspace)
    return launch_file_agent(FILE_SINGLE_PROMPT, workspace, "single")


# ── Test runner ─────────────────────────────────────────────

def run_tests(modules):
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


# ── Main ────────────────────────────────────────────────────

CONDITION_RUNNERS = {
    "graph_label": run_graph_label,
    "graph_validated": run_graph_validated,
    "graph_properties": run_graph_properties,
    "file_single": run_file_single,
}


def run_experiment(condition, num_runs):
    print(f"\n{'='*60}")
    print(f"  E31: {condition} — {num_runs} runs")
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
            test_result = run_tests(modules)
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
            "agent_result_snippet": run_result.get("agent_result", "")[:300],
            **test_result,
        }
        all_results.append(run_data)

        print(f"  elapsed: {run_result.get('elapsed', 0):.1f}s  cost: ${run_result.get('cost', 0):.3f}")
        print(f"  tests: {test_result['passed']}/{test_result['total']}")
        print(f"  structural bugs: {test_result['structural_bugs']}/{len(STRUCTURAL_TESTS)}")
        print(f"  obligation bugs: {test_result['obligation_bugs']}/{len(OBLIGATION_TESTS)}")
        print()

    total_struct = sum(r.get("structural_bugs", 0) for r in all_results)
    total_oblig = sum(r.get("obligation_bugs", 0) for r in all_results)

    summary = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "experiment": "E31",
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

    outfile = SCRIPT_DIR / f"results-e31-{condition}.json"
    outfile.write_text(json.dumps(summary, indent=2, default=str))
    print(f"Results: {outfile}")
    print(f"Structural: {total_struct}/{num_runs * len(STRUCTURAL_TESTS)}")
    print(f"Obligation: {total_oblig}/{num_runs * len(OBLIGATION_TESTS)}")

    return summary


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="E31 experiment runner")
    parser.add_argument("condition",
                        choices=list(CONDITION_RUNNERS.keys()) + ["all", "graph_all"],
                        help="Which condition(s) to run")
    parser.add_argument("--runs", type=int, default=NUM_RUNS)
    args = parser.parse_args()

    if args.condition == "all":
        for cond in CONDITION_RUNNERS:
            run_experiment(cond, args.runs)
    elif args.condition == "graph_all":
        for cond in ["graph_label", "graph_validated", "graph_properties"]:
            run_experiment(cond, args.runs)
    else:
        run_experiment(args.condition, args.runs)

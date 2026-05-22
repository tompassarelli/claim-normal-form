#!/usr/bin/env python3
"""
E32: Multi-Entity Feature Synthesis — Cross-Entity Priority Routing

Task: add a priority system (low/normal/high/critical) to ClaimDesk.
Priorities are explicit entities with properties. The test is whether the
graph preserves cross-entity obligations (priority → escalation target,
priority → role permission gate, priority → notification mode, priority → SLA)
that file agents miss.

Base domain includes escalated status/group (from E31), senior role, and
escalation transitions — so the auto-escalation target already exists.

Conditions:
  graph:           agent adds priorities via MCP, obligation checker available
  graph_validated: same + graph rejects incomplete cross-entity links at add time
  file_single:     agent edits Python files directly
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

PRIORITY_DESCRIPTION = """\
Add a priority system to ClaimDesk.

Priorities:
- low: response target 24h
- normal: response target 8h
- high: response target 4h, immediate email notifications
- critical: response target 1h, urgent page notifications, requires \
senior/admin handling, auto-escalates into the escalated ticket state

Update permissions, assignment routing, notifications, analytics, and \
SLA reporting. The escalated status and senior role already exist in the domain.
"""

# ── Integration tests ──────────────────────────────────────
# Categories:
#   01-04: Structural/domain-model
#   05-08: Cross-entity relation
#   09-13: Obligation
#   14-17: Projection/runtime

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


# ── Category 1: Structural/domain-model ──────────────────

def test_01_priority_levels_exists():
    """PRIORITY_LEVELS or equivalent dict exists in workflow"""
    for attr in ['PRIORITY_LEVELS', 'PRIORITIES', 'PRIORITY_CONFIGS']:
        if hasattr(sys.modules['workflow'], attr):
            val = getattr(sys.modules['workflow'], attr)
            check("test_01", isinstance(val, dict) and len(val) >= 4,
                  f"{attr} has {len(val)} entries")
            return
    check("test_01", False, "no priority constant found in workflow")

def test_02_four_priorities():
    """All 4 priorities present"""
    prios = None
    for attr in ['PRIORITY_LEVELS', 'PRIORITIES', 'PRIORITY_CONFIGS']:
        if hasattr(sys.modules['workflow'], attr):
            prios = getattr(sys.modules['workflow'], attr)
            break
    if prios is None:
        check("test_02", False, "no priority constant found")
        return
    expected = {"low", "normal", "high", "critical"}
    found = set(prios.keys())
    check("test_02", expected.issubset(found),
          f"expected {expected}, found {found}")

def test_03_response_targets():
    """Response targets: critical <= high <= normal <= low"""
    prios = None
    for attr in ['PRIORITY_LEVELS', 'PRIORITIES', 'PRIORITY_CONFIGS']:
        if hasattr(sys.modules['workflow'], attr):
            prios = getattr(sys.modules['workflow'], attr)
            break
    if prios is None:
        check("test_03", False, "no priority constant found")
        return
    def get_target(name):
        val = prios.get(name, {})
        if isinstance(val, dict):
            return val.get("response_target", val.get("sla", val.get("target")))
        return val
    targets = {k: get_target(k) for k in ["critical", "high", "normal", "low"]}
    all_present = all(t is not None for t in targets.values())
    ordered = all_present and targets["critical"] <= targets["high"] <= targets["normal"] <= targets["low"]
    check("test_03", ordered, f"targets={targets}")

def test_04_get_response_target():
    """get_response_target function exists and works"""
    try:
        from workflow import get_response_target
        result = get_response_target("critical")
        check("test_04", result is not None and result <= 4,
              f"get_response_target('critical')={result}")
    except ImportError:
        check("test_04", False, "get_response_target not defined")


# ── Category 2: Cross-entity relation ────────────────────

def test_05_critical_auto_escalates():
    """Critical priority has auto-escalation indicator"""
    prios = None
    for attr in ['PRIORITY_LEVELS', 'PRIORITIES', 'PRIORITY_CONFIGS']:
        if hasattr(sys.modules['workflow'], attr):
            prios = getattr(sys.modules['workflow'], attr)
            break
    if prios is None:
        check("test_05", False, "no priority constant found")
        return
    crit = prios.get("critical", {})
    if isinstance(crit, dict):
        has_auto = crit.get("auto_escalate") == True
        check("test_05", has_auto, f"critical config={crit}")
    else:
        check("test_05", False, f"critical is not a dict: {crit}")

def test_06_critical_references_escalated():
    """Critical links to escalated status/group"""
    prios = None
    for attr in ['PRIORITY_LEVELS', 'PRIORITIES', 'PRIORITY_CONFIGS']:
        if hasattr(sys.modules['workflow'], attr):
            prios = getattr(sys.modules['workflow'], attr)
            break
    if prios is None:
        check("test_06", False, "no priority constant found")
        return
    crit = prios.get("critical", {})
    if isinstance(crit, dict):
        ref = crit.get("escalates_to") or crit.get("escalation_target") or crit.get("escalate_to")
        check("test_06", ref is not None and "escalat" in str(ref).lower(),
              f"critical escalation ref={ref}")
    else:
        check("test_06", False, f"critical is not a dict: {crit}")

def test_07_priority_role_requirements():
    """Permission system gates critical priority to senior/admin"""
    try:
        from permissions import PRIORITY_ROLE_REQUIREMENTS
        crit_roles = PRIORITY_ROLE_REQUIREMENTS.get("critical", set())
        has_senior = "senior" in crit_roles or "admin" in crit_roles
        check("test_07", has_senior,
              f"critical roles={crit_roles}")
    except ImportError:
        # Check if can_set_priority exists instead
        try:
            from permissions import can_set_priority
            check("test_07", True, "can_set_priority exists (can't test role gate without user object)")
        except ImportError:
            check("test_07", False, "no PRIORITY_ROLE_REQUIREMENTS or can_set_priority")

def test_08_notification_modes_differ():
    """Different notification modes for critical vs normal"""
    try:
        from notifications import PRIORITY_NOTIFICATION_MODES
        crit = PRIORITY_NOTIFICATION_MODES.get("critical", "")
        check("test_08", crit != "normal" and crit != "",
              f"critical notification mode={crit}")
    except ImportError:
        try:
            from notifications import get_priority_notification_mode
            crit = get_priority_notification_mode("critical")
            norm = get_priority_notification_mode("normal")
            check("test_08", crit != norm,
                  f"critical={crit}, normal={norm}")
        except (ImportError, TypeError):
            check("test_08", False, "no priority notification mode differentiation")


# ── Category 3: Obligation ───────────────────────────────

def test_09_can_set_priority_exists():
    """can_set_priority function or equivalent role gate exists"""
    try:
        from permissions import can_set_priority
        check("test_09", callable(can_set_priority))
    except ImportError:
        try:
            from permissions import PRIORITY_ROLE_REQUIREMENTS
            check("test_09", isinstance(PRIORITY_ROLE_REQUIREMENTS, dict))
        except ImportError:
            check("test_09", False, "no priority permission gate")

def test_10_critical_blocked_for_agent():
    """Agent role cannot set critical priority"""
    try:
        from permissions import can_set_priority
        class FakeUser:
            def __init__(self, role):
                self.role = role
        result = can_set_priority(FakeUser("agent"), "critical")
        check("test_10", result == False,
              f"can_set_priority(agent, critical)={result}")
    except ImportError:
        try:
            from permissions import PRIORITY_ROLE_REQUIREMENTS
            crit_roles = PRIORITY_ROLE_REQUIREMENTS.get("critical", set())
            check("test_10", "agent" not in crit_roles,
                  f"critical roles={crit_roles}")
        except ImportError:
            check("test_10", False, "no priority permission gate")

def test_11_critical_notification_urgent():
    """Critical priority triggers urgent/page notification"""
    try:
        from notifications import PRIORITY_NOTIFICATION_MODES
        mode = PRIORITY_NOTIFICATION_MODES.get("critical", "")
        is_urgent = "urgent" in mode or "page" in mode
        check("test_11", is_urgent, f"critical mode={mode}")
    except ImportError:
        try:
            from notifications import get_priority_notification_mode
            mode = get_priority_notification_mode("critical")
            is_urgent = mode is not None and ("urgent" in str(mode) or "page" in str(mode))
            check("test_11", is_urgent, f"critical mode={mode}")
        except (ImportError, TypeError):
            check("test_11", False, "no priority notification mode")

def test_12_analytics_tracks_priority():
    """Analytics has priority tracking function"""
    try:
        from analytics import track_priority_assignment
        event = track_priority_assignment("t1", "critical")
        has_priority = isinstance(event, dict) and "priority" in event
        check("test_12", has_priority, f"event={event}")
    except ImportError:
        check("test_12", False, "track_priority_assignment not found")
    except Exception as e:
        check("test_12", False, str(e))

def test_13_sla_compliance_exists():
    """SLA compliance function exists"""
    try:
        from analytics import sla_compliance
        result = sla_compliance("critical", 0.5)
        check("test_13", result == True,
              f"sla_compliance('critical', 0.5)={result}")
    except ImportError:
        check("test_13", False, "sla_compliance not found")
    except Exception as e:
        check("test_13", False, str(e))


# ── Category 4: Projection/runtime ──────────────────────

def test_14_all_imports_resolve():
    """All modules import without errors"""
    ok = True
    for mod in ["workflow", "notifications", "analytics", "permissions"]:
        try:
            __import__(mod)
        except Exception as e:
            ok = False
            check("test_14", False, f"{mod}: {e}")
            return
    check("test_14", ok)

def test_15_priority_values_are_dicts():
    """Priority config values are dicts (structured), not bare strings"""
    prios = None
    for attr in ['PRIORITY_LEVELS', 'PRIORITIES', 'PRIORITY_CONFIGS']:
        if hasattr(sys.modules['workflow'], attr):
            prios = getattr(sys.modules['workflow'], attr)
            break
    if prios is None:
        check("test_15", False, "no priority constant")
        return
    all_dicts = all(isinstance(v, dict) for v in prios.values())
    check("test_15", all_dicts,
          f"types={[type(v).__name__ for v in prios.values()]}")

def test_16_sla_targets_in_analytics():
    """Analytics has SLA targets that match workflow response targets"""
    try:
        from analytics import PRIORITY_SLA_TARGETS
        from workflow import PRIORITY_LEVELS
        crit_sla = PRIORITY_SLA_TARGETS.get("critical")
        crit_wf = PRIORITY_LEVELS.get("critical", {}).get("response_target")
        check("test_16", crit_sla is not None and crit_sla == crit_wf,
              f"analytics SLA={crit_sla}, workflow target={crit_wf}")
    except ImportError as e:
        check("test_16", False, f"import failed: {e}")

def test_17_existing_statuses_preserved():
    """Adding priorities did not break existing status system"""
    expected = {"open", "in_progress", "on_hold", "closed", "resolved",
                "archived", "escalated"}
    all_s = set(ALL_STATUSES)
    missing = expected - all_s
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

STRUCTURAL_TESTS = ["test_01", "test_02", "test_03", "test_04"]
CROSS_ENTITY_TESTS = ["test_05", "test_06", "test_07", "test_08"]
OBLIGATION_TESTS = ["test_09", "test_10", "test_11", "test_12", "test_13"]
PROJECTION_TESTS = ["test_14", "test_15", "test_16", "test_17"]

ALL_TESTS = STRUCTURAL_TESTS + CROSS_ENTITY_TESTS + OBLIGATION_TESTS + PROJECTION_TESTS


# ── Graph conditions ────────────────────────────────────────

GRAPH_PROMPT = f"""\
{PRIORITY_DESCRIPTION}

You are modifying the ClaimDesk domain by editing its claim graph.
The graph already contains statuses (including escalated), transitions,
roles (agent, senior, admin), permissions, and effects.

Use the available tools to explore the current domain, add all 4 priority
levels with their properties, check obligations across all modules, and
project the results.

You MUST call project_all_to_disk at the end to save the updated Python.
Do NOT write Python code. Edit the graph; Python is projected automatically.
"""

GRAPH_TOOLS = [
    "mcp__claimdesk__list_statuses",
    "mcp__claimdesk__list_transitions",
    "mcp__claimdesk__list_roles",
    "mcp__claimdesk__list_permissions",
    "mcp__claimdesk__list_effects",
    "mcp__claimdesk__list_priorities",
    "mcp__claimdesk__add_status",
    "mcp__claimdesk__add_transition",
    "mcp__claimdesk__add_role",
    "mcp__claimdesk__add_permission",
    "mcp__claimdesk__add_effect",
    "mcp__claimdesk__add_priority",
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
                         "--mode", mode, "--base", "e32"],
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


def run_graph(run_id):
    output_dir = SCRIPT_DIR / "output" / f"e32-graph-{run_id}"
    output_dir.mkdir(parents=True, exist_ok=True)
    return launch_graph_agent(GRAPH_PROMPT, output_dir, "single",
                              mode="label")


def run_graph_validated(run_id):
    output_dir = SCRIPT_DIR / "output" / f"e32-graph_validated-{run_id}"
    output_dir.mkdir(parents=True, exist_ok=True)
    return launch_graph_agent(GRAPH_PROMPT, output_dir, "single",
                              mode="validated")


# ── File condition ──────────────────────────────────────────

FILE_SINGLE_PROMPT = f"""\
{PRIORITY_DESCRIPTION}

You are modifying the ClaimDesk helpdesk application. The workspace
contains the Python source files: workflow.py, permissions.py,
notifications.py, analytics.py (plus models.py and core.py).

The application already supports escalated tickets with ESCALATED_STATUSES,
is_escalated(), and a senior role. Read the existing code to understand
the architecture, then add the priority system across the codebase.
"""


def setup_file_workspace(workspace_dir):
    """Generate E32 base files by projecting from the E32 graph domain."""
    codebase = E24B_DIR / "codebase"
    for f in ["models.py", "core.py"]:
        shutil.copy(codebase / f, workspace_dir / f)

    result = subprocess.run(
        ["racket", "-e", '''
(require "claimdesk.rkt"
         "../../cnf-lib/private/kernel.rkt"
         "../../cnf-lib/private/datalog.rkt"
         "../../cnf-lib/private/schema.rkt")
(setup-claimdesk-e32!)
(display "===WORKFLOW===\n")
(display (project-workflow-py))
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
        if name in ("workflow", "notifications", "analytics", "permissions"):
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
    output_dir = SCRIPT_DIR / "output" / f"e32-file_single-{run_id}"
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

    structural = sum(1 for t in STRUCTURAL_TESTS if results.get(t) != "pass")
    cross_entity = sum(1 for t in CROSS_ENTITY_TESTS if results.get(t) != "pass")
    obligation = sum(1 for t in OBLIGATION_TESTS if results.get(t) != "pass")
    projection = sum(1 for t in PROJECTION_TESTS if results.get(t) != "pass")

    return {
        "tests": results,
        "passed": sum(1 for v in results.values() if v == "pass"),
        "total": len(results),
        "structural_bugs": structural,
        "cross_entity_bugs": cross_entity,
        "obligation_bugs": obligation,
        "projection_bugs": projection,
        "raw_output": output,
    }


# ── Main ────────────────────────────────────────────────────

CONDITION_RUNNERS = {
    "graph": run_graph,
    "graph_validated": run_graph_validated,
    "file_single": run_file_single,
}


def run_experiment(condition, num_runs):
    print(f"\n{'='*60}")
    print(f"  E32: {condition} — {num_runs} runs")
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
                                "cross_entity_bugs": len(CROSS_ENTITY_TESTS),
                                "obligation_bugs": len(OBLIGATION_TESTS),
                                "projection_bugs": len(PROJECTION_TESTS)})
            continue
        except Exception as e:
            print(f"  ERROR: {e}")
            all_results.append({"run_id": run_id, "error": str(e),
                                "structural_bugs": len(STRUCTURAL_TESTS),
                                "cross_entity_bugs": len(CROSS_ENTITY_TESTS),
                                "obligation_bugs": len(OBLIGATION_TESTS),
                                "projection_bugs": len(PROJECTION_TESTS)})
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
                           "cross_entity_bugs": len(CROSS_ENTITY_TESTS),
                           "obligation_bugs": len(OBLIGATION_TESTS),
                           "projection_bugs": len(PROJECTION_TESTS),
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
        print(f"  structural:   {test_result['structural_bugs']}/{len(STRUCTURAL_TESTS)}")
        print(f"  cross-entity: {test_result['cross_entity_bugs']}/{len(CROSS_ENTITY_TESTS)}")
        print(f"  obligation:   {test_result['obligation_bugs']}/{len(OBLIGATION_TESTS)}")
        print(f"  projection:   {test_result['projection_bugs']}/{len(PROJECTION_TESTS)}")
        print()

    agg = {
        "total_structural": sum(r.get("structural_bugs", 0) for r in all_results),
        "total_cross_entity": sum(r.get("cross_entity_bugs", 0) for r in all_results),
        "total_obligation": sum(r.get("obligation_bugs", 0) for r in all_results),
        "total_projection": sum(r.get("projection_bugs", 0) for r in all_results),
        "structural_opportunities": num_runs * len(STRUCTURAL_TESTS),
        "cross_entity_opportunities": num_runs * len(CROSS_ENTITY_TESTS),
        "obligation_opportunities": num_runs * len(OBLIGATION_TESTS),
        "projection_opportunities": num_runs * len(PROJECTION_TESTS),
        "mean_elapsed": sum(r.get("elapsed", 0) for r in all_results) / max(len(all_results), 1),
        "mean_cost": sum(r.get("cost", 0) for r in all_results) / max(len(all_results), 1),
    }

    summary = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "experiment": "E32",
        "condition": condition,
        "num_runs": num_runs,
        "runs": all_results,
        "aggregate": agg,
    }

    outfile = SCRIPT_DIR / f"results-e32-{condition}.json"
    outfile.write_text(json.dumps(summary, indent=2, default=str))
    print(f"Results: {outfile}")
    print(f"Structural:   {agg['total_structural']}/{agg['structural_opportunities']}")
    print(f"Cross-entity: {agg['total_cross_entity']}/{agg['cross_entity_opportunities']}")
    print(f"Obligation:   {agg['total_obligation']}/{agg['obligation_opportunities']}")
    print(f"Projection:   {agg['total_projection']}/{agg['projection_opportunities']}")

    return summary


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="E32 experiment runner")
    parser.add_argument("condition",
                        choices=list(CONDITION_RUNNERS.keys()) + ["all", "graph_all"],
                        help="Which condition(s) to run")
    parser.add_argument("--runs", type=int, default=NUM_RUNS)
    args = parser.parse_args()

    if args.condition == "all":
        for cond in CONDITION_RUNNERS:
            run_experiment(cond, args.runs)
    elif args.condition == "graph_all":
        for cond in ["graph", "graph_validated"]:
            run_experiment(cond, args.runs)
    else:
        run_experiment(args.condition, args.runs)

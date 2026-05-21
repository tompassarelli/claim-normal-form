#!/usr/bin/env python3
"""E21: Graph-Native Agent Race

Head-to-head: text agent (files + shell + eval helper) vs graph agent (MCP tools).
Same task, same model, same time limit. Different tooling.

Task: implement safe-div, wire it into payroll, verify, query errors, rename.

Usage:
    python runner.py              # Run both agents sequentially
    python runner.py --text-only  # Text agent only
    python runner.py --graph-only # Graph agent only
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()
CNF_ROOT = SCRIPT_DIR.parent.parent
MODEL = "sonnet"
TIMEOUT = 300  # 5 minutes per agent

STARTING_PROGRAM = (SCRIPT_DIR / "program.cnf").read_text()

# ════════════════════════════════════════════════════════════════════
# Shared task — identical for both agents
# ════════════════════════════════════════════════════════════════════

TASK_PREAMBLE = """\
You are given a 5-function payroll program in a tiny functional language.
The language supports: defn, +, -, *, /, =, if, and function calls.

Starting program:
```
{program}
```

TASK: Implement safe division and wire it into the payroll system.

Complete these steps IN ORDER. Report evidence for each step.

1. PARSE: Load the program. Confirm 5 functions parsed.

2. VERIFY BASELINE: Evaluate split-pay(1000, 4). Expected: 250.

3. REPRODUCE BUG: Evaluate split-pay(1000, 0). It will crash with
   division by zero. Report the error.

4. ADD SAFE-DIV: Add this function:
   (defn safe-div [a b]
     (if (= b 0) 0 (/ a b)))

5. WIRE IT IN: Modify split-pay to use safe-div instead of /:
   (defn split-pay [total parts]
     (safe-div total parts))

6. VERIFY FIX:
   a) split-pay(1000, 4) should still return 250
   b) split-pay(1000, 0) should return 0 (no crash)
   c) after-split(1000, 4, 50) should return 200

7. QUERY DEPENDENCIES: Which functions depend on safe-div?
   Expected: split-pay depends on safe-div.

8. RENAME: Rename safe-div to guarded-div.
   Verify split-pay's rendering shows guarded-div (not safe-div).

9. VERIFY AFTER RENAME: Evaluate after-split(1000, 4, 50) = 200 still works.

10. ERROR HISTORY: Show that the failed evaluation from step 3 is still
    queryable. Report its status and error reason.

For each step, report: what you did, what result you got, pass/fail.
"""

# ════════════════════════════════════════════════════════════════════
# Text agent setup
# ════════════════════════════════════════════════════════════════════

TEXT_PROMPT = TASK_PREAMBLE.format(program=STARTING_PROGRAM) + """
TOOLS: You have a working directory with:
- program.cnf — the source file (edit this to add/modify functions)
- eval-helper.rkt — evaluation tool with these commands:
    racket eval-helper.rkt eval program.cnf <fn-name> <arg1> <arg2> ...
    racket eval-helper.rkt deps program.cnf
    racket eval-helper.rkt render program.cnf
    racket eval-helper.rkt runs program.cnf <fn-name> <arg1> <arg2> ...

The eval-helper re-parses the file each time, so edit program.cnf first,
then run eval commands.

For step 8 (rename): manually find-and-replace in program.cnf.
For step 10 (error history): the eval-helper re-parses fresh each run,
so prior errors are NOT retained. Report what you can.

Work in the current directory. Do not create new files unless needed.
"""

# ════════════════════════════════════════════════════════════════════
# Graph agent setup
# ════════════════════════════════════════════════════════════════════

GRAPH_PROMPT = TASK_PREAMBLE.format(program=STARTING_PROGRAM) + """
TOOLS: You have MCP tools connected to a CNF claim graph server.

Key tools:
- reset: Initialize a fresh workspace
- parse_program: Parse source into the graph (language: "cnf")
- evaluate: Run a function by name, get result as queryable claims
- query: Run Datalog queries (e.g. fn-depends-on)
- render: Render a function or program back to text
- rename: Rename an entity, all references update automatically
- add_function: Add a new function to the graph
- modify_function: Change a function's implementation
- inspect: Examine any entity's claims

For step 3 (reproduce bug): evaluate will record the error as a queryable
eval-run entity with status and reason claims.

For step 8 (rename): use the rename tool — call sites update automatically.

For step 10 (error history): query for eval-run entities with status="error".
The failed run from step 3 persists in the graph.

Start with reset, then parse_program with the starting program.
"""


def launch_text_agent():
    """Launch text agent with file access and shell."""
    ws = Path(tempfile.mkdtemp(prefix="e21-text-"))
    shutil.copy(SCRIPT_DIR / "program.cnf", ws / "program.cnf")
    shutil.copy(SCRIPT_DIR / "eval-helper.rkt", ws / "eval-helper.rkt")

    print(f"  Text agent workspace: {ws}")
    start = time.monotonic()
    try:
        result = subprocess.run(
            ["claude", "-p", "--model", MODEL,
             "--dangerously-skip-permissions",
             "--add-dir", str(ws)],
            input=TEXT_PROMPT,
            capture_output=True, text=True, timeout=TIMEOUT,
        )
        elapsed = time.monotonic() - start
        transcript = result.stdout or ""
        return {
            "agent": "text",
            "elapsed": elapsed,
            "transcript": transcript,
            "error": None if result.returncode == 0 else result.stderr[:500],
            "workspace": str(ws),
        }
    except subprocess.TimeoutExpired:
        elapsed = time.monotonic() - start
        return {
            "agent": "text",
            "elapsed": elapsed,
            "transcript": "",
            "error": "timeout",
            "workspace": str(ws),
        }


def launch_graph_agent():
    """Launch graph agent with MCP tools."""
    mcp_config = str(SCRIPT_DIR / "mcp-config.json")

    print(f"  Graph agent MCP config: {mcp_config}")
    start = time.monotonic()
    try:
        result = subprocess.run(
            ["claude", "-p", "--model", MODEL,
             "--dangerously-skip-permissions",
             "--mcp-config", mcp_config],
            input=GRAPH_PROMPT,
            capture_output=True, text=True, timeout=TIMEOUT,
        )
        elapsed = time.monotonic() - start
        transcript = result.stdout or ""
        return {
            "agent": "graph",
            "elapsed": elapsed,
            "transcript": transcript,
            "error": None if result.returncode == 0 else result.stderr[:500],
        }
    except subprocess.TimeoutExpired:
        elapsed = time.monotonic() - start
        return {
            "agent": "graph",
            "elapsed": elapsed,
            "transcript": "",
            "error": "timeout",
        }


# ════════════════════════════════════════════════════════════════════
# Scoring
# ════════════════════════════════════════════════════════════════════

CHECKS = [
    ("step1_parse", "5 functions", "parse confirmed"),
    ("step2_baseline", "250", "split-pay baseline"),
    ("step3_error", "division by zero", "error reproduced"),
    ("step4_safediv", "safe-div", "safe-div added"),
    ("step5_wire", "safe-div", "split-pay wired"),
    ("step6a_verify", "250", "split-pay still correct"),
    ("step6b_zero", "split-pay(1000, 0)", "zero case tested"),
    ("step7_deps", "depends", "dependency query"),
    ("step8_rename", "guarded-div", "rename propagated"),
    ("step9_postrename", "200", "eval after rename"),
    ("step10_history", "status", "error history reported"),
]


def score_transcript(transcript):
    """Simple keyword scoring — not authoritative, just indicative."""
    t = transcript.lower()
    results = {}
    for check_id, keyword, desc in CHECKS:
        results[check_id] = keyword.lower() in t
    return results


def print_results(text_result, graph_result):
    w = 72
    print()
    print("═" * w)
    print("  E21: GRAPH-NATIVE AGENT RACE — RESULTS")
    print("═" * w)

    print(f"\n  {'':30} {'Text':>14} {'Graph':>14}")
    print("  " + "─" * (w - 4))

    if text_result:
        print(f"  {'Wall time':<30} {text_result['elapsed']:>13.1f}s", end="")
    else:
        print(f"  {'Wall time':<30} {'—':>14}", end="")
    if graph_result:
        print(f" {graph_result['elapsed']:>13.1f}s")
    else:
        print(f" {'—':>14}")

    if text_result and text_result.get("error"):
        print(f"  {'Text error':<30} {text_result['error'][:40]}")
    if graph_result and graph_result.get("error"):
        print(f"  {'Graph error':<30} {graph_result['error'][:40]}")

    # Score
    text_score = score_transcript(text_result["transcript"]) if text_result else {}
    graph_score = score_transcript(graph_result["transcript"]) if graph_result else {}

    print(f"\n  Step checks (keyword presence in transcript):")
    print(f"  {'Check':<35} {'Text':>10} {'Graph':>10}")
    print("  " + "─" * (w - 4))

    text_pass = graph_pass = 0
    for check_id, _, desc in CHECKS:
        t = text_score.get(check_id, False)
        g = graph_score.get(check_id, False)
        if t: text_pass += 1
        if g: graph_pass += 1
        t_str = "PASS" if t else "FAIL"
        g_str = "PASS" if g else "FAIL"
        print(f"  {desc:<35} {t_str:>10} {g_str:>10}")

    print("  " + "─" * (w - 4))
    print(f"  {'TOTAL':<35} {text_pass:>10}/{len(CHECKS)} {graph_pass:>10}/{len(CHECKS)}")

    # Structural advantage
    print(f"\n  Key differentiators:")
    print(f"      Step 8 (rename): graph=semantic, text=find-and-replace")
    print(f"      Step 10 (error history): graph=queryable claims, text=not retained")
    print()


def main():
    w = 72
    print("═" * w)
    print("  E21: Graph-Native Agent Race")
    print()
    print(f"  Model: {MODEL}, Timeout: {TIMEOUT}s")
    print("  Text:  files + shell + eval-helper.rkt")
    print("  Graph: MCP tools (parse, query, evaluate, rename, render)")
    print("═" * w)

    text_result = None
    graph_result = None

    if "--graph-only" not in sys.argv:
        print("\n  Launching TEXT agent...")
        text_result = launch_text_agent()
        print(f"  Text agent done in {text_result['elapsed']:.1f}s")
        if text_result.get("error"):
            print(f"  Error: {text_result['error'][:100]}")

    if "--text-only" not in sys.argv:
        print("\n  Launching GRAPH agent...")
        graph_result = launch_graph_agent()
        print(f"  Graph agent done in {graph_result['elapsed']:.1f}s")
        if graph_result.get("error"):
            print(f"  Error: {graph_result['error'][:100]}")

    if text_result or graph_result:
        print_results(text_result, graph_result)

    # Save results
    output = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "model": MODEL,
        "timeout": TIMEOUT,
    }
    if text_result:
        output["text"] = {
            "elapsed": text_result["elapsed"],
            "error": text_result.get("error"),
            "transcript_length": len(text_result["transcript"]),
            "score": score_transcript(text_result["transcript"]),
        }
        (SCRIPT_DIR / "text-transcript.md").write_text(text_result["transcript"])
    if graph_result:
        output["graph"] = {
            "elapsed": graph_result["elapsed"],
            "error": graph_result.get("error"),
            "transcript_length": len(graph_result["transcript"]),
            "score": score_transcript(graph_result["transcript"]),
        }
        (SCRIPT_DIR / "graph-transcript.md").write_text(graph_result["transcript"])

    results_file = SCRIPT_DIR / "results.json"
    with open(results_file, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"  Results saved to {results_file}")
    print(f"  Transcripts saved to {SCRIPT_DIR}/{{text,graph}}-transcript.md")


if __name__ == "__main__":
    main()

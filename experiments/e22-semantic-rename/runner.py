#!/usr/bin/env python3
"""E22: Semantic Rename at Scale

58 functions. Target function "helper" shares its name with:
- 5 other function names containing "helper" (helper-rate, tax-helper, etc.)
- 4 parameter bindings named "helper" (in process-a through process-d)

Text agent: find-and-replace in source file.
Graph agent: one rename operation on the entity.

The graph wins when the object being renamed is not a string.

Usage:
    python runner.py              # Run both agents sequentially
    python runner.py --text-only  # Text agent only
    python runner.py --graph-only # Graph agent only
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()
CNF_ROOT = SCRIPT_DIR.parent.parent
MODEL = "sonnet"
TIMEOUT = 300

STARTING_PROGRAM = (SCRIPT_DIR / "program.cnf").read_text()

# ════════════════════════════════════════════════════════════════════
# Ground truth for verification
# ════════════════════════════════════════════════════════════════════

# Functions that directly call `helper` (these call sites MUST change)
TRUE_CALLERS = [
    "compute-a", "compute-b", "compute-c", "compute-d",
    "compute-e", "compute-f", "mix-a", "mix-b", "mix-c",
]

# Function names containing "helper" that must NOT change
TRAP_NAMES = [
    "helper-rate", "tax-helper", "old-helper", "rate-helper", "helper-sum",
]

# Functions with parameter named "helper" — param must NOT change
PARAM_TRAP_FNS = ["process-a", "process-b", "process-c", "process-d"]


# ════════════════════════════════════════════════════════════════════
# Shared task
# ════════════════════════════════════════════════════════════════════

TASK_PREAMBLE = """\
You have a 58-function payroll program in a tiny functional language.
The language supports: defn, +, -, *, /, =, if, and function calls.

The program is already loaded (see below). Your task involves the
function named "helper".

IMPORTANT: The name "helper" appears in MANY places:
- "helper" is the TARGET function: (defn helper [x y] (+ x y))
- "helper-rate", "tax-helper", "old-helper", "rate-helper", "helper-sum"
  are DIFFERENT functions — do NOT rename them
- "process-a", "process-b", "process-c", "process-d" have PARAMETERS
  named "helper" — do NOT rename those parameters

Complete these steps IN ORDER. Report evidence for each step.

1. PARSE: Load the program. Confirm 58 functions parsed.

2. BASELINE: Evaluate these and confirm results:
   - helper(3, 4) = 7
   - compute-a(3, 4) = 14  (calls helper)
   - mix-a(3, 4) = 19  (calls helper AND helper-rate)
   - process-a(5, 3) = 15  (parameter named helper, NOT a call)
   - helper-rate(8, 25) = 200  (different function)

3. BREAK HELPER: Modify helper to cause division by zero:
   (defn helper [x y] (/ x y))
   Then evaluate compute-a(3, 0). It should error.
   Report the error.

4. FIX HELPER: Restore helper:
   (defn helper [x y] (+ x y))
   Verify compute-a(3, 4) = 14 again.

5. RENAME: Rename ONLY the function "helper" to "safe-helper".
   This must:
   a) Change the function definition from "helper" to "safe-helper"
   b) Update all 9 call sites in compute-a through compute-f, mix-a, mix-b, mix-c
   c) NOT change helper-rate, tax-helper, old-helper, rate-helper, helper-sum
   d) NOT change parameters named "helper" in process-a through process-d

6. VERIFY RENAME:
   a) Render the program. Confirm "safe-helper" appears as a function.
   b) Confirm "helper-rate" still appears (not "safe-helper-rate").
   c) Confirm process-a still has parameter "helper" (not "safe-helper").
   d) Evaluate safe-helper(3, 4) = 7
   e) Evaluate compute-a(3, 4) = 14  (now calls safe-helper)
   f) Evaluate mix-a(3, 4) = 19  (calls safe-helper + helper-rate)
   g) Evaluate process-a(5, 3) = 15  (parameter, unaffected)
   h) Evaluate helper-rate(8, 25) = 200  (unaffected)

7. QUERY DEPENDENCIES: Which functions depend on safe-helper?
   List them.

8. ERROR HISTORY: Is the failed evaluation from step 3 still queryable?
   Report its status and reason.

9. FINAL RENDER: Show the full rendered program to prove coherence.

For each step, report: what you did, result, pass/fail.
"""

# ════════════════════════════════════════════════════════════════════
# Text agent
# ════════════════════════════════════════════════════════════════════

TEXT_PROMPT = TASK_PREAMBLE + """
TOOLS: You have a working directory with:
- program.cnf — the 58-function source file
- eval-helper.rkt — evaluation tool:
    racket eval-helper.rkt eval program.cnf <fn-name> <arg1> <arg2> ...
    racket eval-helper.rkt deps program.cnf
    racket eval-helper.rkt render program.cnf

The eval-helper re-parses fresh each invocation. No cross-run state.

For step 5 (rename): edit program.cnf. Be VERY careful — "helper"
appears as a substring in other function names and as parameter names.
A naive find-and-replace will break the program.

For step 8 (error history): the eval-helper has no persistent state.
Report what you observed in step 3.

Starting program:
```
""" + STARTING_PROGRAM + """
```
"""

# ════════════════════════════════════════════════════════════════════
# Graph agent
# ════════════════════════════════════════════════════════════════════

GRAPH_PROMPT = TASK_PREAMBLE + """
TOOLS: You have MCP tools connected to a CNF claim graph server.

Key tools:
- reset: Initialize fresh workspace
- parse_program: Parse source into graph (language: "cnf")
- evaluate: Run function by name, result as queryable claims
- query: Datalog queries (e.g. fn-depends-on)
- rename: Rename an entity — call sites update automatically
- modify_function: Change a function's implementation
- render: Render function or program to text
- inspect: Examine any entity's claims

For step 5 (rename): use the rename tool. It operates on the entity,
not on string matching. Call sites update automatically. Other functions
with "helper" in their name and parameters named "helper" are unaffected.

For step 8 (error history): the eval-run entity from step 3 persists
in the graph. Query it.

Start with reset, then parse_program with the starting program.

Starting program:
```
""" + STARTING_PROGRAM + """
```
"""


def launch_text_agent():
    ws = Path(tempfile.mkdtemp(prefix="e22-text-"))
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
        # Read the modified program for verification
        modified = ""
        prog_path = ws / "program.cnf"
        if prog_path.exists():
            modified = prog_path.read_text()
        return {
            "agent": "text",
            "elapsed": elapsed,
            "transcript": result.stdout or "",
            "modified_program": modified,
            "error": None if result.returncode == 0 else result.stderr[:500],
            "workspace": str(ws),
        }
    except subprocess.TimeoutExpired:
        elapsed = time.monotonic() - start
        modified = ""
        prog_path = ws / "program.cnf"
        if prog_path.exists():
            modified = prog_path.read_text()
        return {
            "agent": "text",
            "elapsed": elapsed,
            "transcript": "",
            "modified_program": modified,
            "error": "timeout",
            "workspace": str(ws),
        }


def launch_graph_agent():
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
        return {
            "agent": "graph",
            "elapsed": elapsed,
            "transcript": result.stdout or "",
            "modified_program": "",
            "error": None if result.returncode == 0 else result.stderr[:500],
        }
    except subprocess.TimeoutExpired:
        elapsed = time.monotonic() - start
        return {
            "agent": "graph",
            "elapsed": elapsed,
            "transcript": "",
            "modified_program": "",
            "error": "timeout",
        }


# ════════════════════════════════════════════════════════════════════
# Verification (text agent's modified program)
# ════════════════════════════════════════════════════════════════════

def verify_text_rename(modified):
    """Check the text agent's modified program.cnf for rename correctness."""
    if not modified:
        return {"error": "no modified program found"}

    results = {}

    # 1. Function "safe-helper" exists
    results["defn_safe_helper"] = "(defn safe-helper [" in modified

    # 2. Old "defn helper" gone (but helper-rate etc. still there)
    has_defn_helper = bool(re.search(r'\(defn helper\s+\[', modified))
    results["defn_helper_gone"] = not has_defn_helper

    # 3. Trap names preserved
    for name in TRAP_NAMES:
        results[f"preserved_{name}"] = name in modified

    # 4. No false positives: helper-rate should NOT become safe-helper-rate
    results["no_safe_helper_rate"] = "safe-helper-rate" not in modified
    results["no_safe_helper_sum"] = "safe-helper-sum" not in modified
    results["no_tax_safe_helper"] = "tax-safe-helper" not in modified
    results["no_old_safe_helper"] = "old-safe-helper" not in modified
    results["no_rate_safe_helper"] = "rate-safe-helper" not in modified

    # 5. Parameter "helper" preserved in process-* functions
    for fn_name in PARAM_TRAP_FNS:
        pattern = rf'\(defn {re.escape(fn_name)} \[.*?helper.*?\]'
        match = re.search(pattern, modified)
        if match:
            results[f"param_{fn_name}"] = "safe-helper" not in match.group()
        else:
            results[f"param_{fn_name}"] = False

    # 6. Call sites updated — extract full function body between matching parens
    for caller in TRUE_CALLERS:
        start = modified.find(f"(defn {caller} ")
        if start >= 0:
            depth = 0
            end = start
            for i in range(start, len(modified)):
                if modified[i] == '(':
                    depth += 1
                elif modified[i] == ')':
                    depth -= 1
                    if depth == 0:
                        end = i + 1
                        break
            body = modified[start:end]
            results[f"callsite_{caller}"] = "safe-helper" in body
        else:
            results[f"callsite_{caller}"] = False

    return results


def verify_graph_transcript(transcript):
    """Check the graph agent's transcript for evidence of correct behavior."""
    t = transcript.lower()
    results = {}

    results["parsed_58"] = "58" in t
    results["baseline_7"] = "= 7" in t or "result: 7" in t
    results["baseline_14"] = "= 14" in t or "result: 14" in t
    results["error_recorded"] = "division by zero" in t
    results["renamed"] = "safe-helper" in t
    results["helper_rate_preserved"] = "helper-rate" in t
    results["error_history"] = "error" in t and ("run" in t or "status" in t)
    results["no_false_positive"] = "safe-helper-rate" not in t

    return results


def print_results(text_result, graph_result):
    w = 76
    print()
    print("═" * w)
    print("  E22: SEMANTIC RENAME AT SCALE — RESULTS")
    print("═" * w)

    print(f"\n  {'':35} {'Text':>14} {'Graph':>14}")
    print("  " + "─" * (w - 4))

    if text_result:
        print(f"  {'Wall time':<35} {text_result['elapsed']:>13.1f}s", end="")
    else:
        print(f"  {'Wall time':<35} {'—':>14}", end="")
    if graph_result:
        print(f" {graph_result['elapsed']:>13.1f}s")
    else:
        print(f" {'—':>14}")

    # Text agent file verification
    if text_result and text_result.get("modified_program"):
        text_v = verify_text_rename(text_result["modified_program"])
        fp_count = sum(1 for k, v in text_v.items()
                       if k.startswith("no_") and not v)
        preserved = sum(1 for k, v in text_v.items()
                        if k.startswith("preserved_") and v)
        params = sum(1 for k, v in text_v.items()
                     if k.startswith("param_") and v)
        callsites = sum(1 for k, v in text_v.items()
                        if k.startswith("callsite_") and v)

        print(f"\n  Text agent rename verification:")
        print(f"    defn safe-helper exists:      {text_v.get('defn_safe_helper', '?')}")
        print(f"    defn helper gone:             {text_v.get('defn_helper_gone', '?')}")
        print(f"    Trap names preserved:         {preserved}/5")
        print(f"    False-positive renames:       {fp_count}")
        print(f"    Params preserved:             {params}/4")
        print(f"    Call sites updated:           {callsites}/9")

        # Detail failures
        for k, v in sorted(text_v.items()):
            if not v:
                print(f"    FAIL: {k}")

    # Graph agent transcript check
    if graph_result:
        graph_v = verify_graph_transcript(graph_result["transcript"])
        print(f"\n  Graph agent transcript checks:")
        for k, v in sorted(graph_v.items()):
            status = "PASS" if v else "FAIL"
            print(f"    {k:<30} {status}")

    # Key differentiators
    print(f"\n  Key differentiators:")
    print(f"    Rename: graph=1 operation on entity, text=careful string editing")
    print(f"    Error history: graph=queryable eval-run, text=not retained")
    print(f"    False positives: graph=impossible by construction, text=depends on care")
    print()


def main():
    w = 76
    print("═" * w)
    print("  E22: Semantic Rename at Scale")
    print()
    print(f"  58 functions, name-ambiguity traps, model: {MODEL}")
    print("  Target: rename 'helper' → 'safe-helper'")
    print("  Traps: 5 similarly-named functions, 4 parameter shadows")
    print("═" * w)

    text_result = None
    graph_result = None

    if "--graph-only" not in sys.argv:
        print("\n  Launching TEXT agent...")
        text_result = launch_text_agent()
        print(f"  Text agent done in {text_result['elapsed']:.1f}s")

    if "--text-only" not in sys.argv:
        print("\n  Launching GRAPH agent...")
        graph_result = launch_graph_agent()
        print(f"  Graph agent done in {graph_result['elapsed']:.1f}s")

    if text_result or graph_result:
        print_results(text_result, graph_result)

    # Save results
    output = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "model": MODEL,
        "timeout": TIMEOUT,
        "functions": 58,
        "true_callers": len(TRUE_CALLERS),
        "trap_names": len(TRAP_NAMES),
        "param_traps": len(PARAM_TRAP_FNS),
    }
    if text_result:
        output["text"] = {
            "elapsed": text_result["elapsed"],
            "error": text_result.get("error"),
            "verification": verify_text_rename(text_result.get("modified_program", "")),
        }
        (SCRIPT_DIR / "text-transcript.md").write_text(text_result["transcript"])
        if text_result.get("modified_program"):
            (SCRIPT_DIR / "text-modified.cnf").write_text(text_result["modified_program"])
    if graph_result:
        output["graph"] = {
            "elapsed": graph_result["elapsed"],
            "error": graph_result.get("error"),
            "verification": verify_graph_transcript(graph_result["transcript"]),
        }
        (SCRIPT_DIR / "graph-transcript.md").write_text(graph_result["transcript"])

    results_file = SCRIPT_DIR / "results.json"
    with open(results_file, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"  Results: {results_file}")
    print(f"  Transcripts: {SCRIPT_DIR}/{{text,graph}}-transcript.md")


if __name__ == "__main__":
    main()

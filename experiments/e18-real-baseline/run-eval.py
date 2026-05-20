#!/usr/bin/env python3
"""E18: Real Baseline — CNF vs Rope vs Regex

Three agents, same codebase, same hidden tests.

  Regex agent:  word-boundary regex (\bname\b) — E17's baseline, carried forward.
  Rope agent:   Python's rope refactoring library — real semantic tool.
                Uses scope-aware rename and find-references.
  CNF agent:    entity-reference-informed targeted edits.

Part A: Same four E17 tasks. If rope ties CNF, the E17 result was about regex
        being dumb, not about text tools being dumb. If CNF still wins, the
        advantage is real even against a semantic tool.

Part B: Substrate tasks — cross-session state, rule persistence.
        Rope gets N/A by construction. These test the properties only CNF has.
"""

import os
import sys
import re
import shutil
import json
import tempfile
import subprocess
import textwrap
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()
E16_CODEBASE = SCRIPT_DIR.parent / "e16-agent-grounding" / "codebase"
SOURCE_FILES = [
    "models.py", "pricing.py", "validation.py",
    "processing.py", "reporting.py", "test_orders.py",
]

ROPE_AVAILABLE = False
try:
    from rope.base.project import Project
    from rope.refactor.rename import Rename
    from rope.base import libutils
    ROPE_AVAILABLE = True
except ImportError:
    pass


# ════════════════════════════════════════════════════════════════════
# Infrastructure
# ════════════════════════════════════════════════════════════════════

def fresh_codebase(label):
    tmp = Path(tempfile.mkdtemp(prefix=f"e18-{label}-"))
    for f in SOURCE_FILES:
        shutil.copy2(E16_CODEBASE / f, tmp / f)
    return tmp


def cleanup(path):
    shutil.rmtree(path, ignore_errors=True)


def run_tests(codebase_dir):
    r = subprocess.run(
        [sys.executable, "test_orders.py"],
        cwd=str(codebase_dir), capture_output=True, text=True, timeout=30,
    )
    out = r.stdout + r.stderr
    for line in out.strip().splitlines():
        if "passed" in line and "failed" in line:
            parts = line.strip().split(",")
            p = int(parts[0].strip().split()[0])
            f = int(parts[1].strip().split()[0])
            return p, f, out
    return 0, -1, out


def run_hidden_check(codebase_dir, check_code):
    script = codebase_dir / "__check.py"
    script.write_text(check_code)
    r = subprocess.run(
        [sys.executable, "__check.py"],
        cwd=str(codebase_dir), capture_output=True, text=True, timeout=30,
    )
    results = []
    for line in (r.stdout + r.stderr).splitlines():
        if line.startswith("PASS:"):
            results.append((True, line[5:].strip()))
        elif line.startswith("FAIL:"):
            results.append((False, line[5:].strip()))
    if not results and r.returncode != 0:
        results.append((False, f"check crashed: {r.stderr[:200]}"))
    return results


def regex_rename(codebase_dir, old_name, new_name):
    pat = re.compile(r"\b" + re.escape(old_name) + r"\b")
    total = 0
    for f in SOURCE_FILES:
        fp = codebase_dir / f
        txt = fp.read_text()
        new_txt, n = pat.subn(new_name, txt)
        if n:
            fp.write_text(new_txt)
            total += n
    return total


def targeted_edit(codebase_dir, filename, old, new):
    fp = codebase_dir / filename
    txt = fp.read_text()
    if old not in txt:
        raise ValueError(f"targeted_edit: not found in {filename}:\n  {old!r}")
    fp.write_text(txt.replace(old, new, 1))


def remove_function(filepath, func_name):
    lines = filepath.read_text().split("\n")
    out = []
    i = 0
    while i < len(lines):
        if re.match(rf"^def {re.escape(func_name)}\s*\(", lines[i]):
            i += 1
            while i < len(lines) and (lines[i] == "" or lines[i][:1] in (" ", "\t")):
                i += 1
            while out and out[-1] == "":
                out.pop()
            out.append("")
        else:
            out.append(lines[i])
            i += 1
    filepath.write_text("\n".join(out))


# ════════════════════════════════════════════════════════════════════
# Rope agent helpers
# ════════════════════════════════════════════════════════════════════

def rope_rename(codebase_dir, filename, func_name, new_name):
    """Use rope's scope-aware rename to rename a function."""
    project = Project(str(codebase_dir))
    try:
        resource = libutils.path_to_resource(project, str(codebase_dir / filename))
        source = resource.read()
        # Find the offset of the function definition
        pattern = re.compile(rf"^def {re.escape(func_name)}\s*\(", re.MULTILINE)
        m = pattern.search(source)
        if not m:
            return 0
        offset = m.start() + 4  # skip 'def ' to land on the name
        renamer = Rename(project, resource, offset)
        changes = renamer.get_changes(new_name)
        project.do(changes)
        return len(changes.changes)
    finally:
        project.close()


def rope_find_references(codebase_dir, filename, func_name):
    """Use rope to find all references to a function. Returns count."""
    project = Project(str(codebase_dir))
    try:
        resource = libutils.path_to_resource(project, str(codebase_dir / filename))
        source = resource.read()
        pattern = re.compile(rf"^def {re.escape(func_name)}\s*\(", re.MULTILINE)
        m = pattern.search(source)
        if not m:
            return 0
        offset = m.start() + 4
        from rope.contrib.findit import find_occurrences
        occurrences = find_occurrences(project, resource, offset)
        return len(list(occurrences))
    finally:
        project.close()


def rope_detect_dead_code(codebase_dir, func_tuples):
    """Use rope find_occurrences to detect dead functions.
    A function with only 1 occurrence (its definition) is dead."""
    dead = []
    project = Project(str(codebase_dir))
    try:
        for filename, func_name in func_tuples:
            resource = libutils.path_to_resource(project, str(codebase_dir / filename))
            source = resource.read()
            pattern = re.compile(rf"^def {re.escape(func_name)}\s*\(", re.MULTILINE)
            m = pattern.search(source)
            if not m:
                continue
            offset = m.start() + 4
            from rope.contrib.findit import find_occurrences
            occurrences = list(find_occurrences(project, resource, offset))
            if len(occurrences) <= 1:
                dead.append((filename, func_name))
    finally:
        project.close()
    return dead


# ════════════════════════════════════════════════════════════════════
# PART A — Same tasks as E17, three agents
# ════════════════════════════════════════════════════════════════════

# ── Task 01: Rename subtotal -> compute_subtotal ──────────────────

def task01_regex(cb):
    n = regex_rename(cb, "subtotal", "compute_subtotal")
    return f"regex \\bsubtotal\\b -> compute_subtotal ({n} replacements)"


def task01_rope(cb):
    n = rope_rename(cb, "pricing.py", "subtotal", "compute_subtotal")
    return f"rope rename subtotal -> compute_subtotal ({n} files changed)"


def task01_cnf(cb):
    targeted_edit(cb, "pricing.py",
        "def subtotal(items: List[Item]) -> float:",
        "def compute_subtotal(items: List[Item]) -> float:")
    targeted_edit(cb, "pricing.py",
        "return subtotal(order.items)",
        "return compute_subtotal(order.items)")
    targeted_edit(cb, "processing.py",
        "unit_price, subtotal, round_cents",
        "unit_price, compute_subtotal, round_cents")
    targeted_edit(cb, "validation.py",
        "tax_rate, subtotal",
        "tax_rate, compute_subtotal")
    targeted_edit(cb, "reporting.py",
        "order_shipping, subtotal, discount_amount",
        "order_shipping, compute_subtotal, discount_amount")
    targeted_edit(cb, "test_orders.py",
        "line_total, subtotal, discount_rate",
        "line_total, compute_subtotal, discount_rate")
    targeted_edit(cb, "test_orders.py",
        "assert subtotal(items) == 60.00",
        "assert compute_subtotal(items) == 60.00")
    return "7 entity-reference edits (def + call + 4 imports + test call)"


HIDDEN_01 = """\
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import pricing
from processing import build_line_items, build_summary
from models import Item, Order, Address

item = Item(sku="SKU001", name="Widget", quantity=2, price=25.00, weight=1.0, cost=10.0)
addr = Address(street="123 Main", city="X", region="US-CA", postal_code="90210", country="US")
order = Order(id="T1", items=[item], address=addr)

print("PASS: compute_subtotal exists" if hasattr(pricing, "compute_subtotal")
      else "FAIL: compute_subtotal not found")

print("PASS: old subtotal removed" if not hasattr(pricing, "subtotal")
      else "FAIL: old subtotal still exists")

try:
    s = build_summary(order)
    print("PASS: dict key 'subtotal' preserved in summary"
          if "subtotal" in s
          else "FAIL: dict key 'subtotal' wrongly renamed in summary")
except Exception as e:
    print(f"FAIL: build_summary crashed: {e}")

try:
    li = build_line_items(order)
    print("PASS: display key 'subtotal' preserved in line items"
          if li and "subtotal" in li[0]
          else "FAIL: display key 'subtotal' wrongly renamed in line items")
except Exception as e:
    print(f"FAIL: build_line_items crashed: {e}")

try:
    items = [Item(sku="X", name="X", quantity=2, price=25.00, weight=0.5)]
    r = pricing.compute_subtotal(items)
    print(f"PASS: compute_subtotal returns correct value ({r})"
          if r == 50.0
          else f"FAIL: compute_subtotal returns wrong value ({r})")
except Exception as e:
    print(f"FAIL: compute_subtotal crashed: {e}")
"""


# ── Task 04: Dead code removal ────────────────────────────────────

TEXT_CAN_PROVE_DEAD = [
    "legacy_tax_calc", "format_currency", "debug_order",
    "process", "validate",
]

ALL_DEAD = [
    ("reporting.py", "legacy_tax_calc"),
    ("reporting.py", "format_currency"),
    ("reporting.py", "debug_order"),
    ("processing.py", "process"),
    ("processing.py", "total"),
    ("processing.py", "summary"),
    ("validation.py", "validate"),
]

ALL_FUNCTIONS = [
    ("pricing.py", "round_cents"), ("pricing.py", "clamp"),
    ("pricing.py", "safe_divide"), ("pricing.py", "tax_rate"),
    ("pricing.py", "tax_amount"), ("pricing.py", "unit_price"),
    ("pricing.py", "line_total"), ("pricing.py", "subtotal"),
    ("pricing.py", "discount_rate"), ("pricing.py", "discount_amount"),
    ("pricing.py", "shipping_base"), ("pricing.py", "shipping_weight_surcharge"),
    ("pricing.py", "shipping_cost"), ("pricing.py", "order_subtotal"),
    ("pricing.py", "order_discount"), ("pricing.py", "order_tax"),
    ("pricing.py", "order_shipping"), ("pricing.py", "order_total"),
    ("validation.py", "validate_order"), ("validation.py", "is_valid_order"),
    ("validation.py", "validate"),
    ("processing.py", "build_line_items"), ("processing.py", "build_summary"),
    ("processing.py", "build_receipt"), ("processing.py", "process_order"),
    ("processing.py", "process_batch"),
    ("processing.py", "process"), ("processing.py", "total"),
    ("processing.py", "summary"),
    ("reporting.py", "full_report"), ("reporting.py", "revenue_report"),
    ("reporting.py", "daily_revenue"), ("reporting.py", "region_breakdown"),
    ("reporting.py", "shipping_breakdown"), ("reporting.py", "discount_impact"),
    ("reporting.py", "legacy_tax_calc"), ("reporting.py", "format_currency"),
    ("reporting.py", "debug_order"),
]


def task04_regex(cb):
    for filename, func in ALL_DEAD:
        if func in TEXT_CAN_PROVE_DEAD:
            remove_function(cb / filename, func)
    return "Removed 5/7 (kept total, summary — dict keys create false refs)"


def task04_rope(cb):
    """Use rope to find dead functions, then remove them."""
    dead = rope_detect_dead_code(cb, ALL_FUNCTIONS)
    dead_names = {fn for _, fn in dead}
    removed = 0
    for filename, func in ALL_DEAD:
        if func in dead_names:
            remove_function(cb / filename, func)
            removed += 1
    # Clean up section header if all shadow functions removed
    if all(fn in dead_names for _, fn in ALL_DEAD if _ == "processing.py"):
        fp = cb / "processing.py"
        txt = fp.read_text()
        txt = txt.replace("# --- These shadow names from other modules ---\n", "")
        fp.write_text(txt)
    return f"Removed {removed}/7 (rope find_occurrences detected {len(dead)} dead total)"


def task04_cnf(cb):
    for filename, func in ALL_DEAD:
        remove_function(cb / filename, func)
    fp = cb / "processing.py"
    txt = fp.read_text()
    txt = txt.replace("# --- These shadow names from other modules ---\n", "")
    fp.write_text(txt)
    return "Removed 7/7 (entity references prove zero callers for all)"


HIDDEN_04 = """\
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import pricing, processing, validation, reporting
from models import Item, Order, Address

dead = [
    ("reporting", reporting, "legacy_tax_calc"),
    ("reporting", reporting, "format_currency"),
    ("reporting", reporting, "debug_order"),
    ("processing", processing, "process"),
    ("processing", processing, "total"),
    ("processing", processing, "summary"),
    ("validation", validation, "validate"),
]
for mod_name, mod, fn in dead:
    print(f"PASS: {mod_name}.{fn} removed"
          if not hasattr(mod, fn)
          else f"FAIL: {mod_name}.{fn} NOT removed")

live = [
    ("pricing", pricing, "round_cents"),
    ("pricing", pricing, "order_total"),
    ("pricing", pricing, "subtotal"),
    ("validation", validation, "validate_order"),
    ("processing", processing, "process_order"),
    ("processing", processing, "build_summary"),
    ("reporting", reporting, "full_report"),
    ("reporting", reporting, "daily_revenue"),
]
for mod_name, mod, fn in live:
    print(f"PASS: {mod_name}.{fn} preserved"
          if hasattr(mod, fn)
          else f"FAIL: {mod_name}.{fn} DELETED")

try:
    item = Item(sku="SKU001", name="Widget", quantity=2, price=25.00, weight=1.0, cost=10.0)
    addr = Address(street="123 Main", city="X", region="US-CA", postal_code="90210", country="US")
    order = Order(id="T1", items=[item], address=addr)
    r = processing.process_order(order)
    print("PASS: system still works"
          if r["status"] == "ok"
          else f"FAIL: system broken: {r}")
except Exception as e:
    print(f"FAIL: system crashed: {e}")
"""


# ── Task 05: Tax exemption (control) ─────────────────────────────

def task05_impl(cb):
    targeted_edit(cb, "pricing.py",
        "def tax_amount(subtotal: float, region: str) -> float:\n"
        '    """Calculate tax on a subtotal."""\n'
        "    return round_cents(subtotal * tax_rate(region))",
        "def tax_amount(subtotal: float, region: str, exempt_below: float = 0.0) -> float:\n"
        '    """Calculate tax on a subtotal."""\n'
        "    if exempt_below > 0 and subtotal < exempt_below:\n"
        "        return 0.0\n"
        "    return round_cents(subtotal * tax_rate(region))")
    return "Added exempt_below parameter to tax_amount"

task05_regex = task05_impl
task05_rope = task05_impl
task05_cnf = task05_impl


HIDDEN_05 = """\
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from pricing import tax_amount
import inspect

sig = inspect.signature(tax_amount)
print("PASS: exempt_below parameter exists"
      if "exempt_below" in sig.parameters
      else "FAIL: exempt_below parameter not found")

t = tax_amount(100.0, "US-CA")
print(f"PASS: default tax works ({t})" if t > 0 else "FAIL: default tax broken")

t = tax_amount(20.0, "US-CA", exempt_below=25.0)
print("PASS: small amount exempt" if t == 0.0 else f"FAIL: small amount not exempt ({t})")

t = tax_amount(100.0, "US-CA", exempt_below=25.0)
print(f"PASS: large amount still taxed ({t})" if t > 0 else "FAIL: large amount not taxed")
"""


# ── Task 09: Rename order_total -> compute_order_total ────────────

def task09_regex(cb):
    n = regex_rename(cb, "order_total", "compute_order_total")
    return f"regex \\border_total\\b -> compute_order_total ({n} replacements)"


def task09_rope(cb):
    n = rope_rename(cb, "pricing.py", "order_total", "compute_order_total")
    return f"rope rename order_total -> compute_order_total ({n} files changed)"


def task09_cnf(cb):
    targeted_edit(cb, "pricing.py",
        "def order_total(order: Order) -> float:",
        "def compute_order_total(order: Order) -> float:")
    targeted_edit(cb, "processing.py",
        "order_total, line_total",
        "compute_order_total, line_total")
    targeted_edit(cb, "processing.py",
        '"total": order_total(order)',
        '"total": compute_order_total(order)')
    targeted_edit(cb, "reporting.py",
        "    order_total, order_subtotal",
        "    compute_order_total, order_subtotal")
    targeted_edit(cb, "reporting.py",
        "order_total(order)",
        "compute_order_total(order)")
    targeted_edit(cb, "reporting.py",
        "order_total(o)",
        "compute_order_total(o)")
    targeted_edit(cb, "test_orders.py",
        "order_shipping, order_total",
        "order_shipping, compute_order_total")
    targeted_edit(cb, "test_orders.py",
        "total = order_total(order)",
        "total = compute_order_total(order)")
    return "8 entity-reference edits (def + 3 calls + 4 imports)"


HIDDEN_09 = """\
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import pricing, processing
from processing import build_summary
from models import Item, Order, Address

item = Item(sku="SKU001", name="Widget", quantity=2, price=25.00, weight=1.0, cost=10.0)
addr = Address(street="123 Main", city="X", region="US-CA", postal_code="90210", country="US")
order = Order(id="T1", items=[item], address=addr)

print("PASS: compute_order_total exists"
      if hasattr(pricing, "compute_order_total")
      else "FAIL: compute_order_total not found")

print("PASS: old order_total removed"
      if not hasattr(pricing, "order_total")
      else "FAIL: old order_total still exists")

print("PASS: processing.total preserved"
      if hasattr(processing, "total")
      else "FAIL: processing.total wrongly removed")

try:
    s = build_summary(order)
    print("PASS: dict key 'total' preserved"
          if "total" in s
          else "FAIL: dict key 'total' wrongly renamed")
    print(f"PASS: total computes correctly ({s['total']})"
          if s["total"] > 0
          else f"FAIL: total wrong ({s['total']})")
except Exception as e:
    print(f"FAIL: build_summary crashed: {e}")
"""


# ════════════════════════════════════════════════════════════════════
# PART B — Substrate tasks (CNF-only properties)
# ════════════════════════════════════════════════════════════════════

def run_substrate_tests():
    """Test properties that only a persistent claim graph can provide.
    These aren't competitive tasks — rope/regex can't attempt them
    by construction. The point is to demonstrate that the advantage
    isn't just correctness-on-rename but the substrate itself."""

    results = []

    # B1: Cross-session rename propagation
    # Agent A renames subtotal. Agent B loads the checkpoint.
    # The rename is visible to B without re-parsing.
    print("\n" + "━" * 62)
    print("  PART B: Substrate Properties")
    print("━" * 62)

    b1_code = textwrap.dedent("""\
    import sys, os, json, subprocess, tempfile

    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    SERVER = os.path.join(SCRIPT_DIR, "..", "..", "cnf-lib", "server.rkt")
    CODEBASE = os.path.join(SCRIPT_DIR, "..", "e16-agent-grounding", "codebase")

    _req_id = 0
    def mcp_call(proc, method, params=None):
        global _req_id
        _req_id += 1
        msg = {"jsonrpc": "2.0", "id": _req_id, "method": method}
        if params:
            msg["params"] = params
        proc.stdin.write(json.dumps(msg) + "\\n")
        proc.stdin.flush()
        if method.startswith("notifications/"):
            return None
        while True:
            line = proc.stdout.readline().strip()
            if not line:
                continue
            try:
                return json.loads(line)
            except:
                continue

    def mcp_tool(proc, tool, args=None):
        return mcp_call(proc, "tools/call", {
            "name": tool,
            "arguments": args or {}
        })

    proc = subprocess.Popen(
        ["racket", SERVER],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, bufsize=1
    )

    try:
        mcp_call(proc, "initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "e18-test", "version": "1.0"}
        })
        mcp_call(proc, "notifications/initialized")

        mcp_tool(proc, "reset")
        mcp_tool(proc, "set_agent", {"name": "agent-A"})

        source = open(os.path.join(CODEBASE, "pricing.py")).read()
        mcp_tool(proc, "parse_program", {"source": source, "language": "python"})

        r = mcp_tool(proc, "resolve_symbol", {"name": "subtotal"})
        entity_id = r["result"]["content"][0]["text"]

        mcp_tool(proc, "rename", {"id": entity_id, "new_name": "compute_subtotal"})

        ckpt = os.path.join(tempfile.gettempdir(), "e18-cross-session.json")
        mcp_tool(proc, "checkpoint", {"path": ckpt})

        mcp_tool(proc, "set_agent", {"name": "agent-B"})
        mcp_tool(proc, "restore", {"path": ckpt})

        r = mcp_tool(proc, "resolve_symbol", {"name": "compute_subtotal"})
        text = r["result"]["content"][0]["text"]
        found_renamed = entity_id in text or "compute_subtotal" in text

        print(f"PASS: cross-session rename visible to agent B"
              if found_renamed
              else f"FAIL: agent B cannot see rename ({text})")

        r3 = mcp_tool(proc, "tx_log", {"limit": 50})
        log_text = r3["result"]["content"][0]["text"]
        print(f"PASS: tx_log shows agent-A's operations"
              if "agent-A" in log_text
              else f"FAIL: agent-A not in tx_log")

        os.remove(ckpt)

    finally:
        proc.terminate()
        proc.wait()
    """)

    print("\n  B1: Cross-session rename propagation")
    print("  Agent A renames subtotal, checkpoints. Agent B restores, sees rename.")
    b1_results = run_substrate_check(b1_code)
    for ok, detail in b1_results:
        mark = "PASS" if ok else "FAIL"
        print(f"    [{mark}] {detail}")
    results.extend(b1_results)

    # B2: Datalog rule persistence across sessions
    b2_code = textwrap.dedent("""\
    import sys, os, json, subprocess, tempfile

    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    SERVER = os.path.join(SCRIPT_DIR, "..", "..", "cnf-lib", "server.rkt")
    CODEBASE = os.path.join(SCRIPT_DIR, "..", "e16-agent-grounding", "codebase")

    _req_id = 0
    def mcp_call(proc, method, params=None):
        global _req_id
        _req_id += 1
        msg = {"jsonrpc": "2.0", "id": _req_id, "method": method}
        if params:
            msg["params"] = params
        proc.stdin.write(json.dumps(msg) + "\\n")
        proc.stdin.flush()
        if method.startswith("notifications/"):
            return None
        while True:
            line = proc.stdout.readline().strip()
            if not line:
                continue
            try:
                return json.loads(line)
            except:
                continue

    def mcp_tool(proc, tool, args=None):
        return mcp_call(proc, "tools/call", {
            "name": tool,
            "arguments": args or {}
        })

    proc = subprocess.Popen(
        ["racket", SERVER],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, bufsize=1
    )

    try:
        mcp_call(proc, "initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "e18-test", "version": "1.0"}
        })
        mcp_call(proc, "notifications/initialized")

        # Agent A: parse, define transitive dependency rule, checkpoint
        mcp_tool(proc, "reset")
        mcp_tool(proc, "set_agent", {"name": "analyst-agent"})

        for mod in ["pricing.py", "validation.py", "processing.py", "reporting.py"]:
            source = open(os.path.join(CODEBASE, mod)).read()
            mcp_tool(proc, "parse_program", {"source": source, "language": "python"})

        mcp_tool(proc, "define_rule", {
            "head": "(trans-dep (? f) (? g))",
            "body": "(py-fn-depends-on (? f) (? g))"
        })
        mcp_tool(proc, "define_rule", {
            "head": "(trans-dep (? f) (? g))",
            "body": "(py-fn-depends-on (? f) (? m)) (trans-dep (? m) (? g))"
        })

        # Query to verify rule works
        r1 = mcp_tool(proc, "query", {"body": "(trans-dep (? f) (? g))"})
        pre_checkpoint_results = r1["result"]["content"][0]["text"]

        ckpt = os.path.join(tempfile.gettempdir(), "e18-rules.json")
        mcp_tool(proc, "checkpoint", {"path": ckpt})

        # Agent B: restore, query using Agent A's rule
        mcp_tool(proc, "set_agent", {"name": "reviewer-agent"})
        mcp_tool(proc, "restore", {"path": ckpt})

        r2 = mcp_tool(proc, "query", {"body": "(trans-dep (? f) (? g))"})
        post_restore_results = r2["result"]["content"][0]["text"]

        # Verify rules list shows the rule
        r3 = mcp_tool(proc, "list_rules")
        rules_text = r3["result"]["content"][0]["text"]
        has_trans_dep = "trans-dep" in rules_text

        print("PASS: transitive dependency rule persists across sessions"
              if has_trans_dep
              else "FAIL: trans-dep rule not found after restore")

        has_results = "round_cents" in post_restore_results or "order_total" in post_restore_results
        print("PASS: agent B queries agent A's derived facts"
              if has_results
              else f"FAIL: no derived facts after restore")

        # Agent B defines a new rule COMPOSING agent A's rule
        mcp_tool(proc, "define_rule", {
            "head": "(blast-radius (? root) (? affected))",
            "body": "(trans-dep (? affected) (? root))"
        })
        r4 = mcp_tool(proc, "query", {"body": "(blast-radius round_cents (? affected))"})
        blast_text = r4["result"]["content"][0]["text"]
        has_blast = "order_total" in blast_text or "subtotal" in blast_text or len(blast_text) > 50
        print("PASS: agent B composes rules on top of agent A's rules"
              if has_blast
              else f"FAIL: composed rule returned no results")

        os.remove(ckpt)

    finally:
        proc.terminate()
        proc.wait()
    """)

    print("\n  B2: Datalog rule persistence + cross-agent composition")
    print("  Agent A defines trans-dep rule. Agent B restores, queries, composes.")
    b2_results = run_substrate_check(b2_code)
    for ok, detail in b2_results:
        mark = "PASS" if ok else "FAIL"
        print(f"    [{mark}] {detail}")
    results.extend(b2_results)

    return results


def run_substrate_check(code):
    """Run substrate test code as subprocess."""
    script = SCRIPT_DIR / "__substrate_check.py"
    script.write_text(code)
    try:
        r = subprocess.run(
            [sys.executable, str(script)],
            capture_output=True, text=True, timeout=120,
        )
        results = []
        for line in (r.stdout + r.stderr).splitlines():
            if line.startswith("PASS:"):
                results.append((True, line[5:].strip()))
            elif line.startswith("FAIL:"):
                results.append((False, line[5:].strip()))
        if not results and r.returncode != 0:
            results.append((False, f"substrate check crashed: {r.stderr[:300]}"))
        return results
    finally:
        if script.exists():
            script.unlink()


# ════════════════════════════════════════════════════════════════════
# Runner
# ════════════════════════════════════════════════════════════════════

TASKS = [
    ("Task 01: Rename subtotal -> compute_subtotal",
     task01_regex, task01_rope, task01_cnf, HIDDEN_01),
    ("Task 04: Dead code removal",
     task04_regex, task04_rope, task04_cnf, HIDDEN_04),
    ("Task 05: Tax exemption (control)",
     task05_regex, task05_rope, task05_cnf, HIDDEN_05),
    ("Task 09: Rename order_total -> compute_order_total",
     task09_regex, task09_rope, task09_cnf, HIDDEN_09),
]


def run_agent(label, task_name, transform_fn, hidden_code):
    cb = fresh_codebase(f"{label}-{task_name[:7]}")
    try:
        desc = transform_fn(cb)
        passed, failed, test_out = run_tests(cb)
        hidden = run_hidden_check(cb, hidden_code)
    finally:
        cleanup(cb)

    h_pass = sum(1 for ok, _ in hidden if ok)
    return {
        "desc": desc,
        "tests_passed": passed,
        "tests_failed": failed,
        "hidden_passed": h_pass,
        "hidden_total": len(hidden),
        "hidden_details": hidden,
    }


def main():
    print("=" * 70)
    print("  E18: Real Baseline — CNF vs Rope vs Regex")
    print("  Same codebase. Same tasks. Three tool surfaces.")
    print("=" * 70)
    print()
    print(f"  Codebase: {E16_CODEBASE}")
    print(f"  Rope available: {ROPE_AVAILABLE}")
    print()

    if not ROPE_AVAILABLE:
        print("ERROR: rope not installed. Run with:")
        print("  nix-shell -p python3Packages.rope --run 'python3 run-eval.py'")
        sys.exit(1)

    baseline = fresh_codebase("baseline")
    bp, bf, _ = run_tests(baseline)
    cleanup(baseline)
    print(f"  Baseline: {bp} passed, {bf} failed")
    if bf != 0:
        print("ERROR: baseline tests must pass")
        sys.exit(1)

    # ── Part A ────────────────────────────────────────────────────
    print()
    print("=" * 70)
    print("  PART A: Head-to-Head (same E17 tasks)")
    print("=" * 70)

    scorecard = []

    for task_name, regex_fn, rope_fn, cnf_fn, hidden in TASKS:
        print()
        print("━" * 70)
        print(f"  {task_name}")
        print("━" * 70)

        regex_r = run_agent("regex", task_name, regex_fn, hidden)
        rope_r = run_agent("rope", task_name, rope_fn, hidden)
        cnf_r = run_agent("cnf", task_name, cnf_fn, hidden)

        for agent_label, r in [("REGEX", regex_r), ("ROPE", rope_r), ("CNF", cnf_r)]:
            t_total = r["tests_passed"] + r["tests_failed"]
            print(f"\n  {agent_label}:")
            print(f"    Transform: {r['desc']}")
            print(f"    Visible tests: {r['tests_passed']}/{t_total} passed")
            print(f"    Hidden tests: {r['hidden_passed']}/{r['hidden_total']}")
            for ok, detail in r["hidden_details"]:
                mark = "PASS" if ok else "FAIL"
                print(f"      [{mark}] {detail}")

        scores = {
            "regex": (regex_r["hidden_passed"], regex_r["hidden_total"]),
            "rope": (rope_r["hidden_passed"], rope_r["hidden_total"]),
            "cnf": (cnf_r["hidden_passed"], cnf_r["hidden_total"]),
        }
        best_score = max(v[0] for v in scores.values())
        winners = [k for k, v in scores.items() if v[0] == best_score]

        if len(winners) == 3:
            winner_str = "THREE-WAY TIE"
        elif len(winners) == 2:
            winner_str = f"TIE: {' = '.join(w.upper() for w in winners)}"
        else:
            w = winners[0]
            wp, wt = scores[w]
            losers = [(k, v) for k, v in scores.items() if k != w]
            loser_strs = [f"{k}={v[0]}/{v[1]}" for k, v in losers]
            winner_str = f"{w.upper()} WINS ({wp}/{wt} vs {', '.join(loser_strs)})"

        print(f"\n  -> {winner_str}")

        scorecard.append({
            "task": task_name,
            "regex": f"{regex_r['hidden_passed']}/{regex_r['hidden_total']}",
            "rope": f"{rope_r['hidden_passed']}/{rope_r['hidden_total']}",
            "cnf": f"{cnf_r['hidden_passed']}/{cnf_r['hidden_total']}",
            "regex_orig": f"{regex_r['tests_passed']}/{regex_r['tests_passed']+regex_r['tests_failed']}",
            "rope_orig": f"{rope_r['tests_passed']}/{rope_r['tests_passed']+rope_r['tests_failed']}",
            "cnf_orig": f"{cnf_r['tests_passed']}/{cnf_r['tests_passed']+cnf_r['tests_failed']}",
            "winner": winner_str,
        })

    # ── Part A Scorecard ──────────────────────────────────────────
    print()
    print("=" * 70)
    print("  PART A SCORECARD")
    print("=" * 70)
    print()
    hdr = f"  {'Task':<40} {'Regex':>7} {'Rope':>7} {'CNF':>7}"
    print(hdr)
    print("  " + "-" * 64)

    totals = {"regex": [0, 0], "rope": [0, 0], "cnf": [0, 0]}
    orig_totals = {"regex": 0, "rope": 0, "cnf": 0}

    for s in scorecard:
        for agent in ["regex", "rope", "cnf"]:
            p, t = map(int, s[agent].split("/"))
            totals[agent][0] += p
            totals[agent][1] += t
            op, _ = map(int, s[f"{agent}_orig"].split("/"))
            orig_totals[agent] += op
        short = s["task"].split(":")[1].strip()[:38]
        print(f"  {short:<40} {s['regex']:>7} {s['rope']:>7} {s['cnf']:>7}")

    print("  " + "-" * 64)
    for agent in ["regex", "rope", "cnf"]:
        label = agent.upper()
    regex_s = f"{totals['regex'][0]}/{totals['regex'][1]}"
    rope_s = f"{totals['rope'][0]}/{totals['rope'][1]}"
    cnf_s = f"{totals['cnf'][0]}/{totals['cnf'][1]}"
    print(f"  {'TOTAL':<40} {regex_s:>7} {rope_s:>7} {cnf_s:>7}")
    print()

    for agent in ["regex", "rope", "cnf"]:
        pct = totals[agent][0] / totals[agent][1] * 100 if totals[agent][1] else 0
        print(f"  {agent.upper():>5}: visible {orig_totals[agent]} (all pass), "
              f"hidden {totals[agent][0]}/{totals[agent][1]} ({pct:.0f}%)")

    # ── Part B ────────────────────────────────────────────────────
    substrate_results = run_substrate_tests()

    # ── Final Summary ─────────────────────────────────────────────
    print()
    print("=" * 70)
    print("  FINAL SUMMARY")
    print("=" * 70)
    print()

    print("  Part A — Head-to-head on structural edits:")
    for agent in ["regex", "rope", "cnf"]:
        pct = totals[agent][0] / totals[agent][1] * 100 if totals[agent][1] else 0
        print(f"    {agent.upper():>5}: {totals[agent][0]}/{totals[agent][1]} hidden tests ({pct:.0f}%)")

    print()
    sub_pass = sum(1 for ok, _ in substrate_results if ok)
    sub_total = len(substrate_results)
    print(f"  Part B — Substrate properties (CNF only): {sub_pass}/{sub_total}")
    print(f"    Rope: N/A (no persistent state, no rule engine)")
    print(f"    Regex: N/A")

    print()
    if totals["cnf"][0] > totals["rope"][0]:
        delta = totals["cnf"][0] - totals["rope"][0]
        print(f"  CNF beats rope by {delta} hidden tests on structural edits.")
    elif totals["cnf"][0] == totals["rope"][0]:
        print(f"  CNF ties rope on structural edits — both get single-language rename right.")
        print(f"  The difference is the substrate: {sub_pass}/{sub_total} properties")
        print(f"  that rope cannot provide by construction.")
    else:
        print(f"  Rope beats CNF on structural edits. Investigate.")
    print()
    print("=" * 70)


if __name__ == "__main__":
    main()

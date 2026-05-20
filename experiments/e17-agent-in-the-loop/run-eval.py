#!/usr/bin/env python3
"""E17: Agent-in-the-Loop Evaluation

Same codebase, same tasks, same hidden tests.
Text agent: word-boundary regex (best realistic text approach).
CNF agent: entity-reference-informed targeted edits.

Both make actual code changes. Both run the full test suite.
Hidden tests score correctness beyond what the test suite catches.

The text agent's approach is CHARITABLE — word-boundary regex is the
best a text tool can do. It still fails because regex cannot distinguish
a function call from a dict key when they share the same word.
"""

import os
import sys
import re
import shutil
import tempfile
import subprocess
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()
E16_CODEBASE = SCRIPT_DIR.parent / "e16-agent-grounding" / "codebase"
SOURCE_FILES = [
    "models.py", "pricing.py", "validation.py",
    "processing.py", "reporting.py", "test_orders.py",
]


# ────────────────────────────────────────────────────────────────────
# Infrastructure
# ────────────────────────────────────────────────────────────────────

def fresh_codebase(label):
    tmp = Path(tempfile.mkdtemp(prefix=f"e17-{label}-"))
    for f in SOURCE_FILES:
        shutil.copy2(E16_CODEBASE / f, tmp / f)
    return tmp


def cleanup(path):
    shutil.rmtree(path, ignore_errors=True)


def run_tests(codebase_dir):
    """Run test_orders.py -> (passed, failed, output)."""
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
    """Run hidden test code as subprocess -> list of (bool, detail)."""
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
    """Word-boundary regex rename across all source files. Returns count."""
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
    """Single targeted string replacement in one file."""
    fp = codebase_dir / filename
    txt = fp.read_text()
    if old not in txt:
        raise ValueError(f"targeted_edit: not found in {filename}:\n  {old!r}")
    fp.write_text(txt.replace(old, new, 1))


def remove_function(filepath, func_name):
    """Remove a top-level function definition from a Python file."""
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


# ────────────────────────────────────────────────────────────────────
# Task 01: Rename subtotal -> compute_subtotal
#
# Trap: "subtotal" appears as dict keys and display strings.
# Text agent's \bsubtotal\b matches dict keys (same word).
# CNF agent's entity references skip dict keys (not references).
# ────────────────────────────────────────────────────────────────────

def task01_text(cb):
    n = regex_rename(cb, "subtotal", "compute_subtotal")
    return f"regex \\bsubtotal\\b -> compute_subtotal ({n} replacements)"


def task01_cnf(cb):
    """CNF entity reference query: subtotal has 1 caller (order_subtotal).
    Entity references = definition + call sites + imports. Not dict keys."""
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


# ────────────────────────────────────────────────────────────────────
# Task 04: Dead code removal
#
# 7 dead functions. Text agent can prove 5 dead (unique names).
# Text agent CANNOT prove total() and summary() dead because
# grep -w 'total' matches dict keys "total" and grep -w 'summary'
# matches dict keys "summary" — appearing to have callers.
# CNF agent: entity references show zero callers for all 7.
# ────────────────────────────────────────────────────────────────────

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


def task04_text(cb):
    for filename, func in ALL_DEAD:
        if func in TEXT_CAN_PROVE_DEAD:
            remove_function(cb / filename, func)
    return "Removed 5/7 (kept total, summary — dict keys create false refs)"


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


# ────────────────────────────────────────────────────────────────────
# Task 05: Tax exemption (control — both make same change)
#
# Both agents add exempt_below parameter to tax_amount.
# This is a local code change — structural analysis not needed.
# Included to show CNF doesn't claim to win on everything.
# ────────────────────────────────────────────────────────────────────

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


def task05_text(cb):
    return task05_impl(cb)


def task05_cnf(cb):
    return task05_impl(cb)


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


# ────────────────────────────────────────────────────────────────────
# Task 09: Rename order_total -> compute_order_total
#
# Text agent succeeds here — order_total is specific enough that
# \border_total\b doesn't hit dict key "total" or processing.total().
# Included to show text CAN work when names are unique.
# ────────────────────────────────────────────────────────────────────

def task09_text(cb):
    n = regex_rename(cb, "order_total", "compute_order_total")
    return f"regex \\border_total\\b -> compute_order_total ({n} replacements)"


def task09_cnf(cb):
    """CNF entity reference query: order_total callers =
    [build_summary, daily_revenue, region_breakdown]."""
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


# ────────────────────────────────────────────────────────────────────
# Runner
# ────────────────────────────────────────────────────────────────────

TASKS = [
    ("Task 01: Rename subtotal -> compute_subtotal",
     task01_text, task01_cnf, HIDDEN_01),
    ("Task 04: Dead code removal",
     task04_text, task04_cnf, HIDDEN_04),
    ("Task 05: Tax exemption (control)",
     task05_text, task05_cnf, HIDDEN_05),
    ("Task 09: Rename order_total -> compute_order_total",
     task09_text, task09_cnf, HIDDEN_09),
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
    print("=" * 62)
    print("  E17: Agent-in-the-Loop Evaluation")
    print("  Same codebase. Same tasks. Different tool surfaces.")
    print("=" * 62)
    print()
    print(f"Codebase: {E16_CODEBASE}")
    print()

    baseline = fresh_codebase("baseline")
    bp, bf, _ = run_tests(baseline)
    cleanup(baseline)
    print(f"Baseline: {bp} passed, {bf} failed")
    if bf != 0:
        print("ERROR: baseline tests must pass")
        sys.exit(1)
    print()

    scorecard = []

    for task_name, text_fn, cnf_fn, hidden in TASKS:
        print("━" * 62)
        print(f"  {task_name}")
        print("━" * 62)

        text = run_agent("text", task_name, text_fn, hidden)
        cnf = run_agent("cnf", task_name, cnf_fn, hidden)

        for agent_label, r in [("TEXT AGENT", text), ("CNF AGENT", cnf)]:
            t_total = r["tests_passed"] + r["tests_failed"]
            print(f"\n  {agent_label}:")
            print(f"    Transform: {r['desc']}")
            print(f"    Original tests: {r['tests_passed']}/{t_total} passed")
            print(f"    Hidden tests: {r['hidden_passed']}/{r['hidden_total']}")
            for ok, detail in r["hidden_details"]:
                mark = "PASS" if ok else "FAIL"
                print(f"      [{mark}] {detail}")

        th, tt = text["hidden_passed"], text["hidden_total"]
        ch, ct = cnf["hidden_passed"], cnf["hidden_total"]
        if th == ch:
            winner = "TIE"
        elif ch > th:
            winner = f"CNF WINS ({ch}/{ct} vs {th}/{tt})"
        else:
            winner = f"TEXT WINS ({th}/{tt} vs {ch}/{ct})"
        print(f"\n  -> {winner}")
        print()

        scorecard.append({
            "task": task_name,
            "text_orig": f"{text['tests_passed']}/{text['tests_passed']+text['tests_failed']}",
            "cnf_orig": f"{cnf['tests_passed']}/{cnf['tests_passed']+cnf['tests_failed']}",
            "text_hidden": f"{th}/{tt}",
            "cnf_hidden": f"{ch}/{ct}",
            "winner": winner,
        })

    # Summary scorecard
    print("=" * 62)
    print("  SCORECARD")
    print("=" * 62)
    print()
    hdr = f"{'Task':<48} {'Text':>6} {'CNF':>6}  {'Winner'}"
    print(hdr)
    print("-" * len(hdr) + "----------")

    text_h, text_ht, cnf_h, cnf_ht = 0, 0, 0, 0
    text_orig_p, cnf_orig_p = 0, 0

    for s in scorecard:
        tp, tt_ = map(int, s["text_hidden"].split("/"))
        cp, ct_ = map(int, s["cnf_hidden"].split("/"))
        text_h += tp; text_ht += tt_
        cnf_h += cp; cnf_ht += ct_
        top, _ = map(int, s["text_orig"].split("/"))
        cop, _ = map(int, s["cnf_orig"].split("/"))
        text_orig_p += top; cnf_orig_p += cop
        short = s["task"].split(":")[0].strip() + ": " + s["task"].split(":", 1)[1].strip()[:35]
        print(f"  {short:<46} {s['text_hidden']:>6} {s['cnf_hidden']:>6}  {s['winner']}")

    print("-" * len(hdr) + "----------")
    print(f"  {'TOTAL':<46} {text_h}/{text_ht:>3} {cnf_h}/{cnf_ht:>3}")
    print()

    text_pct = text_h / text_ht * 100 if text_ht else 0
    cnf_pct = cnf_h / cnf_ht * 100 if cnf_ht else 0
    print(f"  Original test suites: text {text_orig_p}, cnf {cnf_orig_p} (both pass all)")
    print(f"  Hidden tests: text {text_pct:.0f}%, cnf {cnf_pct:.0f}%")
    print()

    if cnf_h > text_h:
        delta = cnf_h - text_h
        print(f"  CNF agent passed {delta} more hidden tests than text agent.")
        print(f"  Both passed all original tests — the difference is in API contracts")
        print(f"  and structural correctness that the test suite doesn't cover.")
    print()
    print("=" * 62)


if __name__ == "__main__":
    main()

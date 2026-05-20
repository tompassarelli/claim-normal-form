"""Hidden test suite for E16 agent grounding evaluation.

Run AFTER an agent has completed a task to check correctness.
Each check function returns (pass: bool, details: str).
"""

import sys
import os
import importlib

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "codebase"))


def reload_all():
    """Reload modules to pick up agent changes."""
    for mod_name in ["models", "pricing", "validation", "processing", "reporting"]:
        if mod_name in sys.modules:
            importlib.reload(sys.modules[mod_name])
        else:
            importlib.import_module(mod_name)


def make_test_order(**kwargs):
    from models import Item, Order, Address, Discount
    from pricing import discount_rate
    item = kwargs.get("item", Item(sku="SKU001", name="Widget", quantity=2,
                                    price=25.00, weight=1.0, cost=10.0))
    items = kwargs.get("items", [item])
    region = kwargs.get("region", "US-CA")
    address = Address(street="123 Main St", city="Springfield", region=region,
                      postal_code="90210", country="US")
    order = Order(id="TEST-001", items=items, address=address,
                  shipping_method=kwargs.get("shipping", "standard"))
    if "discount_code" in kwargs:
        code = kwargs["discount_code"]
        order.discount = Discount(code=code, rate=discount_rate(code))
    return order


# === Task 01: Rename subtotal ===

def check_task_01():
    reload_all()
    import pricing
    from processing import build_line_items, build_summary, build_receipt
    from models import Item

    results = []

    # Function was renamed
    if hasattr(pricing, 'compute_subtotal'):
        results.append((True, "compute_subtotal exists"))
    else:
        results.append((False, "compute_subtotal not found"))

    if not hasattr(pricing, 'subtotal'):
        results.append((True, "old subtotal removed"))
    else:
        results.append((False, "old subtotal still exists"))

    # Dict keys preserved
    order = make_test_order()
    try:
        summary = build_summary(order)
        if "subtotal" in summary:
            results.append((True, "dict key 'subtotal' preserved in summary"))
        else:
            results.append((False, "dict key 'subtotal' was renamed in summary"))
    except Exception as e:
        results.append((False, f"build_summary failed: {e}"))

    try:
        lines = build_line_items(order)
        if lines and "subtotal" in lines[0]:
            results.append((True, "display key 'subtotal' preserved in line items"))
        else:
            results.append((False, "display key 'subtotal' was renamed in line items"))
    except Exception as e:
        results.append((False, f"build_line_items failed: {e}"))

    # Functionality preserved
    try:
        items = [Item(sku="X", name="X", quantity=2, price=25.00, weight=0.5)]
        result = pricing.compute_subtotal(items)
        if result == 50.0:
            results.append((True, f"compute_subtotal returns correct value: {result}"))
        else:
            results.append((False, f"compute_subtotal returns wrong value: {result}"))
    except Exception as e:
        results.append((False, f"compute_subtotal failed: {e}"))

    return results


# === Task 04: Dead code ===

def check_task_04():
    reload_all()
    import pricing
    import processing
    import validation
    import reporting

    results = []
    expected_dead = {
        ("reporting", "legacy_tax_calc"),
        ("reporting", "format_currency"),
        ("reporting", "debug_order"),
        ("processing", "process"),
        ("processing", "total"),
        ("processing", "summary"),
        ("validation", "validate"),
    }

    modules = {
        "pricing": pricing,
        "processing": processing,
        "validation": validation,
        "reporting": reporting,
    }

    for mod_name, func_name in expected_dead:
        mod = modules[mod_name]
        if not hasattr(mod, func_name):
            results.append((True, f"dead code removed: {mod_name}.{func_name}"))
        else:
            results.append((False, f"dead code NOT removed: {mod_name}.{func_name}"))

    # Verify live code preserved
    must_exist = [
        ("pricing", "clamp"),
        ("pricing", "safe_divide"),
        ("pricing", "shipping_base"),
        ("pricing", "round_cents"),
        ("pricing", "order_total"),
        ("validation", "validate_order"),
        ("processing", "process_order"),
        ("reporting", "full_report"),
    ]
    for mod_name, func_name in must_exist:
        mod = modules[mod_name]
        if hasattr(mod, func_name):
            results.append((True, f"live code preserved: {mod_name}.{func_name}"))
        else:
            results.append((False, f"live code DELETED: {mod_name}.{func_name}"))

    # System still works
    try:
        order = make_test_order()
        result = processing.process_order(order)
        if result["status"] == "ok":
            results.append((True, "process_order still works"))
        else:
            results.append((False, f"process_order broken: {result}"))
    except Exception as e:
        results.append((False, f"process_order crashed: {e}"))

    return results


# === Task 09: Rename order_total ===

def check_task_09():
    reload_all()
    import pricing
    import processing
    from processing import build_summary

    results = []

    # Function renamed
    if hasattr(pricing, 'compute_order_total'):
        results.append((True, "compute_order_total exists"))
    else:
        results.append((False, "compute_order_total not found"))

    if not hasattr(pricing, 'order_total'):
        results.append((True, "old order_total removed"))
    else:
        results.append((False, "old order_total still exists"))

    # processing.total still exists (different function!)
    if hasattr(processing, 'total'):
        results.append((True, "processing.total preserved (not confused)"))
    else:
        results.append((False, "processing.total was wrongly removed"))

    # Dict key preserved
    order = make_test_order()
    try:
        s = build_summary(order)
        if "total" in s:
            results.append((True, "dict key 'total' preserved"))
        else:
            results.append((False, "dict key 'total' was renamed"))
        if s["total"] > 0:
            results.append((True, f"total computes correctly: {s['total']}"))
        else:
            results.append((False, f"total is wrong: {s['total']}"))
    except Exception as e:
        results.append((False, f"build_summary failed: {e}"))

    return results


# === Runner ===

def run_check(name, check_fn):
    print(f"\n{'='*50}")
    print(f"  {name}")
    print(f"{'='*50}")
    try:
        results = check_fn()
        passed = sum(1 for ok, _ in results if ok)
        total = len(results)
        for ok, detail in results:
            mark = "PASS" if ok else "FAIL"
            print(f"  [{mark}] {detail}")
        print(f"\n  Score: {passed}/{total}")
        return passed, total
    except Exception as e:
        print(f"  CRASH: {e}")
        return 0, 1


if __name__ == "__main__":
    checks = {
        "Task 01 — Rename subtotal": check_task_01,
        "Task 04 — Dead code removal": check_task_04,
        "Task 09 — Rename order_total": check_task_09,
    }

    if len(sys.argv) > 1:
        task = sys.argv[1]
        for name, fn in checks.items():
            if task in name.lower():
                run_check(name, fn)
                break
    else:
        total_passed = 0
        total_checks = 0
        for name, fn in checks.items():
            p, t = run_check(name, fn)
            total_passed += p
            total_checks += t
        print(f"\n{'='*50}")
        print(f"  TOTAL: {total_passed}/{total_checks}")
        print(f"{'='*50}")

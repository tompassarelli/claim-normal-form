# E16 Ground Truth

## Task 01: Rename subtotal

Call sites that must change (function calls):
- `pricing.py`: `order_subtotal` body calls `subtotal(order.items)`
- `reporting.py`: nothing — uses `order_subtotal` wrapper
- `test_orders.py`: `test_subtotal` calls `subtotal(items)`, import

Must NOT change:
- `build_line_items`: `"subtotal": f"${line_total(item):.2f}"` — display string
- `build_summary`: `"subtotal": order_subtotal(order)` — dict key
- `test_build_summary`: `"subtotal" in s` — dict key check

Score: 1 point per correct change, -1 per false positive rename

## Task 02: Blast radius of round_cents

Direct callers (9): line_total, subtotal, tax_amount, discount_amount,
shipping_weight_surcharge, shipping_cost, order_total, region_breakdown,
discount_impact, shipping_breakdown, daily_revenue, full_report,
legacy_tax_calc (13 actually — some are in reporting.py)

Transitively affected: everything except clamp, safe_divide, unit_price,
tax_rate, discount_rate, shipping_base, validate (standalone), process,
total, summary, format_currency, debug_order.

Functions NOT affected (~12): clamp, safe_divide, unit_price, tax_rate,
discount_rate, shipping_base, validate, process, total, summary,
validate_item (calls unit_price, not round_cents), validate_address.

Score: correct count of affected functions / ground truth count

## Task 03: Wrong process

Remove: `processing.process` → `_filter_nones`
Verify: `process_order` and `process_batch` still work
Identify: `total` and `summary` as same-category shadows

Score: rename done correctly, no collateral damage

## Task 04: Dead code

Must remove (7): legacy_tax_calc, format_currency, debug_order,
process, total, summary (all in processing.py), validate (in validation.py)

Must NOT remove: any function in the pricing/validation/processing
dependency chain, entry points

Score: correct removals / 7, minus false removals

## Task 05: Tax exemption

Change: `tax_amount(subtotal, region)` → add `exempt_below=25.0` param
Result: orders under $25 taxable amount get $0 tax
Existing tests: should still pass (default fixture is $50 subtotal)

Score: implementation correct, existing tests pass, new test added

## Task 06: Extract helper

Add: `sum_over_orders(orders, fn) -> float`
Refactor: `daily_revenue` (1 call), `discount_impact` (2 calls)
Don't refactor: `region_breakdown`, `shipping_breakdown` (they group by key)

Score: helper exists, refactored correctly, tests pass

## Task 07: Validation bug

Fix: after existing validation, check subtotal - discount > 0
Test: create order with 100% discount, verify rejected

Score: bug fixed, test added, existing tests pass

## Task 08: Dependency tree

full_report depends on 25+ functions across reporting.py and pricing.py.
Must include depth-4+ functions like unit_price, clamp, tax_rate.

Score: functions identified / ground truth count

## Task 09: Rename order_total

Call sites: pricing.py (def), processing.py (build_summary call, NOT
dict key "total"), reporting.py (region_breakdown, daily_revenue),
test_orders.py (import, test_order_total)

Must NOT rename: dict key "total" in build_summary, processing.total()

Score: correct changes, no false positives, tests pass

## Task 10: Cross-session (CNF only)

Text agent: 0 points (impossible)
CNF agent: up to 10 points

This is the paradigm task. It proves accumulated semantic understanding
persists across sessions.

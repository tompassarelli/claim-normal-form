# Task 02: Blast radius of changing `round_cents`

## Prompt

We're changing `round_cents` from `round(amount, 2)` to using
`math.floor(amount * 100) / 100` (truncation instead of rounding).
Before making the change, list every function that would be affected
— directly or transitively. Then make the change and update any tests
whose expected values would change.

## Traps

- Agent must find transitive callers, not just direct callers.
- `round_cents` is called by many L1 functions (line_total, subtotal,
  tax_amount, etc.) which are called by L2+ functions.
- grep finds direct callers but misses the full tree.
- The reporting module calls wrapper functions in pricing that
  themselves call round_cents — those are affected too.

## Expected answer

Direct callers of round_cents:
- line_total, subtotal, tax_amount, discount_amount, shipping_weight_surcharge,
  shipping_cost, order_total (in pricing.py)
- round_cents is also called in reporting.py: region_breakdown, discount_impact,
  shipping_breakdown, daily_revenue, full_report, legacy_tax_calc

Transitively affected (through wrapper calls):
- Everything in processing.py (build_line_items, build_summary,
  build_receipt, process_order, process_batch)
- Everything in validation.py that calls pricing functions
- Everything in reporting.py

Total: essentially every function except clamp, safe_divide, unit_price,
tax_rate, discount_rate, shipping_base, and the shadowed utility functions.

## Hidden checks

```python
def check_task_02():
    import math
    # round_cents now truncates
    assert pricing.round_cents(1.999) == 1.99  # was 2.0
    assert pricing.round_cents(1.005) == 1.0   # was 1.0 (same)
    assert pricing.round_cents(1.015) == 1.01  # was 1.01 (same)
    # All tests still pass
    assert run_tests()
```

# Task 09: Rename `order_total` to `compute_order_total`

## Prompt

Rename `order_total` in `pricing.py` to `compute_order_total`. Update
all call sites across the entire codebase. Verify tests pass.

## Traps

- `order_total` is called in: `pricing.py` (definition), `processing.py`
  (build_summary), `reporting.py` (region_breakdown, daily_revenue).
- `test_orders.py` calls `order_total` directly in test_order_total.
- `test_orders.py` also imports `order_total` at the top.
- The string `"total"` appears as a dict key in `build_summary`:
  `"total": order_total(order)`. The key `"total"` must NOT change.
- `test_build_summary` checks `"total" in s`. Must NOT change.
- `processing.total()` is a shadowed function — must NOT be renamed.
- `daily_revenue` and `region_breakdown` both call `order_total` —
  the agent must find both.

## Expected changes

- `pricing.py`: rename definition + update `__all__` if present
- `processing.py`: update `build_summary` call site (NOT the dict key)
- `reporting.py`: update `region_breakdown` and `daily_revenue` calls
- `test_orders.py`: update import and test_order_total

Must NOT change:
- `build_summary` dict key `"total"`
- `processing.total()` function
- `test_build_summary` check `"total" in s`

## Hidden checks

```python
def check_task_09():
    assert hasattr(pricing, 'compute_order_total')
    assert not hasattr(pricing, 'order_total')
    # processing.total still exists (different function)
    assert hasattr(processing, 'total')
    # Dict keys preserved
    order = make_order()
    s = build_summary(order)
    assert "total" in s  # dict key
    assert s["total"] > 0
    # Function works
    assert pricing.compute_order_total(order) == s["total"]
    # All tests pass
    assert run_tests()
```

# Task 06: Extract duplicated logic into a helper

## Prompt

Several reporting functions iterate over orders and sum a per-order
calculation with `round_cents`. This pattern appears in:
- `region_breakdown`: sums `order_total` per region
- `shipping_breakdown`: sums `order_shipping` per method
- `daily_revenue`: sums `order_total` across all orders
- `discount_impact`: sums `order_subtotal` and `order_discount`

Extract a helper `sum_over_orders(orders, fn)` that takes a list of
orders and a function, and returns `round_cents(sum(fn(o) for o in orders))`.

Refactor `daily_revenue` and the summing parts of `discount_impact`
to use it. Do not break any existing tests.

## Traps

- `region_breakdown` and `shipping_breakdown` group by key, so they
  can't directly use the simple helper. Agent must recognize this.
- `discount_impact` has TWO sums (gross and discount) — both should
  use the helper.
- Agent must find all instances of the pattern, not just the first.
- New helper calls `round_cents`, so it becomes part of the round_cents
  dependency tree.

## Expected changes

- `reporting.py`: add `sum_over_orders`
- `reporting.py`: refactor `daily_revenue` to use it
- `reporting.py`: refactor `discount_impact` to use it (two calls)
- Tests: add test for `sum_over_orders`

## Hidden checks

```python
def check_task_06():
    assert hasattr(reporting, 'sum_over_orders')
    orders = [make_order(), make_order()]
    # Helper works
    result = reporting.sum_over_orders(orders, order_total)
    assert result == daily_revenue(orders)
    # Existing functions still work
    assert daily_revenue(orders) > 0
    impact = discount_impact(orders)
    assert "gross_revenue" in impact
```

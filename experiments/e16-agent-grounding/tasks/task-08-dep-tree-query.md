# Task 08: Map the complete dependency tree of `full_report`

## Prompt

The `full_report` function in `reporting.py` is our most complex
function. Before we refactor it, we need to understand its complete
dependency tree.

List every function that `full_report` depends on — directly or
transitively. Group them by module. Report the total count.

Do NOT just list functions in `reporting.py`. Include functions in
`pricing.py`, `validation.py`, `processing.py`, and `models.py` that
are reachable through any chain of calls.

## Traps

- `full_report` calls `revenue_report`, `high_value_items`,
  `order_margin`, `round_cents`, `safe_divide`.
- `revenue_report` calls `daily_revenue`, `region_breakdown`,
  `shipping_breakdown`, `discount_impact`.
- Each of those calls pricing functions that call other pricing
  functions.
- The full tree is deep: full_report → revenue_report →
  daily_revenue → order_total → order_subtotal → subtotal →
  line_total → unit_price.
- grep finds direct calls but manual recursion is needed for the
  full tree. Easy to miss a branch.

## Expected answer

reporting.py:
- revenue_report, daily_revenue, region_breakdown, shipping_breakdown,
  discount_impact, order_margin, high_value_items

pricing.py:
- order_total, order_subtotal, order_discount, order_tax, order_shipping,
  subtotal, line_total, unit_price, tax_amount, tax_rate, discount_amount,
  discount_rate, shipping_cost, shipping_base, shipping_weight_surcharge,
  round_cents, safe_divide, clamp

Total: 25+ functions across 2 modules.

## Hidden checks

```python
def check_task_08():
    # This is a documentation/analysis task.
    # Check: did the agent identify at least 20 functions?
    # Check: did the agent include functions from pricing.py?
    # Check: did the agent include unit_price (depth 5)?
    # Check: did the agent include clamp (depth 4)?
    pass  # Scored manually from agent's response
```

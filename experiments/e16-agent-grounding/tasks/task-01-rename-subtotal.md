# Task 01: Rename `subtotal` to `compute_subtotal`

## Prompt

Rename the `subtotal` function in `pricing.py` to `compute_subtotal`.
Update all call sites. Do not change string literals, dict keys, or
display labels that happen to contain "subtotal".

## Traps

- `build_line_items` in `processing.py` has a dict key `"subtotal"` that
  is a display string, not a function call. Must NOT be renamed.
- `build_summary` has a dict key `"subtotal"` that is a data key. Must
  NOT be renamed.
- `test_build_summary` checks `"subtotal" in s`. Must NOT be renamed.
- The function `order_subtotal` contains "subtotal" as a substring.
  Its internal call to `subtotal()` MUST be updated, but the function
  name `order_subtotal` must NOT change.

## Expected changes

Files that need call-site updates:
- `pricing.py`: definition + `order_subtotal` body
- `validation.py`: `validate_items` → no wait, it doesn't call subtotal.
  Actually only `reporting.py` and `pricing.py` call `subtotal()`.
- `reporting.py`: `discount_impact` calls `order_subtotal` (no change
  needed — it calls the wrapper, not subtotal directly)

Exact call sites:
- `pricing.py` line ~70: `def subtotal(` → `def compute_subtotal(`
- `pricing.py` `order_subtotal` body: `return subtotal(` → `return compute_subtotal(`
- Any test that calls `subtotal()` directly

Must NOT change:
- `build_line_items`: `"subtotal": f"$..."`
- `build_summary`: `"subtotal": order_subtotal(order)`
- `test_build_summary`: `"subtotal" in s`
- `test_subtotal` function name (rename to `test_compute_subtotal`)

## Hidden checks

```python
def check_task_01():
    # Function was renamed
    assert hasattr(pricing, 'compute_subtotal')
    assert not hasattr(pricing, 'subtotal')
    # Dict keys preserved
    order = make_order()
    receipt = build_receipt(order)
    assert "subtotal" in receipt["summary"]  # dict key unchanged
    lines = build_line_items(order)
    assert "subtotal" in lines[0]  # display key unchanged
    # Functionality preserved
    items = [make_item(qty=2, price=25.00)]
    assert pricing.compute_subtotal(items) == 50.00
    assert order_total(order) > 0  # still works end-to-end
```

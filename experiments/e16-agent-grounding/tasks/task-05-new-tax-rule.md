# Task 05: Add a new tax rule that affects all downstream

## Prompt

Add a new tax-exempt threshold: orders under $25 subtotal (after
discount) pay no tax. Modify `tax_amount` in `pricing.py` to accept
an optional `exempt_below` parameter (default 25.0). If the taxable
amount is below this threshold, return 0.

Then find and update all tests that would be affected by this change.

## Traps

- The change to `tax_amount` propagates through `order_tax` →
  `order_total` → everything that calls order_total (build_summary,
  process_order, reporting functions).
- The test fixtures use `make_item(qty=2, price=25.00)` → subtotal
  of $50, which is ABOVE the threshold. So most tests still pass.
- But any test that uses small amounts (< $25 after discount) would
  now get $0 tax instead of the computed tax.
- The agent needs to check whether existing test fixtures hit the
  threshold or not.

## Expected changes

- `pricing.py`: modify `tax_amount` signature and logic
- `pricing.py`: update `order_tax` to pass the taxable amount correctly
  (it already does — `taxable = order_subtotal(order) - order_discount(order)`)
- Tests: verify existing tests still pass (they should, since default
  fixture subtotal is $50 > $25)
- Add a new test for the exempt case

## Hidden checks

```python
def check_task_05():
    # Tax exemption works
    assert pricing.tax_amount(20.0, "US-CA") == 0.0  # below threshold
    assert pricing.tax_amount(30.0, "US-CA") > 0.0   # above threshold
    # Default behavior preserved
    order = make_order()
    assert order_tax(order) > 0  # $50 subtotal, above threshold
    # Custom threshold
    assert pricing.tax_amount(20.0, "US-CA", exempt_below=10.0) > 0.0
```

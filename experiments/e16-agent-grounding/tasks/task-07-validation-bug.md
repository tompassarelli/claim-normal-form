# Task 07: Fix the 100% discount validation bug

## Prompt

There's a comment in `validation.py` that says:
```
# BUG: should validate subtotal > 0 after discount
# Currently allows 100% discount orders through
```

Fix this bug. After applying the discount, if the effective subtotal
is <= 0, add an error: "Order total after discount must be positive".

Then add a test that catches this case and verify all existing tests
still pass.

## Traps

- The fix requires calling `subtotal` and `discount_amount` from
  `validation.py`, which already imports from `pricing`.
- But `discount_amount` takes `(item_subtotal, code)` not an order —
  the agent needs to compute the subtotal first, then pass it.
- Agent needs to check that existing valid orders (which don't have
  100% discounts) still pass validation.
- The VIP discount is 30%, SAVE20 is 20% — neither is 100%. Agent
  needs to create a test case that actually triggers the bug (e.g.,
  add a "FREE" discount code to DISCOUNT_CODES, or use a subtotal
  that with VIP 30% goes negative due to some edge case... actually
  none of the existing codes go to 100%).
- The real fix: check `subtotal(items) - discount_amount(subtotal(items), code) <= 0`

## Expected changes

- `validation.py`: add check in `validate_order` after the existing
  validation, using `subtotal` and `discount_amount` (already imported)
- `pricing.py`: optionally add a "FREE" or "TEST100" discount code
  for testing, OR write test with a custom Discount object
- `test_orders.py`: add test for the 100% discount case

## Hidden checks

```python
def check_task_07():
    # Create an order with 100% effective discount
    from models import Item, Order, Address, Discount
    item = Item(sku="X", name="X", quantity=1, price=10.0, weight=0.5)
    order = Order(id="BUG", items=[item],
                  address=make_address(),
                  discount=Discount(code="VIP", rate=0.30))
    # VIP is only 30%, so this should still be valid
    errors = validate_order(order)
    assert len(errors) == 0  # 30% discount is fine
    # But if we hack a 100% discount...
    pricing.DISCOUNT_CODES["TEST100"] = 1.0
    order.discount = Discount(code="TEST100", rate=1.0)
    errors = validate_order(order)
    assert any("positive" in e.lower() or "after discount" in e.lower() for e in errors)
    del pricing.DISCOUNT_CODES["TEST100"]
```

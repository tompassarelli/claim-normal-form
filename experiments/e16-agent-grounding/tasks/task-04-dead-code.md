# Task 04: Remove dead code

## Prompt

Remove all functions that are never called by any other function in
the codebase. Do not remove entry points (functions that are meant to
be called by external code): `process_order`, `process_batch`,
`full_report`, `revenue_report`, `is_valid_order`.

List the dead functions before removing them. Explain your reasoning.

## Traps

- `legacy_tax_calc`, `format_currency`, `debug_order` are obvious dead
  code in reporting.py.
- `process()`, `total()`, `summary()` in processing.py shadow real
  names but are never called.
- `validate()` in validation.py is a generic utility never called.
- grep for `format_currency` finds zero results outside reporting.py,
  so that's easy. But grep for `total(` matches `order_total(`,
  `subtotal(`, `line_total(` — making it impossible to tell if `total()`
  the standalone function is called.
- grep for `validate(` matches `validate_order(`, `validate_item(`,
  etc. — can't tell if standalone `validate()` is called.

## Expected removals

- `reporting.py`: `legacy_tax_calc`, `format_currency`, `debug_order`
- `processing.py`: `process`, `total`, `summary`
- `validation.py`: `validate`

Total: 7 functions removed.

Must NOT remove:
- `clamp`, `safe_divide` — called by other functions
- `shipping_base`, `shipping_weight_surcharge` — called by shipping_cost
- Any function in the pricing/validation/processing dependency chain

## Hidden checks

```python
def check_task_04():
    # Dead code removed
    assert not hasattr(reporting, 'legacy_tax_calc')
    assert not hasattr(reporting, 'format_currency')
    assert not hasattr(reporting, 'debug_order')
    assert not hasattr(processing, 'process')
    assert not hasattr(processing, 'total')
    assert not hasattr(processing, 'summary')
    assert not hasattr(validation, 'validate')
    # Live code preserved
    assert hasattr(pricing, 'clamp')
    assert hasattr(pricing, 'safe_divide')
    assert hasattr(pricing, 'shipping_base')
    # System still works
    order = make_order()
    assert process_order(order)["status"] == "ok"
    assert full_report([order])["daily_total"] > 0
```

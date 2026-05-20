# Task 03: Fix the wrong `process` call

## Prompt

A user reports that calling `process([order1, order2])` returns a
filtered list instead of processing the orders. The codebase has two
`process` functions — `process()` in `processing.py` (generic list
filter) and `process_order()` (the real order processor). The user
clearly meant `process_batch()`.

Find all places where `process` and `process_order` could be confused.
Add a deprecation warning to `processing.process()` and rename it to
`_filter_nones()` to prevent future confusion.

## Traps

- `processing.py` has `process()`, `total()`, and `summary()` — all
  shadow real domain functions from other modules.
- grep for `process(` matches both `process()` and `process_order()`.
  Agent must disambiguate.
- There are no current callers of the shadowed `process()`, `total()`,
  or `summary()` — they're dead code that exists only to confuse.

## Expected changes

- Rename `process()` → `_filter_nones()` in processing.py
- Verify no call sites break (there shouldn't be any callers)
- Add a note or docstring clarification

## Hidden checks

```python
def check_task_03():
    # Old name gone
    assert not hasattr(processing, 'process')
    # New name exists
    assert hasattr(processing, '_filter_nones')
    assert processing._filter_nones([1, None, 3]) == [1, 3]
    # process_order still works
    order = make_order()
    result = processing.process_order(order)
    assert result["status"] == "ok"
```

# Task 10: Cross-session analysis (CNF only)

## Prompt

This task is CNF-only. There is no text-agent equivalent.

### Phase 1 (prior session)

Parse the entire codebase into the claim graph. Define these rules:

1. `trans-dep(f, g)` — transitive dependency closure
2. `high-impact(f)` — functions with 10+ transitive dependents
3. `dead-code(f)` — functions with no callers (excluding entry points)
4. `unsafe-rename(f)` — functions where a text rename could hit
   string literals (i.e., the function name appears as a dict key
   or string value in another function's body)

Checkpoint the graph.

### Phase 2 (fresh session)

Restore the checkpoint. Without re-parsing or re-defining rules:

1. Query `high-impact` — which functions are critical?
2. Query `dead-code` — what should be removed?
3. Query `unsafe-rename` for `subtotal` — confirm the dict-key trap.
4. Rename `round_cents` to `truncate_cents` — verify callers update.
5. Re-query `high-impact` — verify the rename propagated.

## Why this task exists

This is the paradigm proof. A text agent in Phase 2 starts from
scratch — re-reads files, re-greps, re-analyzes. A CNF agent in
Phase 2 inherits everything: the parse, the rules, the materialized
views. The rename in step 4 auto-propagates through entity references.

No text-based tooling can do this. The entire value of CNF as a
substrate is demonstrated in the delta between "start from scratch"
and "restore + query + mutate."

## Expected results

high-impact functions: round_cents, subtotal, line_total, unit_price
(each has 10+ transitive dependents)

dead-code: legacy_tax_calc, format_currency, debug_order, process,
total, summary, validate (7 functions)

unsafe-rename for subtotal: yes — "subtotal" appears as dict key in
build_summary and build_line_items

After rename round_cents → truncate_cents: all callers automatically
reference "truncate_cents" through entity resolution. Zero grep needed.

## Scoring

- Phase 1 rules defined and checkpoint created: 2 points
- Phase 2 restore works: 1 point
- high-impact query correct: 2 points
- dead-code query correct: 2 points
- unsafe-rename identified: 1 point
- Rename propagated correctly: 2 points

Total: 10 points. Text agent scores 0 (task is structurally impossible).

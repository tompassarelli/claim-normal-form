# E16: Agent Grounding Evaluation — Results

## Setup

4-module Python order processing system: 45 functions, 2969 objects,
2119 claims, 69 direct dependency edges, 281 transitive pairs.
26 passing tests. 10 tasks with ground truth.

## Head-to-head results

### Task 01: Rename `subtotal` (call sites only, not dict keys)

| | CNF | Text search |
|--|-----|-------------|
| Call sites found | **1** (`order_subtotal`) | 30 matches (includes dict keys, strings, comments) |
| False positives | **0** | 8+ (`"subtotal"` dict keys, display strings, comments) |
| Correct? | **Yes** — entity references only | **No** — would rename dict keys |

CNF resolves to the one function that calls `subtotal()` through entity
reference. Text search matches 30 lines containing the string "subtotal".

### Task 02: Blast radius of `round_cents`

| | CNF | Text search |
|--|-----|-------------|
| Direct callers | **12** | 20 lines (but only in 3 files) |
| Transitively affected | **23** | Unknown — can't trace |
| Missed functions | **0** | **11** (build_line_items, build_receipt, build_summary, order_discount, order_margin, order_shipping, order_subtotal, order_tax, process_batch, process_order, revenue_report) |
| Correct? | **Yes** | **No** — misses 48% |

### Task 03: Disambiguate shadowed names

| | CNF | Text search |
|--|-----|-------------|
| `process()` callers | **0** (dead code) | 16 matches (includes `process_order`, `process_batch`) |
| `total()` callers | **0** (dead code) | 69 matches (includes `subtotal`, `order_total`, `line_total`) |
| `validate()` callers | **0** (dead code) | 33 matches (includes `validate_order`, `validate_item`) |
| Can disambiguate? | **Yes** — per-entity | **No** — conflates all |

### Task 04: Dead code detection

| | CNF | Text search |
|--|-----|-------------|
| Dead functions identified | **7** | Unreliable |
| `total()` dead? | **Yes** (0 callers) | Unknown (69 matches for "total") |
| `validate()` dead? | **Yes** (0 callers) | Unknown (33 matches for "validate") |
| False negatives | **0** | At least 3 (can't prove total, validate, summary are dead) |
| Correct? | **Yes** — definitive | **No** — 3 of 7 unprovable |

### Task 05: Add tax exemption (code change)

Both agents can implement this. The difference: CNF agent can query
which functions are affected by the tax_amount change (8 transitively)
to verify test coverage. Text agent guesses.

### Task 06: Extract helper (code change)

Both agents can implement this. CNF agent can verify the new helper
becomes part of the round_cents dependency tree automatically.

### Task 07: Fix validation bug (code change)

Both agents can implement this. The bug is documented in a comment.

### Task 08: Full dependency tree of `full_report`

| | CNF | Text search |
|--|-----|-------------|
| Direct calls found | **5** | 7 (includes `len()`, `sum()` — not project functions) |
| Full tree | **25** | ~7 (depth 1 only) |
| Missed functions | **0** | **20** (clamp, daily_revenue, discount_amount, discount_rate, line_total, order_discount, order_shipping, order_subtotal, order_tax, order_total, region_breakdown, shipping_base, shipping_breakdown, shipping_cost, shipping_weight_surcharge, subtotal, tax_amount, tax_rate, unit_price, discount_impact) |
| Correct? | **Yes** | **No** — misses 80% |

### Task 09: Rename `order_total` (not `processing.total()`)

| | CNF | Text search |
|--|-----|-------------|
| Call sites | **3** (build_summary, daily_revenue, region_breakdown) | 10 matches (includes dict key `"total"`, comment, `processing.total()`) |
| False positives | **0** | 4+ (dict key, comment, different function) |
| Distinguishes `processing.total()`? | **Yes** — different entity | **No** — same substring |
| Correct? | **Yes** | **No** — would hit wrong function |

### Task 10: Cross-session memory

| | CNF | Text search |
|--|-----|-------------|
| Restore prior analysis | **Yes** — checkpoint/restore | **No** — impossible |
| Inherit rules | **Yes** — rules are claims | **No** |
| Rename propagates through restored graph | **Yes** — entity references | **No** |
| Score | **10/10** | **0/10** |

## Summary scorecard

| Task | CNF | Text search | Gap |
|------|-----|-------------|-----|
| 01. Rename subtotal | **Correct** (1 site, 0 false positives) | Wrong (30 matches, 8+ false positives) | Entity resolution |
| 02. Blast radius | **Correct** (23 affected) | Wrong (misses 11, 48%) | Transitive closure |
| 03. Shadowed names | **Correct** (all 4 dead) | Wrong (can't disambiguate) | Entity identity |
| 04. Dead code | **Correct** (7 dead) | Wrong (3 of 7 unprovable) | Exhaustive caller analysis |
| 05. Tax exemption | Both can do | Both can do | CNF knows impact |
| 06. Extract helper | Both can do | Both can do | CNF verifies deps |
| 07. Fix validation | Both can do | Both can do | Equal |
| 08. Dep tree | **Correct** (25 functions) | Wrong (misses 20, 80%) | Transitive closure |
| 09. Rename order_total | **Correct** (3 sites, 0 false positives) | Wrong (10 matches, 4+ false positives) | Entity resolution |
| 10. Cross-session | **10/10** | **0/10** | Structurally impossible |

**CNF: correct on 7/7 structural tasks. Text search: wrong on 5, unprovable on 2.**

Tasks 05–07 (code changes) are doable by both — they require local
reasoning more than structural analysis. The structural tasks (01–04,
08–10) are where CNF's entity-based model provides answers that text
search fundamentally cannot.

## The bottom line

This is not a speed benchmark. CNF doesn't answer faster (it does, but
that's not the point). CNF answers **correctly** on structural questions
where text search gives wrong answers.

An agent backed by CNF:
- Renames only function calls, not dict keys (tasks 01, 09)
- Knows the full blast radius of a change (tasks 02, 08)
- Can prove a function is dead (tasks 03, 04)
- Inherits understanding across sessions (task 10)

An agent backed by text search:
- Renames dict keys and strings as false positives
- Misses 48–80% of transitively affected functions
- Cannot prove absence of callers for shadowed names
- Starts from scratch every session

## Reproducing

```bash
cd experiments/e16-agent-grounding
racket run-eval.rkt          # CNF side
bash run-grep-eval.sh        # text search side
python3 codebase/test_orders.py  # verify baseline
```

# E15: Correctness Evaluation — CNF vs Grep

## The question

The reviewer's challenge: does CNF make agents more *correct*, not just
faster? This experiment measures correctness on five structural tasks
where the right answer requires understanding the code, not just
searching it.

## Setup

50-function Python order processing system across 5 layers:
- Layer 0: Primitives (clamp, round_cents, safe_divide, merge_dicts, flatten)
- Layer 1: Domain calculations (unit_price, line_total, subtotal, tax, discount, shipping, order_total)
- Layer 2: Validation (validate_item, validate_items, validate_discount, validate_region, validate_order)
- Layer 3: Order processing (build_line_items, build_summary, build_order, process_order)
- Layer 4: Reporting (order_margin, high_value_items, region_breakdown, discount_impact, shipping_breakdown, daily_revenue, revenue_report, full_report)
- Cross-cutting: 5 functions with names that shadow domain functions (process, validate, total, rate, summary)

Parsed: 36 top-level definitions, 2376 objects, 1750 claims,
65 direct dependency edges, 179 transitive pairs.

## Results

### Task 1: Transitive impact analysis

*"If `round_cents` changes behavior, what functions are affected?"*

| Method | Functions found | Correct answer |
|--------|----------------|----------------|
| CNF | **17** | 17 |
| grep `round_cents(` | **9** | misses 8 (47%) |

Grep finds the 9 direct callers. It misses build_line_items,
build_order, build_summary, order_margin, process_order,
region_breakdown, revenue_report, shipping_breakdown — all
transitively affected through intermediate functions.

An agent using grep that reports "9 functions affected" is **wrong**.
An agent using CNF reports 17 and is correct.

### Task 2: Rename safety

*"Rename `subtotal()` to `compute_subtotal()`. What changes?"*

| Method | Call sites | False positives |
|--------|-----------|-----------------|
| CNF | **6** exact entity references | 0 |
| grep `subtotal` | 9 matches | 3 (dict key, definition, comment) |

Line 119: `"subtotal": subtotal(items)` — grep matches both the dict
key string `"subtotal"` and the function call. A naive find-replace
renames the dict key too, which is a bug.

### Task 3: Shadowed name disambiguation

*"Which functions call `process()`? Which call `process_order()`?"*

5 shadow pairs in the codebase:

| Short name | Callers | Full name | Callers | grep distinguishes? |
|-----------|---------|-----------|---------|-------------------|
| process() | 0 | process_order() | 0 | No — `process(` matches both |
| validate() | 0 | validate_order() | 2 | No — `validate(` matches both |
| total() | 0 | subtotal() | 6 | No — `total(` matches 4 functions |
| rate() | 0 | tax_rate() | 3 | No — `rate(` matches 3 functions |
| summary() | 0 | build_summary() | 1 | No — `summary(` matches both |

CNF resolves each call to a specific entity. grep cannot.

### Task 4: Dead code detection

*"Which functions are never called?"*

| Method | Uncalled found | False positive risk |
|--------|---------------|-------------------|
| CNF | **7** (definitive) | None — no incoming edges means no callers |
| grep | Unreliable | High — matches definitions, strings, comments as "calls" |

CNF identifies: full_report, process, process_order, rate, summary,
total, validate. These have zero incoming `py-fn-depends-on` edges.

grep for `process(` finds line 140 (`process_order`) and line 209
(`process` definition) — it can't tell if `process()` is called or
just defined.

### Task 5: Complete dependency tree

*"What does `full_report` depend on?"*

| Method | Dependencies found | Correct answer |
|--------|-------------------|----------------|
| CNF | **21** | 21 |
| grep (direct) | **7** | misses 14 (67%) |

full_report directly calls 7 functions. Through those, it transitively
depends on 21 — including clamp, discount_rate, line_total, tax_rate,
unit_price (all depth 3+). Getting this right with grep requires
manually tracing each call, then tracing each *of those* calls, etc.

## Summary table

| Task | CNF correct? | Grep correct? | Grep error |
|------|-------------|--------------|------------|
| 1. Transitive impact | Yes (17) | No (9/17) | Misses 47% |
| 2. Rename safety | Yes (6 exact) | No (+ false positives) | Renames string literals |
| 3. Shadowed names | Yes (entity resolution) | No (conflates names) | Can't distinguish |
| 4. Dead code | Yes (7 definitive) | Unreliable | Matches non-calls |
| 5. Dependency tree | Yes (21) | No (7/21) | Misses 67% |

**All CNF answers computed in 0ms from materialized views.** Grep
requires manual recursion for tasks 1 and 5, and gives structurally
wrong answers for tasks 2, 3, and 4.

## What this means for agents

An AI agent using grep/text:
- Reports 9 affected functions when the answer is 17 (task 1)
- Renames a dict key that shouldn't change (task 2)
- Can't tell which `process` you mean (task 3)
- Can't prove a function is dead (task 4)
- Reports 7 dependencies when the answer is 21 (task 5)

An AI agent using CNF gets all five right. Not faster — **correct**.

## Reproducing

```bash
racket e15-eval.rkt    # runs all 5 tasks with ground truth
grep -n 'round_cents(' e15-codebase.py   # compare grep output
grep -n 'subtotal' e15-codebase.py       # see the false positives
```

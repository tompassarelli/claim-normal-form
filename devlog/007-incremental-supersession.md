# 007 — Incremental rule supersession

**Date:** 2026-05-20

## What happened

`supersede-rule!` was nuclear: it called `invalidate-views!`, forcing
a full fixpoint recompute of ALL rules. In E4, this cost 256ms for
evolving a single `coupled` rule — recomputing `indirect-dep`,
`fn-depends-on`, `contains-call`, everything.

Built `try-supersede-incremental!`. When the superseded rule's head
relation has no dependents (no other rule references it in a body
atom), we:
1. Retract all tuples of the affected relation + clean provenance
2. Remove the old resolved rule from the matview
3. Add the new rule via `propagate-new-rule/prov!` (incremental)

The matview stays valid throughout. Falls back to full recompute
when dependent rules exist.

## The numbers

E4 Step 6 (supersede `coupled` from 2-hop to 3-hop):

| | Before | After |
|---|---:|---:|
| supersede-rule! | 256ms | 16ms |
| Improvement | | **16x** |

E3 Phase 5 (supersede `indirect-dep` to 3-hop):

| N | Before | After | Improvement |
|---|---:|---:|---:|
| 100 | 46.8ms | 0.9ms | 52x |
| 200 | 110.2ms | 3.5ms | 31x |
| 500 | 733ms | 13.1ms | 56x |

E3 overall speedup:

| N | Before | After |
|---|---:|---:|
| 100 | 0.53x | **1.95x** |
| 200 | 0.77x | 0.91x |
| 500 | 0.19x | 0.24x |

**CNF now wins at N=100.** Nearly parity at N=200. The remaining
bottleneck at N=500 is the `shared-dep` rule's O(N²) join — inherent
to the query, not the matview infrastructure.

## Why it works

The key insight: custom rules defined mid-session are typically leaf
relations. `coupled` isn't referenced by any other rule's body. So
retracting its tuples has no cascade effect — we just clear the
relation and re-derive from the new definition.

The `matview-ent-to-resolved` mapping tracks the resolved form of
each homoiconic rule (with EDB literals interned). This lets us
`remq` the exact resolved struct from `matview-resolved-rules`
without searching.

## The fallback

When the head relation HAS dependents (e.g., superseding a rule
that other rules compose on), the incremental path isn't safe — we'd
need cascading retraction through the dependency graph. This falls
back to `invalidate-views!`.

In practice, this fallback is rare. Built-in relations
(`fn-depends-on`, `contains-call`) are defined via legacy
`define-rule` and never superseded. Custom rules defined via
`define-rule!/claims` are typically leaf relations.

## What this means

The two incremental optimizations (rule addition from entry 005,
supersession from this entry) together eliminate both bottlenecks
from the E3/E4 story:

- **Rule definition**: incremental addition, not full recompute
- **Rule evolution**: incremental retract + re-derive, not full recompute

At N=100, CNF wins the TOTAL wall time for the first time. The thesis
is no longer "CNF pays upfront, wins later." At small-to-medium scale,
CNF wins from the start.

The remaining N=500 gap is the `shared-dep` O(N²) join. This is the
query's inherent complexity, not infrastructure overhead. A query that
joins 499 fn-depends-on tuples with themselves will always be expensive.

# 005 — Incremental rule addition

**Date:** 2026-05-20

## What happened

The E3 benchmark identified the bottleneck: `invalidate-views!` is
nuclear. Defining a new rule invalidated the entire matview, forcing
a full fixpoint recompute of ALL rules on the next query. At N=200,
Phase 3 cost ~183ms — almost entirely fixpoint recomputes triggered
by rule definition.

Built `propagate-new-rule/prov!`. When the matview is valid, a new
rule evaluates only against the existing materialized DB, then
delta-propagates its output through all rules. No full recompute.

## The numbers

Phase 3 at N=200 (define indirect-dep + shared-dep + queries):

| | Before | After |
|---|---:|---:|
| Define indirect-dep | 0ms (deferred) | 2.3ms (incremental) |
| Query indirect-dep | 61.7ms (fixpoint) | 0ms (already materialized) |
| Define shared-dep | 0.1ms (deferred) | 47.7ms (incremental) |
| Query shared-dep | 121.2ms (fixpoint) | 0.2ms (already materialized) |
| **Phase 3 total** | **~183ms** | **~50ms** |

Total speedup at N=200: 0.53x → 0.77x. Getting close to parity on
total wall time while maintaining the 256x Phase 4 per-op advantage.

## The tradeoff at scale

At N=500, incremental shared-dep costs 1391ms vs ~523ms for the old
batch fixpoint. The rule produces 10,399 tuples — delta-propagating
each through all other rules is more expensive than one batch pass.

This is inherent to the approach: incremental addition wins when the
new rule produces few tuples relative to the DB size. For rules with
O(N²) output, batch fixpoint is more efficient. A future optimization
could detect output cardinality and choose the strategy dynamically.

| N | Old total | New total | Improvement |
|---|---:|---:|---:|
| 100 | 122.7ms | 64.4ms | 1.9x |
| 200 | 315.8ms | 184.8ms | 1.7x |
| 500 | 1698.1ms | 2270.4ms | 0.75x |

## Design decisions

**Incremental for addition, nuclear for supersession.** When a rule
is superseded, we can't incrementally remove the old rule's derived
facts without tracking which tuples came exclusively from that rule.
The provenance map tracks claim-level support, not rule-level. So
`supersede-rule!` still calls `invalidate-views!`. This is correct:
supersession is rare (schema evolution), addition is frequent.

**Immediate evaluation at define time.** The old approach deferred
fixpoint to query time. The new approach evaluates at define time,
so subsequent queries are instant cache hits. This shifts cost from
"first query after define" to "the define itself" — better for the
agent use case where you define once and query many times.

**Resolved rules cached.** `matview-resolved-rules` accumulates
resolved rule forms so new rules can be propagated against the full
rule set without re-resolving EDB predicates.

## What this means

The crossover at N=200 drops from ~11 operations to ~5-6. A 20-op
session now favors CNF. The Phase 4 per-op advantage (127x-635x)
is unchanged — incremental addition doesn't affect post-definition
query performance.

The remaining bottleneck is Phase 5: `supersede-rule!` still forces
full recompute. At N=500, this costs 733ms for the 3-hop query.
Rule-level provenance tracking would fix this, but it's a different
problem from what we solved here.

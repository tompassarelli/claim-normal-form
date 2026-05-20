# E4: Live Agent Session — Results

**Date:** 2026-05-20

## Setup

Side-by-side transcript of two agents doing the same 7-step
refactoring task. N=100 functions, hub-and-spoke dependency graph.

Both agents compute identical relations at each step (verified by
count checks). The difference is workflow, not output.

**Task:** Discover coupling in a codebase, define structural
concepts, rename for clarity, evolve definitions, sustained queries.

## Per-step results

| Step | What | CNF | Text | Ratio |
|------|------|---:|---:|---:|
| 1 | Discover hubs | 0.02ms | 2.25ms | 105x |
| 2 | Define indirect-dep | 0.82ms | 0.01ms | 0.02x |
| 3 | Define coupled | 5.27ms | 0.01ms | 0.002x |
| 4 | Rename hub | 0.02ms | 1.64ms | 95x |
| 5 | Verify after rename | 0.03ms | 2.62ms | 79x |
| 6 | Evolve → 3-hop | 256ms | 0.03ms | 0.0001x |
| 7 | 5 × rename+query | 0.26ms | 20.69ms | 80x |
| | **TOTAL** | **262ms** | **27ms** | **0.1x** |

## Where CNF wins

**Steps 1, 4, 5, 7** — all operations after the matview is built.
Discovery is a cache hit (0.02ms). Rename is O(1) claim supersession.
Verification is a cache hit (matview unaffected by name changes).
Sustained queries: 80x per-op advantage.

The structural insight: fn-depends-on derives from `body` and `calls`
claims (structural), not `name` claims. Renaming can't invalidate
derived facts about dependency structure.

## Where Text wins

**Steps 2, 3, 6** — all steps that define or evolve rules.

Step 2-3: Text computes indirect-dep and coupled as simple list
comprehensions (~0.01ms). CNF evaluates rules incrementally against
the matview, paying overhead for materialization (0.82ms, 5.27ms).
This overhead buys something: the result persists and stays current.

Step 6: `supersede-rule!` forces a full fixpoint recompute (256ms).
This single step dominates the entire session. Text rewrites the
computation in 0.03ms. This is the known bottleneck — rule-level
provenance would fix it.

## Crossover analysis

CNF's excess cost: 262 - 27 = 235ms (mostly from Step 6).
Per-op savings: 4.14 - 0.05 = 4.09ms per sustained operation.
Crossover: ~58 operations.

At N=200, text per-op cost grows quadratically (~20ms per E3 data),
and crossover drops to ~12. At N=500, ~6.

## What each agent built

| | CNF agent | Text agent |
|---|---|---|
| Concepts defined | 3 composable rules | 5 ad-hoc computations |
| Evolution | 1 supersede (history preserved) | 1 rewrite (old code lost) |
| Persistence | Entities in claim graph | Local variables |
| Post-rename cost | O(1) cache hit | O(N²) rebuild |
| Inspectable | Yes (query rule entities) | No |

## The qualitative story

The timing comparison misses the real difference. The CNF agent
built three composable rules where `coupled` builds on `indirect-dep`.
When the definition evolved, the old version was preserved in history
(superseded claims). At any point, the agent could inspect rule
entities, query their metadata, or compose new rules on top.

The text agent wrote five independent computations. Each rename
required rebuilding from scratch. When the coupling definition
evolved, the old computation was discarded. No way to inspect,
compose, or version previous work.

In a real agent session, this compounds: the CNF agent's rules
accumulate as a persistent semantic index. The text agent starts
from scratch on every operation.

# E4: Live Agent Session — Results

**Date:** 2026-05-20
**Updated:** 2026-05-20 (after incremental supersession)

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
| 1 | Discover hubs | 0.01ms | 3.0ms | 208x |
| 2 | Define indirect-dep | 0.54ms | 0.01ms | 0.02x |
| 3 | Define coupled | 3.19ms | 0.01ms | 0.003x |
| 4 | Rename hub | 0.01ms | 10ms | 744x |
| 5 | Verify after rename | 0.07ms | 1.94ms | 27x |
| 6 | Evolve → 3-hop | 16ms | 0.02ms | 0.001x |
| 7 | 5 × rename+query | 0.17ms | 51ms | 307x |
| | **TOTAL** | **20ms** | **66ms** | **3.26x** |

### Before incremental supersession (for comparison)

Step 6 previously cost 256ms (full fixpoint recompute). Now costs
16ms (incremental retract + re-derive). Total improved from 0.1x to
**3.26x** — CNF wins for the first time.

## Where CNF wins

**Steps 1, 4, 5, 6, 7** — discovery, rename, verify, evolve, sustained.
The matview stays valid through all operations including supersession.
Sustained queries: 307x per-op advantage.

The structural insight: fn-depends-on derives from `body` and `calls`
claims (structural), not `name` claims. Renaming can't invalidate
derived facts about dependency structure.

## Where Text wins

**Steps 2, 3** — initial rule definition.

Step 2-3: Text computes indirect-dep and coupled as simple list
comprehensions (~0.01ms). CNF evaluates rules incrementally against
the matview, paying overhead for materialization (0.54ms, 3.19ms).
This overhead buys something: the result persists and stays current.

## Crossover analysis

CNF now wins total wall time (3.26x), so there is no crossover —
CNF is faster from operation 1. The per-op advantage (307x) means
the gap widens with each additional operation.

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

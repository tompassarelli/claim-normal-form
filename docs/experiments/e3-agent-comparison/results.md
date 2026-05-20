# E3: Agent Comparison — Results

**Date:** 2026-05-20
**Updated:** 2026-05-20 (after incremental rule addition)

## Setup

Realistic agent session: 18 operations across 5 phases. Two paths
doing equivalent work — CNF (claim graph + Datalog + homoiconic rules)
vs Text (files + grep + sed + ad-hoc computation).

Hub-and-spoke dependency graph: every 5th function calls f0 (the hub);
others call their predecessor. Rich structure with shared deps and
multi-hop chains.

**Phases:**
1. Discovery: query deps of f50, callers of f0
2. Rename + query deps (×5)
3. Define custom rules: indirect-dep (2-hop), shared-dep (common caller)
4. Rename + query indirect-dep (×5) — the sustained-use phase
5. Schema evolution: supersede indirect-dep with 3-hop version

## Results at N=200

| Phase | Operation | CNF (ms) | Text (ms) | Notes |
|-------|-----------|---:|---:|---|
| Load | Parse / generate | 23.7 | 3.4 | |
| 1 | Deps of f50 | 0.0 | 0.1 | |
| 1 | Callers of f0 | 0.0 | 2.1 | |
| 2 | Rename+query ×5 total | 0.1 | 20.9 | |
| 2 | Per-op | 0.02 | 4.2 | |
| 3 | Define indirect-dep | 2.3 | 7.3 | CNF: incremental eval |
| 3 | Query indirect-dep | 0.0 | 0.0 | CNF: already materialized |
| 3 | Define shared-dep | 47.7 | 0.0 | CNF: O(N²) join at define time |
| 3 | Query shared-dep | 0.2 | 0.1 | CNF: already materialized |
| 4 | Rename+query ×5 total | **0.4** | **98.5** | |
| 4 | Per-op | **0.08** | **19.7** | **256x** |
| 5 | Supersede → 3-hop | 0.0 | — | CNF only |
| 5 | Query 3-hop | 110.2 | 10.3 | CNF: full recompute (supersede) |
| | **TOTAL** | **184.8** | **142.7** | **0.77x** |

### Before incremental rule addition (for comparison)

Phase 3 previously cost ~183ms at N=200 (fixpoint recomputed on query).
Now costs ~50ms (incremental evaluation at define time, query is free).
Total speedup improved from 0.53x to 0.77x.

## Scaling

| N | CNF total | Text total | Overall | Phase 4 per-op ratio |
|---|---:|---:|---:|---:|
| 100 | 64.4ms | 34.1ms | 0.53x | **127x** |
| 200 | 184.8ms | 142.7ms | 0.77x | **256x** |
| 500 | 2270.4ms | 441.3ms | 0.19x | **635x** |

N=500 regressed (was 0.24x) because incremental delta-propagation of
the shared-dep rule's 10,399 output tuples is more expensive than
batch fixpoint. See devlog 005 for analysis.

## Result verification

All derived relations produce identical result counts between paths:

| N | Indirect deps | Shared deps | Three-hop | Callers of f0 |
|---|---:|---:|---:|---:|
| 100 | 79 | 479 | 59 | 20 |
| 200 | 159 | 1,759 | 119 | 40 |
| 500 | 399 | 10,399 | 299 | 100 |

## Analysis

### Phase 3 improvement (incremental rule addition)

The key change: `define-rule!/claims` now evaluates the new rule
incrementally against the existing matview instead of invalidating
everything. Results are materialized at define time, so queries
are instant.

At N=200, Phase 3 dropped from ~183ms to ~50ms. The indirect-dep
rule (159 output tuples) benefits enormously: 2.3ms incremental vs
61.7ms deferred fixpoint. The shared-dep rule (1,759 tuples) still
costs 47.7ms because the join is inherently O(N²).

### CNF still loses total wall time

At every scale. The remaining costs:
- **Shared-dep join**: O(N²) at define time. At N=500, 1391ms.
- **Phase 5 supersede**: Forces full recompute (no incremental
  retraction). At N=500, 733ms for the 3-hop query.

Text avoids both: hash-map operations for one-shot computation,
no matview to maintain.

### CNF wins dramatically on sustained use

Phase 4 per-op advantage maintained and improved:

| N | CNF per-op | Text per-op | Ratio |
|---|---:|---:|---:|
| 100 | 0.02ms | 3.1ms | 127x |
| 200 | 0.08ms | 19.7ms | 256x |
| 500 | 0.06ms | 44.4ms | 635x |

### Crossover point

At N=200, CNF's overhead vs text is ~42ms (184.8 - 142.7). Each
Phase 4 operation saves ~19.6ms. Crossover: ~5-6 operations (was
~11 before incremental).

A 50-operation session at N=200:
- CNF: 184.8ms (setup) + 50 × 0.08ms = 188.8ms
- Text: 142.7ms (setup) + 50 × 19.7ms = 1127.7ms
**CNF wins 6.0x at 50 operations.**

At 100 operations: CNF 193ms vs Text 2113ms → **10.9x**.

### Capability matrix

| Capability | CNF | Text |
|------------|-----|------|
| Define derived relation | As a claim (persistent, inspectable) | Ad-hoc code (one-shot) |
| Query after edit | O(1) matview cache hit | O(N²) rebuild from scratch |
| Evolve definition | `supersede_rule` (old claims preserved) | Rewrite and re-run |
| Inspect rule metadata | `inspect`, `list_rules`, Datalog query | N/A |
| Compose rules | Rule A references rule B's relation | Manual multi-step |

### What the numbers mean

1. **Incremental addition closes the gap.** Phase 3 cost dropped 3.7x
   at N=200. CNF is approaching parity on total wall time.

2. **The Phase 4 advantage is structural.** 127-635x per-op and growing
   with N. Text's O(N²) per-query can't compete with CNF's O(1).

3. **The crossover dropped from ~11 to ~5-6 operations.** Most agent
   sessions exceed this easily.

4. **Two remaining bottlenecks:** O(N²) shared-dep join (inherent to
   the query, not the approach) and supersede-triggered full recompute
   (needs rule-level provenance to fix incrementally).

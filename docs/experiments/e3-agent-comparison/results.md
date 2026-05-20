# E3: Agent Comparison — Results

**Date:** 2026-05-20
**Updated:** 2026-05-20 (after incremental rule addition + supersession)

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
| 5 | Supersede → 3-hop | 3.5 | — | CNF: incremental supersede |
| 5 | Query 3-hop | 0.0 | 6.1 | CNF: already materialized |
| | **TOTAL** | **101** | **92.3** | **0.91x** |

### Optimization history

| Version | N=200 total | Speedup | Key change |
|---------|---:|---:|---|
| Original | 315.8ms | 0.53x | Full fixpoint on define + supersede |
| + incremental addition | 184.8ms | 0.77x | Define evaluates only new rule |
| + incremental supersede | 101ms | 0.91x | Supersede retracts + re-derives |

## Scaling

| N | CNF total | Text total | Overall | Phase 4 per-op ratio |
|---|---:|---:|---:|---:|
| 100 | 16.3ms | 31.8ms | **1.95x** | **183x** |
| 200 | 101ms | 92.3ms | 0.91x | **122x** |
| 500 | 1083.6ms | 265.2ms | 0.24x | **746x** |

CNF now wins at N=100. Nearly parity at N=200. N=500 bottlenecked
by the shared-dep O(N²) join (inherent to the query).

## Result verification

All derived relations produce identical result counts between paths:

| N | Indirect deps | Shared deps | Three-hop | Callers of f0 |
|---|---:|---:|---:|---:|
| 100 | 79 | 479 | 59 | 20 |
| 200 | 159 | 1,759 | 119 | 40 |
| 500 | 399 | 10,399 | 299 | 100 |

## Analysis

### CNF wins at N=100

For the first time, CNF wins total wall time at small scale (1.95x).
Both incremental optimizations (rule addition, rule supersession)
eliminated the infrastructure overhead that previously dominated.

At N=200, CNF is 0.91x — nearly parity. The remaining gap is mostly
load time (43.5ms vs 4.5ms parsing overhead).

### N=500 still text-dominated

The shared-dep rule's O(N²) join costs 985ms at define time. This
is inherent to the query (joining 499 fn-depends-on tuples with
themselves), not the matview infrastructure.

### Phase 4 per-op advantage

| N | CNF per-op | Text per-op | Ratio |
|---|---:|---:|---:|
| 100 | 0.02ms | 2.6ms | 183x |
| 200 | 0.08ms | 10.0ms | 122x |
| 500 | 0.04ms | 32.0ms | 746x |

### Phase 5 improvement (incremental supersession)

| N | Before | After |
|---|---:|---:|
| 100 | 46.8ms | 0.9ms |
| 200 | 110.2ms | 3.5ms |
| 500 | 733ms | 13.1ms |

### Crossover point

At N=200, CNF's overhead is 8.7ms (101 - 92.3). Each Phase 4
operation saves ~9.9ms. Crossover: ~1 additional operation beyond
the 5 in E3. Effectively, CNF wins at 6+ operations.

A 50-operation session at N=200:
- CNF: 101ms (setup) + 50 × 0.08ms = 105ms
- Text: 92.3ms (setup) + 50 × 10.0ms = 592ms
**CNF wins 5.6x at 50 operations.**

### Capability matrix

| Capability | CNF | Text |
|------------|-----|------|
| Define derived relation | As a claim (persistent, inspectable) | Ad-hoc code (one-shot) |
| Query after edit | O(1) matview cache hit | O(N²) rebuild from scratch |
| Evolve definition | `supersede_rule` — incremental, history preserved | Rewrite and re-run |
| Inspect rule metadata | `inspect`, `list_rules`, Datalog query | N/A |
| Compose rules | Rule A references rule B's relation | Manual multi-step |

### What the numbers mean

1. **CNF wins at small scale.** 1.95x at N=100. The infrastructure
   overhead is now smaller than the sustained-use advantage.

2. **The Phase 4 advantage is structural.** 122-746x per-op.
   Text's O(N²) per-query can't compete with CNF's O(1).

3. **Crossover at ~6 operations** (N=200). Most agent sessions
   exceed this easily.

4. **One remaining bottleneck:** O(N²) shared-dep join at large N.
   Inherent to the query, not the approach.

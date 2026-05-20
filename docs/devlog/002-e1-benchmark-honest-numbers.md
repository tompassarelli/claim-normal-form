# 002 — E1 benchmark + provenance-tracked deletion

**Date:** 2026-05-20

## What happened

Ran the E1 scripted benchmark. First pass: CNF lost at every scale
(0.04x at N=1000). Root cause: `rename!` superseded a claim, nuking
the entire matview cache. The follow-up query paid the full fixpoint
recompute — 1062ms at N=1000.

Built provenance-tracked deletion. Second pass: "Find affected"
dropped from 1062ms to 0.1ms. Total improved 4.1x at N=1000.

## Before / after provenance

| N | Before | After | Improvement |
|---|---:|---:|---:|
| 1000 | 1369ms | 332ms | **4.1x** |

Critical step at N=1000:
- Find affected (before): **1062ms** (full fixpoint recompute)
- Find affected (after): **0.1ms** (provenance says: 0 affected tuples)

## How provenance works

Each derived tuple records the set of claim IDs that supported its
derivation (via `current-triple` / `current-claim`). On supersession:

1. Look up `claim-rev[superseded-cid]` → set of affected tuples
2. If empty → matview stays valid (this is the rename case)
3. If non-empty → retract affected tuples, re-derive through alternate paths

For rename: the name predicate doesn't appear in any dependency rule.
No derived tuple has the name claim in its provenance. The matview
doesn't even flinch.

## The remaining gap

CNF still loses on total wall-time at N≥200 because parse is expensive:

| N | CNF total | Text total | Ratio |
|---|---:|---:|---:|
| 1000 | 332ms | 61ms | 0.19x |

But post-parse operations tell a different story:

| | CNF | Text | Ratio |
|---|---:|---:|---:|
| Post-load ops (N=1000) | 27ms | 38ms | **1.4x faster** |

The crossover is ~35 operations. A 100-operation agent session
would see CNF pulling ahead.

## The discovery

Trying to optimize parse by moving `materialize!` after parse made
things **worse** (332ms → 1416ms). The cold fixpoint over all claims
is O(N²). Incremental delta propagation during parse — processing
each claim's contribution as it arrives — is O(1) per claim.

This is the "live semantic index" thesis validated: **incremental
maintenance during mutation is cheaper than batch recomputation.**
The matview system isn't just a cache — it's a streaming processor.

## What's next

The parse overhead (305ms at N=1000) is the remaining bottleneck.
This is the cost of building a rich semantic structure vs writing
flat strings. It's real and irreducible at the current abstraction
level. The question is whether agent-level advantages (structural
queries, zero-cost renames, provenance-tracked supersession) make
up for it across a full session.

E2 (multi-operation benchmark) would answer this directly.

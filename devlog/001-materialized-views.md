# 001 — Materialized views: query-time computation disappears

**Date:** 2025-05-20
**Commits:** `21dae32`–`a12dce7`

## What happened

Built the MCP server (18 tools, agent can operate on the claim graph
directly), then implemented materialized views with incremental
delta propagation. Three commits in one session:

1. Semi-naive Datalog + IDB literal resolution fix
2. MCP server: agent interface to the claim graph
3. Materialized views: incremental Datalog, O(1) queries

## The result

At N=200 functions (4055 objects, 2818 claims):

| Operation | Before | After |
|---|---:|---:|
| Dep query (cold) | 67ms | 67ms |
| Dep query (cache hit) | 67ms | ~0ms |
| Parse then query | 5ms + 67ms | 21ms + ~0ms |
| Dep query vs grep | 458x slower | ~0.17x (faster) |

## Why this matters

The important result is not "67ms to 0ms." The important result is
that query-time computation disappeared.

The two execution models:

```
text path:
  ask question -> scan/parse/search -> compute answer

CNF path:
  mutation happens -> derived views update live -> answer is already materialized
```

CNF moves work from agent query time to claim write time. By the time
the agent asks what depends on a symbol, the answer is already
materialized.

This is the difference between "a graph database you query faster"
and "a live semantic index of the program."

## How it works

`claim!` fires hooks registered by the matview system:

- **Insertion path**: each new claim produces EDB delta tuples
  (triple, claim, current-triple, current-claim). Delta propagates
  through rules: EDB→IDB, then IDB→IDB recursively to fixpoint.
  Views stay current without re-running the full semi-naive engine.

- **Supersession path**: invalidates affected views. Next query
  recomputes and re-caches. (Provenance-tracked deletion would
  make this O(delta) too — that's next.)

`run-query` transparently checks the cache. Valid cache → hash
lookup. Invalid cache → full fixpoint + re-cache. No matview
system → original behavior. Existing code unaffected unless
`materialize!` is called.

## What's still weak

Supersession (rename, update, retract) nukes the entire view cache.
The first query after a rename at N=200 still pays ~38ms for a full
fixpoint recompute. Provenance-tracked deletion — where each derived
tuple records which claim IDs supported it — would make supersession
O(delta) instead of O(full-fixpoint).

## The framing going forward

CNF should not be framed as "a graph database you query faster."

CNF is a **live semantic index of the program.** The system does not
wait until the agent asks "what depends on this?" — it already knows,
because `claim!` propagated the delta while the graph was being built.

The next step is to prove this matters for agent wall-time, not just
microbenchmarks. See `docs/experiments/README.md`.

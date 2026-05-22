# 008 — Interface redesign: the bottleneck shifted

**Date:** 2026-05-20

## What the E5 arena revealed

Two real Claude agents did the same refactoring task on a 20-function
program. Text agent: 8 tool calls, 82s. CNF agent: 42 tool calls, 191s.
Both correct. Text won decisively.

But the matview queries were near-instant — sub-millisecond. The engine
optimizations from entries 001–007 worked. Per-operation, CNF is
100–1000x faster. So why did the CNF agent lose?

## Where 42 calls went

Breaking down the CNF agent's tool calls:

- ~1: reset
- ~1: parse
- ~10–15: **schema discovery** (inspecting entities, figuring out that
  predicate "34" means "body", "37" means "calls", "7" means "left")
- ~10–12: defining 6 rules (each = define + verify)
- ~5: queries and renders
- ~5: rename + verify + final render

Each MCP tool call takes 3–5 seconds of LLM inference time. At 42
calls, that's ~120–200s of pure thinking. The actual claim graph
compute was a rounding error.

The text agent ran `grep` once and had the full picture. No schema
to discover. No rules to define. No IDs to track.

## The bottleneck shifted

Entries 001–007 optimized the engine:

```
E1: 0.04x → 0.33x  (provenance-tracked deletion)
E3: 0.53x → 0.91x  (incremental rule addition)
E4: 0.1x  → 3.26x  (incremental supersession)
```

The engine is fast. But for real agents, the bottleneck is no longer
compute time — it's **tool call count**. Each round-trip costs seconds
of LLM inference. The number of round-trips dominates wall time.

The claim graph is a database, but the agent was forced to use it
through a row-level API: one inspect per entity, one define per rule,
one query per question. Text tools compose (pipes, `&&`). MCP tools
don't — each is an isolated round-trip.

## Three interface fixes

### 1. Parse returns the schema

`parse_program` now returns predicate names, IDs, and built-in
derived relations. The agent knows the vocabulary immediately:

```
Schema (predicate name -> ID):
  op: 4, left: 7, right: 10, name: 22
  body: 34, calls: 37, has-param: 28, position: 37
Built-in: fn-depends-on, contains-call
```

Eliminates ~10–15 schema discovery calls.

### 2. Named symbol resolution in queries

Bare symbols in query/rule S-expressions resolve to named entities:

```
;; Before — agent must discover and track numeric IDs:
(current-triple (? fn) "34" (? body))

;; After — human-readable, no ID lookup needed:
(current-triple (? fn) body (? body))
```

Resolution happens at parse time via `resolve-symbol`. Falls back to
raw string if no named entity matches.

### 3. Batch tool

Multiple operations in a single tool call:

```json
{"tool": "batch", "arguments": {"operations": [
  {"tool": "define_rule", "arguments": {"head": "...", "body": "..."}},
  {"tool": "define_rule", "arguments": {"head": "...", "body": "..."}},
  {"tool": "query", "arguments": {"body": "..."}}
]}}
```

Six operations, one round-trip. Like SQL vs row-level API.

## Predicted impact

The E5 CNF agent's workflow with the new interface:

1. `parse_program` → schema + function IDs (1 call)
2. `render` distance and dot → confirm duplication (1 call)
3. `batch` → define rules + query dependents (1 call)
4. `rename` dot → dot-product (1 call)
5. `batch` → define uses-dot-product, query, render (1 call)

**5 calls.** Down from 42. Competitive with text's 8.

## Why this matters

The project optimized the wrong layer for 7 entries. The engine went
from 0.04x to 3.26x — a two-order-of-magnitude improvement. But
that improvement is invisible to real agents because it's measured in
microseconds, and the real cost is measured in seconds-per-tool-call.

The interface redesign targets the actual bottleneck. It won't change
any benchmark numbers (those measure compute). It changes the real
agent experience: fewer calls, faster sessions, the claim graph's
power exposed without the round-trip tax.

## The compounding thesis

The interface fixes set up the real test: a multi-round arena (E6).
Five sequential tasks, same program. The CNF agent's rules from
task 1 persist through tasks 2–5. Each follow-up task is 1–2 calls
(query existing matview). The text agent re-greps from scratch.

This is where the thesis lives or dies — not in microsecond
benchmarks, but in whether accumulated structural understanding
reduces the total cost of a sustained agent session.

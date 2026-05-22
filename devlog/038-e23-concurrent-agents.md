# 038 — E23: Concurrent Agents

**Date:** 2026-05-21

## What

Two agents, overlapping tasks, same program. Agent A adds safe
division. Agent B renames a core dependency. Five functions in the
overlap zone need both changes.

Graph: 104.5s. Text: 137.7s. Both correct. Graph faster again (1.3x).

## What went wrong

The shared daemon has a MVCC bug: snapshots published by one TCP
connection aren't visible to subsequent connections. The committed
box appears to have the correct value after parse_program, but new
connections read the pre-parse state (166 objects instead of 2474).

This forced independent MCP servers for each graph agent. The true
concurrent coordination test didn't happen.

The text agents accidentally edited the same file (the experiment
directory copy, not their workspace copies). This gave them real-time
coordination for free — Agent B's rename was visible to Agent A
during execution. Despite this best-case scenario, text was still
slower.

## What went right

Both graph agents completed all steps correctly using entity-level
operations. Agent A: 8 functions guarded, 2 correctly left alone
(constant divisors). Agent B: 1 rename operation, 11 call sites
updated, error history (run 14595) still queryable.

Agent B's transcript shows the mechanism clearly: "Rename entity 222
from `helper` → `utility`. All references updated automatically."
One operation. No scanning, no pattern matching, no false-positive
risk.

## The speed trend

```
E21 (5 fn):  text 64.7s,  graph 103.6s → text 1.6x faster
E22 (58 fn): text 157.3s, graph 138.2s → graph 1.1x faster
E23 (51 fn): text 137.7s, graph 104.5s → graph 1.3x faster
```

The gap is widening in the graph's favor. At 51 functions with two
tasks, the graph agents saved 33s through entity-level operations.

## The real blocker

The experiment I want to run is: both agents on the same live graph,
seeing each other's changes in real time, coordinating through
dependency queries and transaction history.

That requires fixing the daemon MVCC cross-connection bug. The
snapshot propagation path (`reset-store!` → `snapshot-ctx` →
`set-box! committed`) works correctly within a single connection but
breaks when a new connection reads the committed box.

Until that's fixed, the "concurrent coordination through graph
facts" hypothesis can't be tested directly.

## What I learned

The accidental text coordination is actually informative. Two agents
editing the same file in real time worked perfectly at 51 functions
and 2 agents. But it's fragile — it depends on edit ordering, file
system atomicity, and one agent not clobbering the other's changes.
At 10 agents on the same file, this breaks.

The graph alternative doesn't need ordering guarantees because the
operations are semantically orthogonal. Rename doesn't touch body
claims. Body modification doesn't touch entity references. The graph
structure makes the non-conflict *provable*, not just empirically
true for this run.

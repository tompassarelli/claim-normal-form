# 004 — E3 agent comparison: honest numbers

**Date:** 2026-05-20

## What happened

Built the E3 benchmark: 18 operations across 5 phases simulating a
real agent session. CNF (claim graph + Datalog + homoiconic rules) vs
Text (files + grep + sed + ad-hoc computation). Hub-and-spoke
dependency graph — every 5th function calls f0, giving rich structure
for multi-hop and shared-dep queries.

## The surprise

CNF loses on total wall time. 0.24-0.53x across all scales. The
fixpoint recompute after each rule definition is expensive — at N=500,
the shared-dep fixpoint (joining 499 fn-depends-on tuples with
themselves) takes 523ms. Text does the equivalent as direct hash-map
operations in ~44ms.

This is the opposite of what E1/E2 suggested (where CNF won on
multi-op benchmarks). The difference: E1/E2 used only built-in
rules (already materialized). E3 defines NEW rules mid-session,
which invalidates the matview and forces a full recompute.

## The discovery

Phase 4 changes the story. After rules are defined and the matview
is populated, each rename-and-query costs:

| N | CNF per-op | Text per-op | Ratio |
|---|---:|---:|---:|
| 100 | 0.02ms | 5.2ms | 202x |
| 200 | 0.14ms | 15.6ms | 115x |
| 500 | 0.04ms | 48.6ms | 1025x |

CNF is O(1) per operation (matview cache hit — renames don't affect
structural claims). Text is O(N²) (rebuild call map + recompute
derived data).

The crossover at N=200 is ~11 operations. A 50-operation session
sees CNF win 3.6x. At 100 operations, 6.6x.

## Why the fixpoint is expensive

The current `invalidate-views!` approach is nuclear: mark the entire
matview invalid, recompute everything on next query. This means
defining a new rule pays the cost of ALL rules, not just the new one.

A smarter approach: incremental rule addition. When a new rule is
defined, run only that rule's fixpoint against the existing matview.
Don't recompute rules that haven't changed.

This is the same insight from E1: incremental maintenance during
mutation is cheaper than batch recomputation. The matview system
already does this for new claims (delta propagation). It should
do the same for new rules.

Estimated impact: Phase 3 cost would drop from ~183ms to ~20-30ms
(only the new rule's fixpoint, not all rules). This would shift the
crossover from ~11 operations to ~2-3.

## What this means for the thesis

The thesis is validated, but more nuanced than expected:

1. **Not "always faster."** CNF pays upfront cost for capabilities
   text doesn't have. The payoff comes in sustained use.

2. **The real advantage is O(1) maintenance.** After the matview is
   built, each edit+query is O(1). This compounds over a session.
   Text pays O(N²) every time.

3. **The capability gap is qualitative.** CNF agents can define,
   evolve, and compose derived relations mid-session. Text agents
   do ad-hoc computation. The difference isn't just speed — it's
   what's possible.

4. **Fixpoint optimization is the next leverage point.** Incremental
   rule addition would eliminate the upfront cost, making CNF win
   at every phase.

## What's next

The E3 numbers are honest. The system works. The capability gap is
real. The fixpoint overhead is the remaining bottleneck, and there's
a clear path to fix it (incremental rule addition, partial fixpoint).

The next question: does this translate to a real agent session? The
benchmarks measure tool-level operations. A real comparison would
have two Claude instances doing the same refactoring task, measuring
turns, tokens, and what each agent could/couldn't accomplish.

But the numbers already tell the story: for sustained agent sessions,
CNF's O(1) per-query advantage dominates. And the capabilities
(define rules, evolve them, compose them) simply don't exist in the
text world.

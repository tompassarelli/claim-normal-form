# 006 — Live agent session: workflow comparison

**Date:** 2026-05-20

## What happened

Built E4: a side-by-side transcript of two agents doing the same
7-step refactoring task. Not a timing benchmark — a workflow
comparison. Both agents compute identical results at each step
(verified by count assertions). The difference is *how* they work.

Task: discover hub functions in a 100-function codebase, define
"indirect-dep" and "coupled" concepts, rename the hub, verify
coupling holds after rename, evolve the coupling definition from
2-hop to 3-hop, then do 5 more renames with re-verification.

## The surprise (again)

Text wins total wall time: 27ms vs 262ms. CNF is 0.1x.

The single dominant cost: `supersede-rule!` in Step 6 (256ms).
Evolving one rule triggers a full fixpoint recompute of everything.
Text rewrites an ad-hoc computation in 0.03ms.

Steps 2-3 (initial rule definition) also favor text: a list
comprehension for 2-hop is ~0.01ms; incremental materialization is
0.82-5.27ms. The overhead buys persistence and composability, but
the one-shot cost is real.

## The real story

Steps 1, 4, 5, 7 — everything after rules are defined:

| Step | CNF | Text | Ratio |
|------|---:|---:|---:|
| Discover hubs | 0.02ms | 2.25ms | 105x |
| Rename | 0.02ms | 1.64ms | 95x |
| Verify | 0.03ms | 2.62ms | 79x |
| Sustained (per-op) | 0.05ms | 4.14ms | 80x |

The sustained-use advantage is 80x per-op. At N=200, E3 showed
256x. At N=500, 635x. Text's cost is O(N²) per operation; CNF's
is O(1).

Crossover at N=100: ~58 operations. Scales down with N: ~12 at
N=200, ~6 at N=500 (per E3 data).

## The qualitative gap

This is what the benchmark can't capture:

The CNF agent built three rules that compose. `coupled` references
`indirect-dep`. When `coupled` was superseded with a 3-hop version,
the old definition was preserved as superseded claims. The agent
could inspect rule entities, query their metadata, or build new
rules on top of existing ones.

The text agent wrote five independent computations. Each was
correct, each was fast, and each was lost the moment the next
rename required a rebuild. When the coupling definition evolved,
the old code was replaced. No history, no composition, no way for
a future query to build on past work.

In a 5-minute session, this doesn't matter. In a 50-minute session,
the CNF agent's accumulated semantic index is an asset. The text
agent starts from scratch on operation 51 just like it did on
operation 1.

## Honest assessment

The numbers don't prove "CNF is better." They prove:

1. **CNF pays upfront for capabilities that compound.** Rules,
   materialization, supersession — each costs more than the ad-hoc
   alternative. The payoff is O(1) sustained use.

2. **The supersede bottleneck is real and fixable.** 256ms for rule
   evolution is too expensive. Rule-level provenance would reduce
   this to incremental retraction + re-derivation. Same approach
   that fixed claim-level deletion in E1.

3. **The qualitative gap is the real argument.** An agent that can
   define, compose, evolve, and inspect structural concepts mid-session
   works differently from one that can't. Not faster — differently.

4. **Crossover depends on session length and codebase size.** Short
   sessions on small codebases: text wins. Long sessions on real
   codebases: CNF dominates.

# E10: The Shared Substrate

## Thesis under test

Accumulated structural knowledge persists and composes across agent
sessions. Text agents start from scratch each session; CNF agents
inherit rules, matviews, and derived relations from prior sessions.

E5–E9 tested single-session efficiency. The text agent always wins
by front-loading analysis into one Python script. E10 tests the one
thing text fundamentally cannot do: **composable cross-session state**.

## What E10 changes

Two sessions, same 50-function codebase (e9-program.txt).

**Session 1:** Both agents parse the program and build understanding:
- Structural analysis (layers, roots, leaves, hubs)
- Define transitive dependency rule
- Define shared-dependency rule (pairs sharing 2+ direct deps)
- CNF agent: checkpoints the claim graph to disk
- Text agent: saves analysis results to a file

**Session 2:** Both agents start fresh (new LLM context, no memory
of Session 1). Five questions that compose Session 1's analysis:

1. List all rules from Session 1 and what they compute
2. Transitive dependents of normalize (requires trans-dep rule)
3. Rename normalize → norm, show which functions updated
4. After rename: shared-dep pairs involving norm (auto-updated?)
5. Define a new "impact" rule composing trans-dep + shared-dep,
   find functions with highest combined impact

## The asymmetry

**CNF Session 2:**
- `restore` → 1 call, full graph with rules + matviews
- `list_rules` → 1 call, sees Session 1's rules
- `query trans-dep` → 1 call, hits existing matview
- `batch(rename + query)` → 1 call, matview auto-updates
- `query shared-dep` → 1 call, matview auto-updated through rename
- `define_rule + query` → 2 calls, composes existing derived relations
- **Predicted: ~7 calls**

**Text Session 2:**
- Read e9-program.txt → 1 call
- Read saved analysis (if it exists) → 1 call
- Python: recompute transitive deps → 1 call (or parse saved results)
- sed: rename → 1 call
- Python: recompute shared deps post-rename → 1 call
- Python: compute impact metric → 1 call
- **Predicted: ~5-6 calls**

## What E10 does NOT test

- **Truly concurrent multi-agent.** Both agents run sequentially, not
  simultaneously. The daemon supports concurrent connections but the
  experiment uses checkpoint/restore.
- **External mutations.** The only mutation is agent-initiated rename.
- **Scale beyond 50 functions.** Still a toy program.

## Honest prediction

**Call count:** Text probably wins again (~5-6 vs ~7). A Python script
can recompute everything from the file in one call. Checkpoint/restore
adds 1 call that text doesn't need.

**The real finding:** CNF demonstrates composable cross-session
knowledge transfer. The CNF agent in Session 2:
1. Inspects rules it didn't define
2. Queries matviews it didn't build
3. Defines new rules that compose prior derived relations
4. Gets auto-updated results through mutations

The text agent re-implements everything from scratch. It might take
fewer calls, but each call is a re-derivation, not a composition.

## Expected answers

Same as E9:
- 12 leaves, 10 roots, normalize=biggest hub (7 callers)
- Transitive deps of normalize: 16 functions
- Rename propagates to 7 callers
- Shared-dep pairs: 6 (pre-rename), should shift post-rename
- Impact metric: defined compositionally from trans-dep + shared-dep

# E9: Accumulated Knowledge at Scale

## Thesis under test

CNF agents accumulate structural knowledge (rules, matviews) that
reduces per-task cost across a multi-task session. Text agents use
Python scripts that are individually cheap but don't compose.

E5–E8 couldn't test this properly because: (1) all tasks were given
upfront, enabling front-loading into one script, (2) the program
was 20 functions — too small for re-analysis to cost anything.

## What E9 changes

- **50 functions** (2.5x E5–E8) with 81 dependency edges
- **Tasks that build on each other** — task 4 renames a function,
  tasks 5+ must work with the renamed codebase
- **7 tasks** mixing analysis, rule definition, mutation, and
  composition

## What E9 does NOT test

- **External mutations.** The engine doesn't support incremental
  parse — `parse_program` creates new entities, so re-parsing after
  external changes would require reset (losing all rules). The only
  mutation is agent-initiated rename.
- **Sequential revelation.** The Agent tool can't send tasks one at
  a time. Both agents see all 7 tasks upfront. Tasks are designed
  to build on each other, making natural front-loading harder.
- **Scale beyond 50 functions.** Still a toy program.

These are honest limitations, not deferrals.

## Program

50 functions across 4 layers in a data processing pipeline DSL.

| Layer | Count | Dependencies |
|-------|------:|-------------|
| L1 — Primitives | 12 | None (leaves) |
| L2 — Transforms | 14 | 2-3 L1 functions each |
| L3 — Combinators | 14 | 2-3 L2 functions each |
| L4 — Pipelines | 10 | 2-3 L3/L4 functions each |

Properties:
- 81 dependency edges
- `normalize` is the biggest hub (7 direct callers)
- `to-int` has 5 callers, `clamp` has 4
- 2 duplicate pairs: lower=upper, validate=negate
- 2 dead functions: negate (L1, never called), group-pair (L3, never called)
- 6 shared-dependency pairs (functions sharing 2+ direct deps)
- Max dependency depth: 4
- 5 functions have 3 deps (nested calls) for graph variety
- 1 cross-layer edge (pipeline → output, L4→L4)

Source: `experiments/e9-program.txt`

## Tasks

1. **Structure Discovery:** Layers, leaves, roots, biggest hub
2. **Duplicate Detection:** Identical implementations, their callers
3. **Transitive Dependencies:** Define rule, query for normalize
4. **Rename + Verify:** normalize → norm, show propagation
5. **Post-Rename Validation:** Transitive deps of norm match task 3
6. **Shared Dependencies:** Pairs sharing 2+ direct deps
7. **Final Report:** Edges, depth, hubs, dead code, duplicates

## Expected answers

- Leaves: 12 (all L1 functions)
- Roots: 9 (negate, group-pair, enrich, output, archive, replicate,
  migrate, audit, reconcile, pipeline) — wait, that's 10. [pipeline,
  enrich, archive, replicate, migrate, audit, reconcile = 7 L4 roots
  + negate (L1) + group-pair (L3) = 9 roots. output is called by
  pipeline so it's NOT a root.]
- Hub: normalize (7 callers)
- Duplicates: lower/upper `(* x (- x y))`, validate/negate `(- (* x x) (* y y))`
- Transitive deps of normalize: 16 functions
- Shared-dep pairs (2+ shared): 6 pairs
- Dead code: negate, group-pair
- Depth: 4
- Total edges: 81

## Predictions

**CNF agent (optimistic):** 7-10 MCP calls. Batch combines setup +
queries. Rules persist across tasks. Rename auto-updates matview.
Post-rename query hits existing rule (0 extra work).

**CNF agent (realistic):** 12-18 MCP calls. Exploration, verification
renders, ID lookups, and mistakes add calls.

**Text agent (optimistic):** 3-5 calls. One comprehensive Python
script handles tasks 1-3, 6-7. Sed for rename. Verification read.

**Text agent (realistic):** 6-10 calls. Separate scripts per task,
re-reading file after rename, verification steps.

**Honest prediction:** Text wins on raw call count. A Python script
is a universal batch operation — one Bash call can do unlimited
computation. The CNF agent's batch tool is powerful but each
operation is a defined MCP tool, not arbitrary code.

The interesting finding will be in the PATTERN: does CNF's per-task
cost decrease while text stays constant? And does the rename in
task 4 cause the text agent extra work in task 5?

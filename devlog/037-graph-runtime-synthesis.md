# 037 — Graph Runtime Synthesis: E20–E22

**Date:** 2026-05-21

## The arc

Three experiments, one question: what happens when the graph *is* the
program?

**E20** proved the loop works. Parse, evaluate, query dependencies,
rename, re-evaluate, add a function, break it, diagnose the error as
graph data, fix it, re-evaluate. All against one claim graph. Scripted,
not agent-driven.

**E21** put it in an agent's hands. Two real Sonnet agents, same task,
different tools. Text agent: files + shell. Graph agent: MCP tools.
Both completed all 10 steps. Text was faster (64.7s vs 103.6s). The
graph's structural advantages — semantic rename, persistent error
history — didn't manifest at 5 functions.

**E22** scaled the task until structure mattered. 58 functions, 5 trap
function names, 4 parameter shadows, 9 true call sites. Both agents
scored perfectly. The graph was faster for the first time (138.2s vs
157.3s).

## What actually matters

The speed crossover is nice. It is not the point.

The point is the difference in mechanism:

- The text agent had to reason correctly about which occurrences of
  "helper" were the target function, which were different functions,
  and which were parameters. It succeeded — through careful analysis,
  planned edits, and verification.

- The graph agent called `rename` on an entity. Call sites updated
  because they reference the entity, not a string. Other entities
  were untouched because they are other entities. There was nothing
  to reason about.

Speed bounces around with model versions, prompt phrasing, and MCP
overhead. Correct-by-construction does not bounce. It is a property
of the substrate.

## Error-as-data

Both E21 and E22 included a break/fix cycle: modify a function to
cause division by zero, observe the error, restore the function. In
both experiments:

- The graph agent queried the error as a persistent eval-run entity
  with status, reason, function ID, and fuel data — after the fix,
  after the rename, after additional evaluations.

- The text agent reported what it observed from conversation context.
  The eval-helper process starts fresh each invocation. There is no
  history to query.

This is not a quality gap. It is a capability gap. The text agent has
no mechanism for querying past runtime failures. Not a worse mechanism —
no mechanism.

## The bug that proved the design

E22 surfaced a real bug in `resolve-fn-name`: parameter entities and
function entities can share the same name. At 5 functions (E20, E21),
this never triggered. At 58 functions with deliberate name collisions,
it broke parsing.

The fix — filter by `position-pred` (parameters have position, functions
don't) — is itself a structural operation. The kind of disambiguation
that requires entity-level identity, not string matching.

The ambiguity task didn't just test the agents. It tested the substrate.

## Where this leaves us

The graph runtime proves three things:

1. **Agents use structural tools when they have them.** The graph agent
   called `rename`, `query`, and `inspect` for error history without
   being told to. The tools were there and it used them.

2. **Entity-level operations are correct by construction.** Rename
   cannot produce false positives or miss call sites. This is a
   provable property, not an empirical observation that might change
   with the next model version.

3. **Error-as-data is a clean structural gap.** Runtime outcomes as
   queryable claims give agents a persistent, structured audit trail
   that file-based tools cannot replicate.

## What's missing

The graph runtime experiments are single-agent. The multi-agent
coordination experiments (F2–F11) used Python/Beagle source, not the
graph-native runtime. The two arcs have never touched.

The next question: when two agents modify the same claim-graph program
concurrently, does the shared substrate reduce coordination failures?

That combines everything: semantic identity, dependency queries,
transaction history, eval-runs, and MVCC — against a real concurrent
workload where the substrate is the coordination mechanism.

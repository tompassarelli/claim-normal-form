# E21: Graph-Native Agent Race

**Date:** 2026-05-21

## Question

When two agents get the same task, does the graph-native agent
outperform the text-native agent?

## Setup

5-function payroll program with cross-dependencies and a
division-by-zero hazard:

```
base-rate(hours, rate)            = hours * rate
overtime(hours, rate)             = base-rate(hours, rate) * 2
total-pay(base, extra)            = base + extra
split-pay(total, parts)           = total / parts        ← div by zero when parts=0
after-split(total, parts, deduct) = split-pay(total, parts) - deduct
```

Dependencies: overtime → base-rate, after-split → split-pay.

10-step task: parse → verify baseline → reproduce bug → add safe-div →
wire it in → verify fix → query dependencies → rename → verify post-rename →
query error history.

**Arm A (text):** source file + shell + `eval-helper.rkt` (parse, eval,
deps, render as shell commands). Find-and-replace for rename. No
persistent state between eval-helper invocations.

**Arm B (graph):** MCP tools (`parse_program`, `evaluate`, `query`,
`add_function`, `modify_function`, `rename`, `render`, `inspect`).
All state persists in the claim graph across tool calls.

**Model:** Claude Sonnet, same version for both.
**Timeout:** 300s per agent.

Run: `python experiments/e21-graph-race/runner.py`

## Results

Both agents completed all 10 steps.

|                      | Text    | Graph   |
|----------------------|---------|---------|
| Wall time            | 64.7s   | 103.6s  |
| Steps completed      | 10/10   | 10/10   |
| Step 10 (error hist) | N/A     | PASS    |
| Step 8 (rename)      | manual  | semantic|

### Where they're equal (steps 1-7, 9)

Both agents parsed the program, reproduced the bug, added safe-div,
wired it into split-pay, verified the fix, queried dependencies, and
evaluated after rename. Identical results, identical correctness.

The text agent was faster on every step. Simpler tool overhead: one
shell invocation vs JSON-RPC round-trip through an MCP server.

### Where the graph wins

**Step 10: Error history.** The graph agent queried run 1240 (the
division-by-zero crash from step 3) after fixing the bug, renaming
the function, and running new evaluations. The run entity was still
in the graph with status, reason, function ID, and fuel data.

The text agent correctly identified this as architecturally
impossible: "cross-invocation history is an architectural limitation
of the in-memory store." Each `eval-helper.rkt` invocation starts
fresh — there is no persistent state to query.

**Step 8: Rename.** Both produced the same output, but the mechanisms
differ. The text agent did find-and-replace in `program.cnf`. The
graph agent called `rename` once — all call sites updated because
names are projections of entity references.

At 5 functions, both work. At 500 functions with name collisions
(e.g., a variable named `safe-div` in a string literal), the text
approach produces false positives. The graph approach is correct by
construction.

### Timing breakdown

The graph agent took 1.6x longer (103.6s vs 64.7s). The overhead is:

1. MCP server startup (Racket process launch + initialization)
2. JSON-RPC serialization per tool call
3. More tool calls needed (reset + parse + individual tool calls vs
   single shell commands)

In the first run with broken `add_function`/`modify_function` tools
(see below), the graph agent took 237.6s — 3.7x slower — because it
had to work around missing tools using raw `parse_program` and
`claim` operations.

### Bug found during race

The first run revealed that `add_function` and `modify_function` in
`server.rkt` didn't route to the cnf toy language — only Python and
Beagle. The graph agent worked around this using `parse_program`
incrementally and direct `claim` assertions. After fixing the server
routing, the graph agent dropped from 237.6s to 103.6s.

## Honest assessment

**The text agent wins on speed.** For a 5-function program, file
editing and shell commands are faster and simpler than MCP tools.

**The graph agent wins on capabilities it didn't need.** Error
history, semantic rename, and incremental mutation are structural
advantages that don't manifest at toy scale. The graph agent's
transcript is more precise (entity IDs, run IDs, structured claims)
but precision doesn't matter when the program fits in one screenful.

**The graph advantages compound with scale:**

- Dependency queries become transitive (grep finds direct calls, not
  chains)
- Rename propagation becomes semantic (find-and-replace fails with
  name collisions)
- Error history becomes a queryable audit trail (not ephemeral stderr)
- Incremental mutation becomes essential (re-parsing 500 functions per
  edit is expensive)

This experiment proves the tools work end-to-end in a real agent's
hands. It does not prove they're faster or better at this scale.

## What this demonstrates

1. The full agent loop works: parse → query → evaluate → add → modify
   → rename → query error history. No scripted steps.
2. Agents USE the graph tools when they have them — the graph agent
   naturally called `query`, `rename`, and `inspect` for error history.
3. Error-as-data is real: run 1240 persisted through program mutations
   and was queryable at step 10.
4. MCP tool overhead is significant at toy scale (~1.6x slowdown).

## What this does NOT demonstrate

- **Scale advantage**: 5 functions, not 500. The graph advantages
  (transitive deps, semantic rename, incremental mutation) compound
  with scale; this demo doesn't prove that.
- **Multi-agent coordination**: single agent per arm. The MVCC
  infrastructure exists but isn't tested.
- **Graph-impossible tasks**: both agents succeeded. A task where the
  text agent structurally CAN'T succeed (e.g., transitive dependency
  chain through 10 functions with name collisions) would show a
  sharper delta.

## What's next

The race proves the tools work. The next test should prove they're
needed: a task at scale where text tools fail and graph tools don't.

Candidates:
- 50-function program with deep dependency chains and name collisions
- Concurrent modification where two agents edit the same function
- Provenance query: "which runs used this version of function X?"

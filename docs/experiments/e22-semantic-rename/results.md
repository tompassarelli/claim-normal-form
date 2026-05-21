# E22: Semantic Rename at Scale

**Date:** 2026-05-21

## Question

When a rename target shares its name with other function names and
parameter bindings, does the graph agent outperform the text agent?

## Setup

58-function program with deliberate name-ambiguity traps:

- **Target function:** `helper` — `(defn helper [x y] (+ x y))`
- **5 trap function names:** `helper-rate`, `tax-helper`, `old-helper`,
  `rate-helper`, `helper-sum` — different functions, NOT the target
- **4 parameter traps:** `process-a` through `process-d` each have a
  parameter named `helper` — NOT a function call
- **9 true call sites:** `compute-a` through `compute-f`, `mix-a`,
  `mix-b`, `mix-c` — these call the target function
- **Transitive callers:** `chain-*`, `deep-*`, `final-*`, `summary-*`
  call the direct callers
- **Unrelated functions:** `pure-a` through `pure-j`, `base-calc`,
  `margin`, `discount`, `markup` — no connection to `helper`

9-step task:

1. Parse (confirm 58 functions)
2. Baseline (evaluate helper, compute-a, mix-a, process-a, helper-rate)
3. Break helper (`/` instead of `+`), observe error on compute-a(3,0)
4. Restore helper (`+`), verify compute-a(3,4) = 14
5. Rename `helper` → `safe-helper` (9 call sites, 0 false positives)
6. Verify rename (8 sub-checks: definition, call sites, trap names,
   parameters, evaluations)
7. Query dependencies of safe-helper
8. Query error history from step 3
9. Render full program, confirm coherence

**Arm A (text):** source file + shell + `eval-helper.rkt`. Rename by
editing `program.cnf`. No cross-invocation state.

**Arm B (graph):** MCP tools against the CNF claim graph. Rename by
entity operation. All state persists.

**Model:** Claude Sonnet, same version for both.
**Timeout:** 300s per agent.

Run: `python experiments/e22-semantic-rename/runner.py`

## Results

Both agents completed all 9 steps correctly.

|                        | Text    | Graph   |
|------------------------|---------|---------|
| Wall time              | 157.3s  | 138.2s  |
| Steps completed        | 9/9     | 9/9     |
| Call sites updated     | 9/9     | 9/9     |
| False-positive renames | 0       | 0       |
| Trap names preserved   | 5/5     | 5/5     |
| Params preserved       | 4/4     | 4/4     |
| Error history          | No      | Yes     |

**The graph agent was faster for the first time: 138.2s vs 157.3s.**

### Rename correctness: both perfect

The text agent did not use naive find-and-replace. It identified the
ambiguity, carefully renamed only the target function and its 9 call
sites, and left all trap names and parameter bindings untouched. It
spent more time and more tool calls to achieve this care — reading
the file, planning the edits, verifying afterward.

The graph agent called `rename` once on the entity. All 9 call sites
updated automatically because they reference the entity, not a string.
Trap names and parameters are different entities — they were never in
scope for the operation.

Both got the same result. The mechanism is fundamentally different.

### Why the graph agent was faster

At 58 functions, the text agent's task grew beyond "just edit the file."
The agent needed to:

1. Read and understand the full 195-line program
2. Identify which occurrences of "helper" are the target
3. Plan careful edits (avoiding trap names and parameters)
4. Execute the edits
5. Verify the result

The graph agent skipped steps 1-4. `rename` on an entity is one tool
call. The structural analysis that the text agent had to perform
manually is built into the substrate.

This is the first experiment where the graph's structural advantage
outweighed its MCP overhead.

### Error history

**Graph:** The division-by-zero from step 3 persisted as eval-run
entity 25674 with `status: "error"`, `reason: "/: division by zero"`.
Queryable at step 8 after the fix, the rename, and additional evaluations.

**Text:** Not retained. Each `eval-helper.rkt` invocation starts fresh.
The text agent reported what it observed during step 3 from its
conversation context — not from a queryable data structure.

### Dependencies

**Graph:** 9 direct callers via Datalog `fn-depends-on` query; 15
transitive callers (24 total).

**Text:** Listed callers by reading the source file. At 58 functions,
this required scanning the file; at 500 functions, this would require
multi-file grep with the same false-positive risk as rename.

## Verification script notes

The results.json shows two false negatives from verification bugs:

1. **`callsite_compute-d: false` (text)** — The original regex used
   `.*?\)` which stops at the first `)`, missing nested expressions
   like `(if (= b 0) 0 (/ (safe-helper a b) 2))`. Fixed to
   paren-depth counting. Manual inspection confirms `safe-helper` is
   correct in compute-d.

2. **`baseline_7: false` (graph)** — The transcript checker looked for
   `"= 7"` but the transcript says `"helper=7"` (no spaces). Both
   transcripts confirm helper(3,4) = 7.

Both agents scored perfectly on all checks.

## Bug found during setup

**resolve-fn-name parameter/function ambiguity.** When parameter
entities share names with function entities (e.g., `process-a [helper x]`),
`resolve-fn-name('helper)` could return the parameter entity instead
of the function entity. This caused "unbound variable: helper" for
functions parsed after the parameter trap functions.

First fix attempt: filter by `body-pred` (functions have bodies,
parameters don't). Failed because during parsing, self-recursive
functions don't have `body-pred` yet.

Final fix: filter OUT entities that have `position-pred` claims.
Parameters have position predicates; functions don't. This is sound
because position is an intrinsic property of parameters, set at
parse time.

This bug only surfaced at 58-function scale with name collisions —
it was invisible in E20 (5 functions) and E21 (5 functions, no name
traps). The ambiguity task design surfaced a real bug.

## Honest assessment

**Both agents got the rename right.** At 58 functions, a careful text
agent can handle name ambiguity. The text agent demonstrated
impressive structural understanding — it didn't fall into any traps.

**The graph agent's advantage is not that it got a better result.** The
advantage is that it couldn't get a worse one. The graph rename is
correct by construction: one operation on an entity, all references
update, other entities are untouched. There is no careful-editing step
that could go wrong.

**The text agent's correctness is fragile.** It depends on the agent
being careful, understanding the program structure, and not making
mistakes under time pressure. At 500 functions across multiple files,
the probability of a missed call site or a false-positive rename
increases. The graph agent's probability stays at zero.

**Speed crossed over.** The graph was faster for the first time. The
crossover happened because rename complexity scales differently:

- **Text:** O(N) — must scan every function, decide per-occurrence
- **Graph:** O(1) — one entity operation regardless of program size

At 5 functions (E21), text overhead is tiny and graph MCP overhead
dominates. At 58 functions, text overhead grows while graph overhead
stays constant.

**Error history is a structural capability gap.** This was true in E21
and remains true at scale. The text agent has no mechanism to query
past runtime failures — it can only report what it remembers from
conversation context.

## What this demonstrates

1. **The graph rename is correct by construction.** Entity-level rename
   cannot produce false positives or miss call sites. This is a
   provable property, not an empirical observation.

2. **Scale flipped the speed result.** E21: text 64.7s, graph 103.6s
   (text 1.6x faster). E22: text 157.3s, graph 138.2s (graph 1.1x
   faster). The trend favors the graph as program size grows.

3. **Name ambiguity is a real problem, not a contrived test.** The
   resolve-fn-name bug proves this — even the implementation had
   trouble with name collisions at scale.

4. **Error-as-data compounds.** At 9 steps with break/fix/rename/eval,
   the graph accumulated a queryable history of every evaluation. The
   text agent's history died with each process invocation.

## What this does NOT demonstrate

- **Text agent failure.** Both agents got perfect scores. A stronger
  test would use a program where the text agent actually makes a
  false-positive rename.

- **Multi-file scale.** 58 functions in one file. Real codebases spread
  functions across files — the text agent's scan cost would be higher.

- **Concurrent rename.** Two agents renaming different functions
  simultaneously — the MVCC infrastructure exists but isn't tested here.

## What's next

E22 proves the graph is faster and correct-by-construction at moderate
scale. The next step is either:

- **Totality classification** — per-node queryable property: provably
  total, fuel-bounded, effectful, unknown. A property no normal
  language has.

- **Multi-agent structural task** — concurrent modifications to the
  same program via the claim graph, where text agents would need merge
  conflict resolution.

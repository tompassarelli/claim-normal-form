# 045 — E27/E28: Graph-native ClaimDesk

**2026-05-22**

## What changed

The domain model is no longer a description of code. It IS the program.

E24/E25 used the claim graph as a semantic index — agents wrote Python,
the graph held parsed metadata, tools checked generated output against
graph facts. That works (4% failure with repair), but it puts CNF in
the same lane as Sourcegraph, Cursor, and tree-sitter. Useful tooling,
not the thesis.

E27 inverts the relationship. The claim graph contains:
- 6 statuses with group membership (active/terminal)
- 9 transition rules as entity links
- 2 roles, 3 permission rules, 2 effect declarations
- Ticket entities with status links
- Users with role links

All of this is claims. Not parsed from Python. Not a mirror. The source.

## The vertical slice (E27)

The full pipeline runs end to end:

**Domain construction** — `define-status!`, `define-transition!`,
`define-role!`, `define-permission!`, `define-effect!` each create
entities and assert claims. No files involved.

**Executable behavior** — `can-transition?` queries transition claims
to validate paths. `check-permission` matches user role entities
against permission claims.

**Projection** — `project-workflow-py`, `project-permissions-py`,
`project-notifications-py`, `project-analytics-py` walk the claim
graph and emit valid Python. `project-all!` writes all 4 modules.

**MCP server** — `claimdesk-mcp.rkt` exposes 14 domain tools over
JSON-RPC stdio: list/add statuses, transitions, roles, permissions,
effects, check obligations, project modules, query derived facts.

**Tests** — 13 rackunit tests cover statuses, transitions, permissions,
new-status addition, projection content, and obligations. All pass.

## The agent experiment (E28)

Task: "Add duplicate as a terminal status to ClaimDesk."

Same prompt for both conditions. No hand-holding — the prompt says
"duplicate tickets are no longer active, can be marked from open or
in_progress" and lets the agent figure out the rest.

**Graph condition**: Agent uses MCP tools. Adds 3 claims. Projects
Python automatically.

**File condition**: Agent edits Python files directly.

### Results

```
graph:  0/36 bugs   30.5s mean   $0.067/run
file:   0/36 bugs   71.8s mean   $0.199/run
```

Both 100% correct. Graph is 2.4x faster, 3x cheaper.

### Why both hit 100%

The codebase is small — 4 files, <100 LOC each. The file agent reads
everything, spots `TERMINAL_STATUSES` used in every module, and
updates consistently. No info-gap because there's nothing hidden.

The graph agent's correctness is structural: adding "duplicate" as
terminal means projections automatically include it. The file agent's
correctness is empirical: it reads and understands the patterns.

At this scale, both work. The thesis predicts the file agent starts
missing things as the codebase grows.

### Where the graph wins

Speed and cost, not correctness. The graph agent does ~6 tool calls
(list, add, add, add, check, project). The file agent reads 4 files,
reasons about each one, edits each one — more tokens, more time.

### What would need to change to see info-gap bugs

E24b showed 38-46% first-pass failure when agents BUILD new modules
without seeing each other's code. This experiment tests MODIFICATIONS
to existing code where the patterns are already visible. To expose
the graph's structural advantage, need either:
- Larger codebase (agent can't read everything)
- Non-obvious downstream effects (hidden constraints)
- Concurrent agents (no shared visibility)

## What this proves

1. The vertical slice works: claims → evaluators → obligations →
   projection → tests
2. An agent can use the graph tools to make changes and project
   correct Python
3. Graph-native editing is faster and cheaper than file editing
4. At small scale, correctness is tied — the gap is speed/cost

## E29: Obligation pressure (2026-05-22)

### The test

Same domain, harder task: add "suspended" as a **blocked** status.
This breaks the binary active/terminal partition — the existing code
has no third group. 4 conditions: graph_single, graph_concurrent,
file_single, file_concurrent. 3 runs each. 17 tests (9 structural +
8 cross-domain obligation).

### The changed failure mode

This is the central finding.

The graph acts as a **semantic commitment amplifier**. When the agent
classifies "suspended" as "blocked", the projector emits
BLOCKED_STATUSES, is_blocked(), analytics tagging — all automatically.
Downstream correctness follows from one structural choice.

When the agent classifies "suspended" as "active" (2/6 graph runs),
the wrong structure propagates everywhere: no blocked group, no
obligations fire, 6-7 tests fail. The graph amplified the wrong
abstraction globally.

File-native editing degrades locally: agents patch visible files and
add ad-hoc special cases. Graph-native editing commits globally: one
classification propagates everywhere, for better or worse.

### The core finding

In 6/6 file runs (3 single, 3 concurrent), zero agents introduced
BLOCKED_STATUSES or is_blocked(). They added the status, defined
transitions, sometimes added permissions. But they did not invent the
missing abstraction. The binary partition was the only pattern visible
in the code, so agents replicated it.

This matters because the task required a concept implied by the
business rule but absent from the existing code surface.

### Numbers

Aggregate does not show a clean graph win on efficiency — file is
faster and cheaper. The story is obligation discovery:

| Condition | Obligation bugs/run | Pattern |
|-----------|---------------------|---------|
| graph (correct class.) | 0–1 | projector vocabulary only |
| graph (wrong class.) | 6–7 | cascading structural failure |
| file_single | 4–5 | always misses third group + often permissions |
| file_concurrent | 3 | always misses third group, gets permissions |

### What this means

The graph does not remove semantic understanding from the agent. It
amplifies it. Good classification → downstream correctness. Bad
classification → downstream catastrophe.

This points directly at the next engineering layer: **semantic
commitment validation**. Instead of `add_status(name, group)`, the
agent should declare properties (counts_as_work, can_transition_out,
terminal) and the graph should derive or validate the group. The agent
expresses business semantics; the graph classifies structure.

The stringly-typed projector vocabulary ("tag-blocked" vs "blocked")
is a related engineering gap — needs typed effect constructors, not
better prompting.

## E30: Semantic authority transfer (2026-05-22)

### The fix

E29's central finding was that the graph amplifies classification —
right or wrong. E30 fixes this by moving classification authority from
the agent into the graph.

Instead of `add_status(name="suspended", group="blocked")`, the
property-derived interface asks:

```
add_status(name="suspended", counts_as_work=false, terminal=false)
```

The graph derives `group=blocked` from a group model that encodes what
each group means. The agent never picks an internal ontology label.

Three interfaces tested:

- **graph_label**: agent picks group directly (E29 control)
- **graph_validated**: agent picks group + declares properties; graph
  rejects contradictions
- **graph_properties**: agent declares properties only; graph derives

Also fixed: effect vocabulary mismatch ("blocked" vs "tag-blocked")
that caused test_14 failures even with correct classification.

### Results

| Condition | Obligation bugs | Mean cost |
|-----------|-----------------|-----------|
| graph_label | 0/24 | $0.151 |
| graph_validated | 0/24 | $0.120 |
| graph_properties | 0/24 | $0.109 |
| file_single | 14/24 | $0.149 |

`graph_properties` achieved 0/24 obligation bugs at lower cost than
the file baseline: $0.109/run vs $0.149/run. Across all graph
conditions, graph editing produced 0/72 obligation bugs; the file
baseline produced 14/24.

### What this means

E29 found: graph-native editing amplifies classification. Wrong
classification → wrong cascade. Right classification → correct cascade.

E30 adds: don't make the agent pick internal ontology labels. Let the
agent declare semantic properties. Let the graph derive the
classification.

That is a design principle, not just a benchmark result.

The agent expresses business semantics (`counts_as_work=false,
terminal=false`). The graph derives structural classification
(`blocked`). The projector emits the right Python. The obligation
checker fires the right constraints. File agents keep missing the
absent abstraction — 0/9 runs produced BLOCKED_STATUSES or is_blocked()
across E29 and E30.

### The progression

```
E28: both correct, graph faster/cheaper
E29: graph amplifies classification, right or wrong
E30: graph compiles agent intent, file repeats the missing abstraction
```

The graph went from "amplifies agent decisions" to "compiles agent
intent." The more semantic authority lives in the graph, the fewer ways
the agent can produce structural bugs.

## Files

- `experiments/e27-runtime-claimdesk/claimdesk.rkt` — domain model,
  evaluators, obligation checker, projection (4 modules)
- `experiments/e27-runtime-claimdesk/claimdesk-mcp.rkt` — MCP server
  (14 tools, `--mode` flag for label/validated/properties)
- `experiments/e27-runtime-claimdesk/runner.py` — E28 experiment runner
- `experiments/e27-runtime-claimdesk/e29-runner.py` — E29 experiment runner
  (4 conditions, obligation pressure)
- `experiments/e27-runtime-claimdesk/e30-runner.py` — E30 experiment runner
  (4 conditions, semantic authority transfer)
- `experiments/e27-runtime-claimdesk/demo.rkt` — full pipeline demo
- `experiments/e27-runtime-claimdesk/test-claimdesk.rkt` — 13 unit tests
- `docs/experiments/e27-runtime-claimdesk/results.md` — E28 results
- `docs/experiments/e27-runtime-claimdesk/results-e29.md` — E29 results
- `docs/experiments/e27-runtime-claimdesk/results-e30.md` — E30 results

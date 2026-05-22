# E30: Property-Derived Classification — Semantic Authority Transfer

## One-sentence summary

E30 eliminated the graph's bimodal failure mode from E29 by moving semantic classification from the agent into the graph, achieving 0/72 obligation bugs across 9 graph runs while file agents continued to miss the same structural abstractions (14/24 obligation bugs).

## Context: what E29 found

E29 tested graph-native vs file-native editing on a task that required inventing a third status group ("blocked") absent from the existing code. Two findings:

1. **File agents never invented the missing structural category.** In 6/6 file runs, zero produced `BLOCKED_STATUSES` or `is_blocked()`. They patched "suspended" as an ad-hoc exception.

2. **Graph agents amplified semantic commitments bimodally.** In 4/6 runs the agent classified "suspended" as "blocked" and got downstream obligations for free (0-1 bugs). In 2/6 runs the agent classified it as "active" and the wrong structure propagated globally (6-7 bugs).

The graph was a **semantic commitment amplifier** — correct classification → downstream correctness, wrong classification → downstream catastrophe. E29's conclusion: the graph needs to take over classification, not just amplify the agent's choice.

## What E30 changes

Two engineering changes:

### 1. Property-derived classification

Instead of the agent choosing an internal ontology label (`"active"`, `"terminal"`, `"blocked"`), the agent declares semantic properties of the new status. The graph derives the group.

The group model encodes what each group means:

```
active:   counts_as_work = true,  terminal = false
terminal: counts_as_work = false, terminal = true
blocked:  counts_as_work = false, terminal = false
```

The agent's `add_status` call changes from:

```
add_status(name="suspended", group="blocked")
```

to:

```
add_status(name="suspended", counts_as_work=false, terminal=false)
```

The graph derives `group = blocked` from the properties. The agent never needs to know the internal label.

### 2. Effect vocabulary fix

E29 had a projector vocabulary mismatch: agents wrote effect condition `"blocked"` but the projector checked for the specific string `"tag-blocked"`. This caused test_14 to fail even when classification was correct.

Fixed by accepting group names as valid effect conditions. Both `"blocked"` and `"tag-blocked"` now match. This is a minimal fix — the larger architectural direction is typed effect constructors, but that's not needed for this experiment.

## Experiment design

Same task as E29: add "suspended" as a blocked status. Same 17 integration tests (9 structural + 8 obligation). Same file baseline.

**4 conditions**, 3 runs each:

| Condition | Interface | What the agent does |
|-----------|-----------|-------------------|
| graph_label | `add_status(name, group)` | Agent picks group label directly (E29 control) |
| graph_validated | `add_status(name, group, counts_as_work, terminal)` | Agent picks group AND declares properties; graph rejects contradictions |
| graph_properties | `add_status(name, counts_as_work, terminal)` | Agent declares properties only; graph derives group |
| file_single | Read/edit Python files | Agent modifies code directly |

All agents are Claude Sonnet. Same prompt across all conditions (business requirement, not technical spec). Graph agents use MCP tools, cannot write Python. File agents have full read/write access.

### What each interface communicates

**graph_label**: "Choose active, terminal, or blocked." The agent must know the ontology.

**graph_validated**: "Choose a group AND declare properties. If they contradict, you'll get an error like: `contradiction: group 'active' requires counts_as_work=true but you declared counts_as_work=false`." The agent proposes, the graph validates.

**graph_properties**: "Declare what the status means: does it count as work? is it terminal? The system figures out the rest." The agent expresses business semantics, the graph classifies.

## Results

### Aggregate (3 runs each)

| Condition | Structural bugs | Obligation bugs | Mean time | Mean cost |
|-----------|----------------|-----------------|-----------|-----------|
| graph_label | 0/27 | 0/24 | 53s | $0.151 |
| graph_validated | 0/27 | 0/24 | 47s | $0.120 |
| graph_properties | 0/27 | 0/24 | 50s | $0.109 |
| file_single | 0/27 | 14/24 | 59s | $0.149 |

### Per-run detail

**graph_label** (agent picks group directly)
```
Run 1:  17/17  46.7s  $0.189
Run 2:  17/17  52.1s  $0.132
Run 3:  17/17  59.2s  $0.131
```

**graph_validated** (agent picks group + properties, graph validates)
```
Run 1:  17/17  46.0s  $0.113
Run 2:  17/17  56.3s  $0.133
Run 3:  17/17  38.3s  $0.113
```

**graph_properties** (agent declares properties, graph derives group)
```
Run 1:  17/17  59.4s  $0.118
Run 2:  17/17  39.5s  $0.101
Run 3:  17/17  50.0s  $0.110
```

**file_single** (edit Python files)
```
Run 1:  13/17  65.4s  $0.160  FAILED: 09,10,14,16
Run 2:  12/17  51.8s  $0.139  FAILED: 09,10,14,15,16
Run 3:  12/17  59.8s  $0.148  FAILED: 09,10,14,15,16
```

### Comparison with E29

| Condition | E29 obligation bugs | E30 obligation bugs |
|-----------|---------------------|---------------------|
| graph_single/label | 7/24 (bimodal) | 0/24 |
| file_single | 13/24 | 14/24 |

The graph improved from 7/24 to 0/24. The file baseline is unchanged (13-14/24). The two changes — accepting "blocked" as an effect condition and property-based derivation — eliminated all graph-side failures.

## Analysis

### The property-derived interface works

graph_properties achieved 0/24 obligation bugs across 3 runs. The agent never chose an ontology label. It declared:

```json
{"name": "suspended", "counts_as_work": false, "terminal": false}
```

The graph derived `group = blocked`. The projector emitted `BLOCKED_STATUSES`, `is_blocked()`, analytics tagging. The obligation checker fired for missing permissions. All automatically.

The agent's output confirms it understood what happened:

> `suspended` — blocked group (not active work, not terminal). The graph enforces all the business rules — `suspended` sits in the `blocked` group, so it is excluded from active workload counts automatically, and the obligation checker confirmed every module is clean before projecting.

### graph_label also got 0/24 — but this doesn't invalidate E29

In E30, graph_label got 3/3 correct. In E29, graph_single got 1/3 misclassified. Two factors:

1. **The effect vocabulary fix helped graph_label too.** E29's test_14 failures in correctly-classified runs were caused by "blocked" vs "tag-blocked" mismatch. That's gone now. This accounts for ~1 obligation bug per run in E29.

2. **Misclassification is stochastic.** E29 had a 2/6 (33%) misclassification rate. Getting 3/3 correct has ~30% probability at that rate. 3 runs isn't enough to confirm the rate dropped — only that it didn't happen this time.

The important point: graph_properties **structurally cannot misclassify**. There is no group parameter to get wrong. The derivation is deterministic. That's the architectural difference, even if graph_label got lucky on 3 runs.

### File agents are unchanged

File agents failed the same tests in E30 as in E29:

- test_09 (BLOCKED_STATUSES): 0/3 — never created
- test_10 (is_blocked()): 0/3 — never created
- test_14 (analytics is_blocked tag): 0/3 — no concept to tag with
- test_15/16 (suspend/resume permissions): 1/3 and 0/3 — sometimes misses

Here's what the file agent produced in workflow.py:

```python
ACTIVE_STATUSES = ["open", "in_progress", "resolved", "on_hold"]
TERMINAL_STATUSES = ["closed", "archived"]
ALL_STATUSES = ACTIVE_STATUSES + ["suspended"] + TERMINAL_STATUSES
```

"Suspended" is appended as an orphan — not in either group, not in a third group. No `BLOCKED_STATUSES`, no `is_blocked()`. The file agent adds `is_archived()` but not `is_blocked()`. It handles "suspended" as a one-off case rather than a structural category.

This is not incompetence. The agent correctly identified the status, defined transitions, excluded it from active counts. But it did not invent the missing abstraction because nothing in the code suggested a third group exists.

Here's the graph-projected version for comparison:

```python
TERMINAL_STATUSES = {"archived", "resolved", "closed"}
ACTIVE_STATUSES = {"on_hold", "in_progress", "open"}
BLOCKED_STATUSES = {"suspended"}
ALL_STATUSES = {"suspended", "archived", "resolved", "closed", "on_hold", "in_progress", "open"}

def is_active(status):
    return status in ACTIVE_STATUSES

def is_terminal(status):
    return status in TERMINAL_STATUSES

def is_blocked(status):
    return status in BLOCKED_STATUSES
```

Three parallel sets, three parallel helpers. The structure emerged automatically from the claim `add_status("suspended", counts_as_work=false, terminal=false)`.

### The cost story

graph_properties is the cheapest condition:

| Condition | Mean cost |
|-----------|-----------|
| graph_properties | $0.109 |
| graph_validated | $0.120 |
| file_single | $0.149 |
| graph_label | $0.151 |

graph_properties is 27% cheaper than file_single and 28% cheaper than graph_label. The property interface is simpler for the agent — fewer decisions to reason about, fewer tokens spent deliberating.

## What E30 shows

### 1. Semantic authority transfer works

Moving classification from agent to graph eliminated misclassification. The agent expresses business semantics (`counts_as_work=false, terminal=false`). The graph derives structural classification (`blocked`). The projector emits the right Python. The obligation checker fires the right constraints. Zero bugs.

### 2. The graph is no longer just an amplifier

In E29, the graph amplified whatever the agent chose — right or wrong. In E30 (properties mode), the graph **compiles** semantic properties into structural classification. The agent can't pick the wrong group because it doesn't pick a group at all.

This is the difference between:
- "Agent uses a graph-shaped API" (E29: agent chooses labels)
- "Graph-native programming" (E30: agent declares intent, graph classifies)

### 3. File agents still can't invent absent abstractions

The three-group gap persists across 9 file runs (E29 + E30). No file agent in any run produced `BLOCKED_STATUSES` or `is_blocked()`. This is consistent and reproducible.

The concept is implied by the business rule ("not active, not terminal, can come back") but absent from the code surface. File agents replicate visible patterns. The graph creates the pattern from declared properties.

### 4. The effect vocabulary fix matters

Accepting "blocked" as a valid effect condition (alongside "tag-blocked") eliminated test_14 failures across all graph conditions. This is the minimum fix — the full solution is typed effect constructors — but it demonstrates that stringly-typed protocols create real, consistent failures.

## The progression

```
E28 (simple task):
  graph 0/36 bugs, file 0/36 bugs
  → both correct, graph faster/cheaper

E29 (obligation pressure):
  graph 7-8/24 obligation bugs (bimodal)
  file 9-13/24 obligation bugs (consistent)
  → graph wins when classification correct, fails harder when wrong

E30 (semantic authority transfer):
  graph 0/24 obligation bugs (all conditions)
  file 14/24 obligation bugs (unchanged)
  → graph wins unambiguously on correctness AND cost
```

The graph-native approach went from "amplifies agent decisions" to "compiles agent intent." That's the architectural progression the thesis predicts: the more semantic authority lives in the graph, the fewer ways the agent can produce structural bugs.

## What comes next

The classification guard works for the three-group model. The next question is whether this pattern generalizes:

1. **Larger domain**: More status groups, more cross-domain obligations, more modules. Does the property-derived classification scale to richer ontologies?

2. **Novel groups**: What happens when the agent declares properties that don't match any existing group? The graph should be able to create new groups, not just classify into existing ones.

3. **Multi-step features**: "Suspended" is one status. What about a feature that requires coordinated changes across multiple entity types (new role + new permissions + new effects + new statuses)?

4. **Real app runtime**: The projected Python passes integration tests, but no one is running it as a live application. The graph-canonical claim is stronger if the projected artifact actually serves requests.

## A note on what the tests measure

The obligation tests (09-16) encode a desired structural abstraction, not just behavioral correctness. A file agent that adds `if status == "suspended": skip()` can be behaviorally adequate without creating `BLOCKED_STATUSES`.

This is intentional. The experiment measures structural obligation discovery: did the agent create the infrastructure that would generalize to a second blocked status? The business rule implies a reusable category ("not active, not terminal, can come back"). The tests check whether the agent created that category or handled "suspended" as a one-off.

## Raw data

- JSON results: `experiments/e27-runtime-claimdesk/results-e30-{condition}.json`
- Agent artifacts: `experiments/e27-runtime-claimdesk/output/e30-{condition}-run-{N}/`
- Domain model with property derivation: `experiments/e27-runtime-claimdesk/claimdesk.rkt`
- MCP server with `--mode` flag: `experiments/e27-runtime-claimdesk/claimdesk-mcp.rkt`
- Runner: `experiments/e27-runtime-claimdesk/e30-runner.py`
- E29 results: `docs/experiments/e27-runtime-claimdesk/results-e29.md`
- E29 detailed report: `docs/experiments/e27-runtime-claimdesk/e29-report-for-review.md`

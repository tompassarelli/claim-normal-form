# E29: Graph-Native Editing as Semantic Commitment Amplifier

## One-sentence summary

E29 shows that graph-native editing can externalize missing structural consequences, but shifts failure to the initial semantic classification step.

## Background

I'm building CNF (Claims, Nodes, Facts) — a system where program structure is an entity-attribute-value claim graph with Datalog-derived facts, obligation checking, and code projection. The thesis: when AI agents edit programs through this graph rather than editing source files, they produce fewer cross-domain bugs because the graph surfaces structural consequences invisible from reading code.

Prior experiment E28 tested a simple task ("add duplicate as terminal status") and found both conditions achieved 100% correctness, with graph being 2.4x faster and 3x cheaper. The codebase was too small — the file agent could read everything, no information gap.

E29 was designed to force a specific failure mode: a task that requires inventing a structural concept absent from the existing code.

## The domain: ClaimDesk

A helpdesk ticket system with 4 Python modules (workflow, permissions, notifications, analytics). The baseline has 6 statuses in two groups:

```python
ACTIVE_STATUSES = {"open", "in_progress", "on_hold"}
TERMINAL_STATUSES = {"closed", "resolved", "archived"}
```

Every module references this binary partition. `is_active()`, `is_terminal()`, `ACTIVE_STATUSES`, `TERMINAL_STATUSES` appear throughout. There is no third group anywhere in the codebase.

## The task

> Add "suspended" as a new status to ClaimDesk.
>
> Suspended tickets are paused/frozen — they are not being actively worked on, but they are not closed or resolved either. They can be resumed later.
>
> Business rules:
> - Tickets can be suspended from in_progress or on_hold
> - Suspended tickets can be resumed back to in_progress, or closed directly
> - Suspended tickets are NOT active work and should NOT be counted in active workload metrics
> - Suspended tickets are NOT terminal — they can come back

The prompt is deliberately a business requirement. The agent must figure out the implementation.

### Why this task creates obligation pressure

"Suspended" doesn't fit in either existing group. It's not active (shouldn't count in workload), not terminal (can come back). The business rule implies a reusable third semantic class: non-active, non-terminal, resumable statuses. The correct implementation introduces a third status group — `BLOCKED_STATUSES` — with corresponding helpers (`is_blocked()`), analytics tagging, and new permissions (`suspend`, `resume`).

Nothing in the existing code suggests this third group. A file-reading agent sees two sets and must either invent the abstraction from scratch (conceptual insight beyond the code surface) or handle "suspended" ad-hoc.

### A note on what the tests measure

The obligation tests (09–16) encode the desired structural abstraction, not just behavioral correctness. A file agent that adds `is_suspended()` as a one-off check and excludes suspended from `ACTIVE_STATUSES` could be behaviorally adequate for a single status. The tests are asking: did the agent create the generalizable structural category?

This is intentional. The experiment measures structural obligation discovery — whether the agent introduces the right abstraction, not just whether the code runs. If the only question were "does suspended work?", both conditions would pass. The question is whether the agent created the infrastructure that would scale to a second blocked status.

## How the two conditions work

### Graph condition

The domain model IS the claim graph. Statuses are entities with `status-name` and `status-group` claims. The `add_status` MCP tool takes a name and a group (`"active"`, `"terminal"`, or `"blocked"`).

When an agent calls `add_status("suspended", "blocked")`:
1. The obligation checker fires: "permissions must define suspend action", "permissions must define resume action", "notifications should handle blocked transitions", "analytics must tag blocked transitions"
2. The projector automatically emits `BLOCKED_STATUSES = {"suspended"}` and `def is_blocked(status): return status in BLOCKED_STATUSES`
3. Analytics projection includes `"is_blocked": new_status in BLOCKED_STATUSES` in event dicts

The agent makes one structural choice (the group). Downstream consequences are derived automatically.

### File condition

The agent gets 4 Python files plus models.py and core.py. It reads them, understands the architecture, edits directly. Standard Claude Code with `--dangerously-skip-permissions` for non-interactive mode. Full read access to all files.

The file condition is not artificially crippled. Agents have complete codebase access, can grep, read patterns, and understand the architecture. Concurrent file agents know they're parallelized. This is a fair baseline.

## Experiment design

**4 conditions**, 3 runs each (12 total agent sessions), all Claude Sonnet:

| Condition | Agents | Substrate | Detail |
|-----------|--------|-----------|--------|
| graph_single | 1 | claim graph | Full access to 14 MCP tools |
| graph_concurrent | 3 | claim graph | Separate MCP server per agent, scoped: workflow / permissions / analytics+notifications |
| file_single | 1 | Python files | Full read/write on all files |
| file_concurrent | 3 | Python files | Separate workspace per agent, scoped same as graph, merged by assignment |

**17 integration tests**: 9 structural (status membership, transitions, regression) + 8 obligation (BLOCKED_STATUSES, is_blocked(), notification triggers, analytics tagging, suspend/resume permissions).

## Results

### The changed failure mode

This is the central finding. It comes first because it frames everything else.

File-native editing degrades locally: agents patch visible files and add ad-hoc special cases. The failures are partial — some obligations missed, others caught.

Graph-native editing commits globally: agents choose a structural classification, and the graph propagates it everywhere. When the classification is right, downstream correctness follows automatically. When the classification is wrong, the wrong structure propagates everywhere.

The graph acts as a **semantic commitment amplifier**.

In 2 of 6 graph runs, the agent classified "suspended" as group `"active"` instead of `"blocked"`. The agent's reasoning (from graph_single run 1):

> New status: `suspended` (group: `active` — not terminal, won't count as terminal workload). The existing `not-terminal` notification effect and analytics effect already apply correctly to `suspended` transitions since it's in the `active` group. No new permissions or roles were needed.

This is wrong — the task says "NOT active work" — but the agent made a defensible-sounding error. When this happens, the entire structural cascade fails: no BLOCKED_STATUSES is projected, no blocked-group obligations fire, 6-7 tests fail. The graph propagated the wrong abstraction globally.

When the agent classifies correctly (4/6 runs): 0-1 obligation bugs.

### Aggregate numbers

| Condition | Structural bugs | Obligation bugs | Mean time | Mean cost |
|-----------|----------------|-----------------|-----------|-----------|
| graph_single | 1/27 | 7/24 | 95.3s | $0.208 |
| graph_concurrent | 1/27 | 8/24 | 113.9s | $0.309 |
| file_single | 0/27 | 13/24 | 72.5s | $0.151 |
| file_concurrent | 0/27 | 9/24 | 80.2s | $0.335 |

Note: aggregate numbers do not show a clean graph win on efficiency:

| Comparison | Winner |
|-----------|--------|
| file_single vs graph_single time | file_single |
| file_single vs graph_single cost | file_single |
| file_concurrent vs graph_concurrent time | file_concurrent |
| file_concurrent vs graph_concurrent cost | graph_concurrent, narrowly |
| obligation correctness | graph, but bimodal |
| structural correctness | tied |

The E28 "graph is faster/cheaper" story does not carry into E29. The E29 story is about structural obligation discovery, not efficiency.

### Per-run detail

**graph_single**
```
Run 1:  10/17 pass  33.5s  $0.061  15 turns   FAILED: 02,09,10,13,14,15,16
Run 2:  16/17 pass  93.8s  $0.178  29 turns   FAILED: 14
Run 3:  17/17 pass  158.6s $0.384  55 turns   FAILED: —
```

**graph_concurrent**
```
Run 1:  10/17 pass  54.9s  $0.153             FAILED: 02,09,10,11,12,13,14
Run 2:  16/17 pass  115.1s $0.346             FAILED: 14
Run 3:  16/17 pass  171.6s $0.428             FAILED: 14
```

**file_single**
```
Run 1:  13/17 pass  82.6s  $0.144             FAILED: 09,10,14,16
Run 2:  12/17 pass  62.9s  $0.147             FAILED: 09,10,14,15,16
Run 3:  13/17 pass  72.1s  $0.161             FAILED: 09,10,14,16
```

**file_concurrent**
```
Run 1:  14/17 pass  78.6s  $0.246             FAILED: 09,10,14
Run 2:  14/17 pass  75.4s  $0.372             FAILED: 09,10,14
Run 3:  86.8s       $0.385             FAILED: 09,10,14
```

### The core finding: file agents did not invent the missing structural category

Across all 6 file runs (3 single, 3 concurrent), zero produced `BLOCKED_STATUSES` or `is_blocked()`. Tests 09 and 10 failed in 6/6 file runs.

Here's what a typical file agent produces in workflow.py:
```python
ACTIVE_STATUSES = ["open", "in_progress", "resolved", "on_hold"]
TERMINAL_STATUSES = ["closed", "archived"]
ALL_STATUSES = ACTIVE_STATUSES + TERMINAL_STATUSES + ["suspended"]

def is_suspended(ticket):
    return ticket.status == "suspended"
```

The agent adds suspended as a loose appendage — not in either group, not in a third group. It creates a one-off `is_suspended()` rather than a generalized `is_blocked()` with a backing set.

The file agents were not incompetent. They correctly added the status, defined transitions, sometimes added permissions, excluded suspended from active counts. But they did not invent the missing abstraction.

By contrast, when the graph agent classifies correctly, the projected Python is:
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

The third group emerges automatically from the structural declaration.

### Behavioral vs structural obligation tests

The 8 obligation tests separate into two categories, and the distinction matters:

**Structural abstraction tests (09, 10):** Does the workflow export `BLOCKED_STATUSES` and `is_blocked()`? These exist only when the agent creates a third status group. These measure whether the agent introduced the right abstraction.
- Graph (correct classification): projected automatically — 4/4
- File: never created — 0/6

**Behavioral obligation tests (11–16):** Do notifications fire, does analytics exclude/tag correctly, do permissions exist? These measure whether downstream modules handle suspended correctly.
- test_11/12 (notifications fire for suspended): both conditions pass reliably
- test_13 (active count excludes suspended): both pass when suspended is not in ACTIVE_STATUSES
- test_14 (analytics tags is_blocked): fails in file (no concept) and graph_concurrent (vocabulary issue — see below)
- test_15/16 (suspend/resume permissions): file_concurrent reliably passes, file_single often misses

File agents can pass some behavioral tests through ad-hoc handling while missing the structural abstraction. A file agent that checks `if status == "suspended"` in analytics gets partial behavioral credit without the generalizable structure. This is the difference between "it works for this one status" and "the system is ready for more blocked statuses."

### The projector vocabulary gap

In graph_concurrent, the analytics agent adds an effect with condition `"blocked"`, but the projector checks for the specific string `"tag-blocked"`. The agent's intent is correct — it wants to tag blocked transitions — but the string doesn't match.

This accounts for test_14 failing in 4/4 graph_concurrent runs that produced analytics output, and in graph_single run 2. It's an engineering gap: stringly-typed projector protocols create false failures.

The fix is not better prompting. It's typed effects or enumerated effect constructors — `(effect analytics-tag-blocked)` instead of `condition = "tag-blocked"`. This class of bug should be eliminated structurally.

### Concurrent scoping helps file agents on permissions

file_concurrent reliably passes test_15/16 (suspend/resume permissions) — 6/6 runs. file_single passes test_15 in 1/3 runs and test_16 in 0/3.

A permissions-scoped agent focuses entirely on access control and reliably adds the new actions. The single agent, spreading attention across 4 files, often skips resume.

### Structural tests are easy for everyone

All 4 conditions achieve 26-27/27 on structural tests. Adding the status, defining transitions, preserving existing statuses — these are straightforward regardless of substrate. The interesting divergence is entirely in obligation tests.

## Decomposed view

Excluding misclassification runs (2/6 graph runs where the agent picked "active"):

| Condition | Obligation bugs per run | What's missed |
|-----------|------------------------|---------------|
| graph_single | 0–1 | projector vocabulary only |
| graph_concurrent | 1 | same vocabulary issue |
| file_single | 4–5 | BLOCKED_STATUSES, is_blocked(), analytics tagging, sometimes permissions |
| file_concurrent | 3 | BLOCKED_STATUSES, is_blocked(), analytics tagging |

Including all runs:

| Condition | Total obligation bugs | Out of |
|-----------|----------------------|--------|
| graph_single | 7 | 24 |
| graph_concurrent | 8 | 24 |
| file_single | 13 | 24 |
| file_concurrent | 9 | 24 |

## Interpretation

E29 did not show a simple graph-native victory. It showed a sharper tradeoff.

File-native agents were locally competent but did not introduce the missing structural category in any of 6 runs. They patched "suspended" as an ad-hoc exception — correct enough to work, not structured enough to generalize.

Graph-native agents, when they classified "suspended" correctly as blocked, got almost all downstream obligations for free through projection and graph-derived obligation checking. But graph-native editing was bimodal: a wrong initial classification caused the wrong structure to propagate globally.

The graph does not remove semantic understanding from the agent. It amplifies it.

### What this means architecturally

The graph's failure mode points directly at the next engineering layer: **semantic commitment validation**.

Right now, the agent chooses a group label (`"active"`, `"terminal"`, `"blocked"`). The graph trusts this choice and propagates it. If the agent picks wrong, the graph amplifies the error.

The fix is not prompting. It's encoding group semantics:

```
active:   counts_as_work=true,  can_transition_out=true,  terminal=false
terminal: counts_as_work=false, can_transition_out=false, terminal=true
blocked:  counts_as_work=false, can_transition_out=true,  terminal=false
```

Then instead of asking the agent to choose a group, ask it to declare properties:

```
add_status(
  name="suspended",
  properties={counts_as_work: false, can_transition_out: true, terminal: false}
)
```

The graph derives or recommends the group. Or at minimum, rejects contradictions: if the task says "NOT active work" and the agent declares `group="active"`, the system flags `counts_as_work=true` as contradicting the requirement.

This moves the graph from "commitment amplifier" to "commitment validator" — which is where the thesis actually wants to be.

## What I would test next (E30)

E30: Same task, same baselines, but the graph condition gets a better interface.

Three graph sub-conditions:

1. **graph_group_choice** — agent directly picks active/terminal/blocked (current E29 behavior, as control)
2. **graph_property_choice** — agent specifies semantic properties, graph derives group
3. **graph_validated_choice** — agent picks group, graph rejects contradictions against declared invariants

Plus: fix the projector vocabulary to use typed effect constructors instead of stringly-typed conditions.

Expected: misclassification drops, projector vocabulary bugs disappear, graph gets a cleaner obligation win. Then the comparison against file baselines becomes unambiguous.

This is more valuable than immediately scaling to 10 modules. E29 found the graph's failure mode. Fix it first, then scale.

## Raw data

- JSON results: `experiments/e27-runtime-claimdesk/results-e29-{condition}.json`
- Agent artifacts: `experiments/e27-runtime-claimdesk/output/{condition}-run-{N}/`
- Domain model: `experiments/e27-runtime-claimdesk/claimdesk.rkt` (~500 lines Racket)
- MCP server: `experiments/e27-runtime-claimdesk/claimdesk-mcp.rkt` (14 tools, JSON-RPC stdio)
- Runner: `experiments/e27-runtime-claimdesk/e29-runner.py` (4 conditions, 17 tests)
- E28 baseline: `docs/experiments/e27-runtime-claimdesk/results.md`

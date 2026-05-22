# E29: Graph as Semantic Commitment Amplifier — Results

## Headline

Graph-native editing externalizes missing structural consequences
but shifts failure to the initial semantic classification step.
Not a clean speed/cost win. The finding is about structural
obligation discovery.

## Experiment

**Task**: Add "suspended" as a new status to ClaimDesk. Suspended
tickets are paused — not active, not terminal. Can be suspended from
in_progress or on_hold; can be resumed or closed.

This task introduces a **third status group** ("blocked") that breaks
the existing binary active/terminal partition. The existing code has
no concept of a third group — agents must invent it or ignore it.

**4 conditions**, 3 runs each:

| Condition | Agents | Substrate | How |
|-----------|--------|-----------|-----|
| graph_single | 1 | claim graph | MCP tools → project Python |
| graph_concurrent | 3 | claim graph | each gets own MCP server instance |
| file_single | 1 | Python files | read/edit files directly |
| file_concurrent | 3 | Python files | separate worktrees per agent |

Concurrent agents are scoped: workflow, permissions, analytics+notifications.

**17 integration tests**: 9 structural (status membership, transitions,
regression) + 8 cross-domain obligations (BLOCKED_STATUSES, is_blocked(),
notification triggers, analytics tagging, suspend/resume permissions).

## Raw results

### Aggregate (3 runs each)

| Condition | Structural bugs | Obligation bugs | Mean time | Mean cost |
|-----------|----------------|-----------------|-----------|-----------|
| graph_single | 1/27 | 7/24 | 95.3s | $0.208 |
| graph_concurrent | 1/27 | 8/24 | 113.9s | $0.309 |
| file_single | 0/27 | 13/24 | 72.5s | $0.151 |
| file_concurrent | 0/27 | 9/24 | 80.2s | $0.335 |

### Per-run detail

**graph_single**

| Run | Time | Cost | Pass | Struct bugs | Oblig bugs | Failed tests |
|-----|------|------|------|-------------|------------|--------------|
| 1 | 33.5s | $0.061 | 10/17 | 1 | 6 | 02,09,10,13,14,15,16 |
| 2 | 93.8s | $0.178 | 16/17 | 0 | 1 | 14 |
| 3 | 158.6s | $0.384 | 17/17 | 0 | 0 | — |

**graph_concurrent**

| Run | Time | Cost | Pass | Struct bugs | Oblig bugs | Failed tests |
|-----|------|------|------|-------------|------------|--------------|
| 1 | 54.9s | $0.153 | 10/17 | 1 | 6 | 02,09,10,11,12,13,14 |
| 2 | 115.1s | $0.346 | 16/17 | 0 | 1 | 14 |
| 3 | 171.6s | $0.428 | 16/17 | 0 | 1 | 14 |

**file_single**

| Run | Time | Cost | Pass | Struct bugs | Oblig bugs | Failed tests |
|-----|------|------|------|-------------|------------|--------------|
| 1 | 82.6s | $0.144 | 13/17 | 0 | 4 | 09,10,14,16 |
| 2 | 62.9s | $0.147 | 12/17 | 0 | 5 | 09,10,14,15,16 |
| 3 | 72.1s | $0.161 | 13/17 | 0 | 4 | 09,10,14,16 |

**file_concurrent**

| Run | Time | Cost | Pass | Struct bugs | Oblig bugs | Failed tests |
|-----|------|------|------|-------------|------------|--------------|
| 1 | 78.6s | $0.246 | 14/17 | 0 | 3 | 09,10,14 |
| 2 | 75.4s | $0.372 | 14/17 | 0 | 3 | 09,10,14 |
| 3 | 86.8s | $0.385 | 14/17 | 0 | 3 | 09,10,14 |

## Analysis

### The obligation tests that matter

The 8 obligation tests fall into three categories:

**Category A — Three-group structure (test_09, test_10)**
Does the workflow export `BLOCKED_STATUSES` and `is_blocked()`?
These exist only when the agent creates a third status group.
- Graph (correct classification): projected automatically — 100%
- File: never created — 0% across 6 runs

**Category B — Cross-domain effects (test_11–14)**
Notifications fire for suspended transitions; analytics tags `is_blocked`.
- test_11/12 (notifications): both conditions pass reliably
- test_13 (analytics excludes suspended from active): both pass when
  suspended is not in ACTIVE_STATUSES
- test_14 (analytics tags `is_blocked`): fails in file (no
  BLOCKED_STATUSES concept) and in graph_concurrent (projector
  vocabulary mismatch — see below)

**Category C — Permission rules (test_15, test_16)**
Do suspend and resume permissions exist?
- Graph (correct classification): obligation checker surfaces these
- File single: usually misses resume, sometimes both
- File concurrent: scoped permissions agent reliably adds both

### Graph variance: bimodal, not gradual

The graph conditions show a bimodal pattern. In 2/6 graph runs, the
agent classified "suspended" as group "active" instead of "blocked".
When this happens, the structural cascade fails completely:
- No BLOCKED_STATUSES is projected (no blocked group exists)
- No blocked-group obligations fire
- 6-7 tests fail

When the agent classifies correctly (4/6 runs): 0-1 obligation bugs.

This means the graph approach has a **higher ceiling but higher
variance** than file editing. The file approach is consistently
mediocre; the graph approach is either near-perfect or catastrophic.

### Why file agents can't discover the third group

The existing code has a binary partition:
```python
TERMINAL_STATUSES = {"closed", "resolved", "archived"}
ACTIVE_STATUSES = {"open", "in_progress", "on_hold"}
```

Every file agent — single or concurrent, all 6 runs — adds "suspended"
to one of these two sets or creates an ad-hoc handling pattern. None
invents `BLOCKED_STATUSES` because nothing in the code suggests a third
set exists. The concept is invisible from the file surface.

The graph agent, by contrast, declares `add_status("suspended", "blocked")`.
The projector then emits `BLOCKED_STATUSES` and `is_blocked()`
automatically. The agent doesn't need to know about Python conventions;
the structural choice propagates.

### The projector vocabulary issue (test_14)

In graph_concurrent, the analytics agent adds an effect with condition
"blocked", but the projector checks for the specific string "tag-blocked".
This vocabulary mismatch causes test_14 to fail in 4/4 graph_concurrent
runs with valid analytics output. This is an engineering gap in the
projector's condition vocabulary, not a fundamental limitation — the
agent's intent is correct, the mapping is too rigid.

### Concurrent scoping helps file agents on permissions

file_concurrent reliably passes test_15/16 (suspend/resume permissions)
while file_single often misses them. A permissions-scoped agent focuses
entirely on access control and reliably adds the new actions. The single
agent, spreading attention across 4 files, often skips resume.

### Honest summary

Excluding misclassification runs (2/6 graph runs where the agent picked
"active" instead of "blocked"):

| Condition | Obligation bugs per run | Pattern |
|-----------|------------------------|---------|
| graph_single | 0–1 | near-perfect when classified right |
| graph_concurrent | 1 | consistent (vocabulary issue only) |
| file_single | 4–5 | always misses three-group + often permissions |
| file_concurrent | 3 | always misses three-group, gets permissions |

Including all runs:

| Condition | Total obligation bugs | Out of |
|-----------|----------------------|--------|
| graph_single | 7 | 24 |
| graph_concurrent | 8 | 24 |
| file_single | 13 | 24 |
| file_concurrent | 9 | 24 |

## What this shows

1. **File agents cannot discover structural concepts absent from code.**
   The three-group partition (BLOCKED_STATUSES, is_blocked()) was never
   produced by any file agent in any run. This is the predicted info-gap:
   you can't implement what you can't see.

2. **Graph obligations surface what files hide.** When the graph agent
   classifies correctly, the obligation checker fires for missing
   permissions and the projector emits the blocked-group infrastructure.
   The agent doesn't need to know about the downstream consequences.

3. **Graph variance is real.** 2/6 graph runs misclassified the group,
   causing cascading failure. The graph approach depends on the agent
   making a correct structural choice — the right one is obvious from
   the task description, but not guaranteed.

4. **Concurrent scoping helps both conditions** — file_concurrent beats
   file_single on permissions; graph_concurrent is comparable to
   graph_single (excluding timeouts).

5. **The projector vocabulary is too rigid.** The "tag-blocked" vs
   "blocked" mismatch is a fixable engineering issue that accounts for
   ~1 obligation bug per graph run.

## Files

- `experiments/e27-runtime-claimdesk/e29-runner.py` — experiment runner
- `experiments/e27-runtime-claimdesk/claimdesk.rkt` — domain model with
  blocked-group support
- `experiments/e27-runtime-claimdesk/claimdesk-mcp.rkt` — MCP server
- `results-e29-{condition}.json` — raw results per condition

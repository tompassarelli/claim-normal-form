# 032: F11 — agent tools: 0/4 info-gap bugs

## The question

Can graph-backed tools eliminate the information-gap bugs that
agents consistently produce when building from code alone?

## Four conditions tested

**Git baseline** — agents see models.py and core.py (simplified),
no graph, no file access. Same as F9/F10.

**Wrapped** — 7 high-level MCP tools (list_values, where_defined,
etc.) that translate between natural-language queries and Datalog.

**Raw** — 4 low-level tools: query, claim, resolve_symbol, inspect.
The prompt includes Datalog schema docs and translation examples.

**Datalog** (the final design) — 4 tools at the right abstraction:
`discover(name)`, `discover_all(kind?)`, `dependencies(symbol?)`,
`declare_intent(module, ...)`. Each returns a complete, actionable
answer: values, module, and exact import statement in one call.

## Final results

| Condition | First-pass | Info-gap bugs | Build time |
|-----------|-----------|---------------|------------|
| Git       | 16/22     | 4/4           | 27s        |
| Wrapped   | 17/22     | 1/4           | 85s        |
| Raw       | 15/22     | 4/4           | 109s       |
| Datalog   | 20/22     | **0/4**       | 44s        |

## What the datalog condition did right

All four agents that needed TERMINAL_STATUSES imported correctly:

```python
from workflow import TERMINAL_STATUSES  # analytics, escalation, notifications, comments
from workflow import ACTIVE_STATUSES    # analytics
```

Each agent called `discover("TERMINAL_STATUSES")`, got back the
values AND the import statement, and used the import. No hardcoded
constants. No guessing.

## Three things it took

### 1. The right tool abstraction

Raw Datalog (4/4 info-gap bugs) vs discover-style tools (0/4).
Same graph, same data. The tools matter:

- `discover("TERMINAL_STATUSES")` returns values, module, and
  import statement in one call
- Raw required: resolve_symbol → inspect → find py-body → inspect
  body → extract values → query source-module (4-5 chained calls
  with regex parsing between each)

Agents can use "look up this symbol" but can't navigate
entity-graph indirection.

### 2. Prompt engineering that blocks guessing

The preamble must actively discourage guessing:

> There is a workflow.py module that you CANNOT see. It defines
> constants like TERMINAL_STATUSES and ACTIVE_STATUSES with values
> that **differ from what you would guess.** You MUST call discover()
> to get the actual values.

Plus a concrete example of what discover() returns. Without this,
agents see "closed" in `close_ticket()` and infer terminal statuses
from training data.

### 3. An MVCC bug in the daemon

The root cause of the "empty graph" intermittent failures:
`reset-store!` in the Racket daemon replaces `current-ctx` (a
thread-local parameter) with a new context object. But the MVCC
`committed` snapshot still references the old context. Subsequent
writes go to the new context; `snapshot-ctx` captures from it; but
`set-box! committed` stores a copy that becomes invisible to new
connections because the snapshot was taken from the wrong parameter
binding.

Fix: don't call reset when the daemon starts fresh (checkpoint
deleted). Confirmed with isolation test: WITH reset, 0 entities
visible; WITHOUT reset, correct count visible.

This bug only affects multi-connection scenarios (F11 is the first
experiment with parallel agents each opening separate daemon
connections). Prior experiments (F2-F10, E18-E19) used single
connections or bridge mode and were never affected.

## What this means

The hypothesis from F10 was that agents couldn't navigate the
Datalog schema to find information. F11 confirms: when tools match
the agent's vocabulary ("discover this symbol" vs "query this
Datalog pattern"), retrieval works and info-gap bugs go to zero.

This is the first time any condition has achieved 0/4 info-gap bugs.
The remaining 2 failures (test_09 audit, test_11 permissions) are
spec-interpretation bugs, not missing information.

## Remaining speed cost

Datalog build time (44s) vs git (27s) — 1.6x overhead. This is
from MCP server startup (6 graph-tools.py instances), daemon
socket connections, and Datalog query evaluation. Significantly
better than wrapped (85s) and raw (109s) because the tool layer
batches queries (2 daemon RPCs per discover_all instead of 40+).

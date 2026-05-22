# E24b: Concurrent Facade Agents — Results

**Date:** 2026-05-22

## Summary

3 agents (notifications, analytics, permissions) build ClaimDesk
modules concurrently. Two conditions: CNF (shared daemon + facade
tools, no filesystem) vs file (full source access + repair agent).

**CNF condition: 9/24 info-gap bugs (38% failure rate)**
**File condition first pass: 11/24 info-gap bugs (46%)**
**File condition after repair: 1/24 (4%)**

## CNF condition — 6 runs (3 + 3 with updated tool descriptions)

### Batch 1 (original tool descriptions)

| Run | Info-gap | Failures |
|-----|----------|----------|
| 1 | 2/8 | test_06, test_08 |
| 2 | 4/8 | test_02, test_04, test_06, test_08 |
| 3 | 3/8 | test_06, test_07, test_08 |

### Batch 2 (added "permissions, access control" to discover_lifecycle)

| Run | Info-gap | Failures |
|-----|----------|----------|
| 4 | 3/8 | test_06, test_07, test_08 |
| 5 | 3/8 | test_06, test_07, test_08 |
| 6 | 3/8 | test_06, test_07, test_08 |

Tool description update had no effect. Batch 2 locked at exactly
3/8 per run: test_06 + test_07 + test_08.

### Per-agent discovery rates (6 runs combined)

| Signal | notifications | analytics | permissions |
|--------|:---:|:---:|:---:|
| imports_workflow | 2/6 | 5/6 | 0/6 |
| knows_archived | 6/6 | 0/6 | 0/6 |
| mean turns | 4.3 | 4.5 | 1.8 |
| mean cost | $0.067 | $0.051 | $0.038 |

**Analytics** reliably imports from workflow via the facade.
**Notifications** discovers "archived" but hardcodes constants.
**Permissions** never imports from workflow. In the latest batch,
it explicitly said: "No external lifecycle registry — ticket
states are plain strings in core.py. I have everything I need."

### Consistent failure pattern

All 6 runs fail the same 3 tests:

- **test_06** (no_manage_archived): Permissions doesn't know archived
  tickets should be unmanageable. The agent has no mental model
  connecting "lifecycle state" to "access control."

- **test_07** (notifications_imports_workflow): Notifications knows
  about archived but defines its own constant instead of importing.
  Same pattern as E24a.

- **test_08** (permissions_imports_workflow): Permissions never
  discovers workflow.py exists.

## File condition — 3 runs

| Run | First pass | After repair | Repair rounds |
|-----|-----------|-------------|---------------|
| 1 | 5/8 | 0/8 | 1 |
| 2 | 3/8 | 1/8 | 1 |
| 3 | 3/8 | 0/8 | 1 |

First pass: 11/24 (46%). After repair: 1/24 (4%).
Every run needed 1 repair round.

### First-pass failures

| Test | Run 1 | Run 2 | Run 3 |
|------|:---:|:---:|:---:|
| test_02 | FAIL | — | — |
| test_04 | FAIL | — | — |
| test_06 | FAIL | FAIL | FAIL |
| test_07 | FAIL | FAIL | FAIL |
| test_08 | FAIL | FAIL | FAIL |

Same core failures as CNF (test_06/07/08), plus occasional extra
failures in analytics (test_02, test_04).

### Per-agent discovery rates

| Signal | notifications | analytics | permissions |
|--------|:---:|:---:|:---:|
| imports_workflow | 3/3 | 2/3 | 3/3 |
| knows_archived | 2/3 | 1/3 | 3/3 |
| mean turns | 6.7 | 4.7 | 3.7 |
| mean cost | $0.120 | $0.086 | $0.087 |

File agents have higher import rates because the repair agent
fixes non-importing code. The "after repair" code imports from
workflow even when the first-pass code didn't.

## Cost comparison

| Metric | CNF | File |
|--------|-----|------|
| Mean cost/run | $0.156 | $0.293 |
| Repair rounds | 0 | 1 per run |
| Final info-gap rate | 38% | 4% |
| Cost per correct test | — | — |

File costs ~2x more but achieves a much lower final failure rate.

## What this means

### The facade works for semantically aligned tasks

Analytics agents reliably discover workflow through the facade
(5/6 import). The discover_all → discover path works when the
agent's task naturally maps to "what statuses/states exist."

### The facade fails for semantically distant tasks

The permissions agent doesn't see "lifecycle state" as relevant
to "access control." It looks at its available tools, decides
they're about status/lifecycle stuff, and writes pure
role-checking code. The tool descriptions say "Call this before
writing code involving... permissions, access control" (added in
batch 2), but the agent already has a mental model of permissions
that doesn't include lifecycle state.

### Import discipline is weak regardless of condition

Both conditions produce agents that know about archived tickets
(from context or discovery) but hardcode the constant instead of
importing from workflow. This is a consistent E24a finding now
replicated at scale.

### Repair is a strong mechanism

The file condition's repair agent sees test failures + full source
and reliably fixes them. This is a structural advantage that CNF
currently lacks.

### E24a's result doesn't generalize to 3 agents

E24a tested notifications + analytics (both semantically close to
the facade). Adding permissions breaks the pattern. The facade
needs to either cover ALL possible agent-task semantics or agents
need a mandatory discovery step.

## What would need to change

1. **Mandatory explore**: Force all agents to call discover_all
   before generating code, regardless of perceived relevance.
   Trade-off: slower, more expensive, less natural.

2. **Task-aware facade**: A meta-tool that maps the agent's task
   description to relevant graph regions. "You're building
   permissions — here's what lifecycle state means for you."

3. **CNF repair mechanism**: Add a post-generation step where a
   repair agent sees test failures and rewrites modules using the
   graph. Would level the playing field with file condition.

4. **Broader discover_all**: Make the entry point more directive:
   "ALWAYS call this first. Every agent task depends on codebase
   knowledge you don't have yet."

## Raw data

See `results-cnf.json` and `results-file.json` in the experiment
directory.

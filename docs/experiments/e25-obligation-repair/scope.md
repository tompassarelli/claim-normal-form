# E25: Obligation Repair — Scope

**Date:** 2026-05-22

## What E24b proved

Facade discovery tools work for semantically aligned tasks — agents
that need workflow knowledge find it through discover/discover_all.
But they fail when hidden structure is relevant but not obviously
relevant. The permissions agent doesn't know lifecycle state matters
for access control, so it never looks. This is the "permissions
problem": cross-domain constraints that fall outside an agent's
mental model of its own task.

## What E25 tests

Whether a graph-native repair loop can close the gap that pure
discovery leaves open.

> **finish_check: use the graph to find obligations the agent's code
> doesn't account for.**

The agent writes code using facade tools. Then `finish_check` analyzes
the generated code against the graph and surfaces cross-domain
constraints the agent missed. The agent gets one chance to fix.

## The finish_check tool

`finish_check(task_description, generated_code)` queries the graph to
find missing obligations:

- **Domain concepts the code touches** — tickets, statuses, roles
- **Cross-domain constraints not accounted for** — terminal statuses
  block notifications, archived tickets need admin access
- **Missing imports** from workflow module
- **Hardcoded constants** that should reference graph-defined values

Output: a structured obligation report listing each gap with the
relevant graph evidence (which claim, which relation).

## Conditions

| Condition | Graph | Tools | Repair |
|-----------|-------|-------|--------|
| **file_first_pass** | none | full source (Read, Bash, Write) | none |
| **file_repair** | none | full source | repair agent, 1 round |
| **cnf_facade** | shared daemon | facade tools | none |
| **cnf_repair** | shared daemon | facade + finish_check | obligation loop, 2 rounds max |

### file_first_pass

Baseline. 3 agents in git worktrees, full source access, three-way
merge. No repair. Whatever they produce on first pass is final.

### file_repair

Same as file_first_pass, plus a repair agent that sees test failures
and gets one round to fix all three modules. This is E24b's strong
file baseline.

### cnf_facade

E24b's CNF condition. Facade discovery only, no repair. Reproduces
the permissions problem.

### cnf_repair

The new condition. Same facade tools, plus the repair loop:

1. Agent generates code using facade tools
2. Runner calls `finish_check(task_description, generated_code)`
3. If obligations found: agent receives obligation report + its own
   code, generates fixed version
4. Runner calls `finish_check` once more (2 rounds max)
5. Final code goes to test

## Agents

Same three agents as E24b: notifications (Agent A), analytics
(Agent B), permissions (Agent C). Same APIs, same prompts.

## Tests

Same 15 tests as E24b. 8 info-gap, 2 cross-module, 5 basic.

The tests that matter for E25 are the ones cnf_facade fails:

```
test_05: archive requires admin role
test_06: can_manage returns False for archived tickets (agent role)
test_08: permissions imports from workflow (not hardcoded)
```

These are the permissions-problem tests. finish_check should surface
the lifecycle/permissions constraint that pure discovery misses.

## The cnf_repair protocol (detail)

```
Agent generates code
        │
        ▼
 finish_check(task, code)
        │
        ├── No obligations ──► done, run tests
        │
        ▼
 Obligation report:
   "Your code handles roles but doesn't account for
    lifecycle state. The graph shows TERMINAL_STATUSES
    {closed, archived} from workflow.py. Archived tickets
    require admin role (claim: archive → admin_only)."
        │
        ▼
 Agent gets: report + its own code
 Agent generates: fixed code
        │
        ▼
 finish_check(task, fixed_code)
        │
        ├── No obligations ──► done, run tests
        │
        ▼
 Still has obligations ──► done anyway, run tests
                           (2 rounds max)
```

## Measurements

### Primary: info-gap bugs

Per-condition failure rate on the 8 info-gap tests, across 3 runs.

| Metric | file_first_pass | file_repair | cnf_facade | cnf_repair |
|--------|:-:|:-:|:-:|:-:|
| Info-gap failures | measure | measure | measure | measure |

### Secondary

| Metric | Description |
|--------|-------------|
| Repair rounds used | How many finish_check rounds before clean |
| Obligation specificity | Are obligations actionable or vague? |
| Cost per condition | Total API cost across 3 agents |
| Wall clock | End-to-end time per condition |
| First-pass vs final | How much does repair actually fix? |

## Success criteria

1. **cnf_repair matches or beats file_repair** on final info-gap rate
2. **cnf_repair produces specific, actionable obligations** — not
   "check for edge cases" but "archived tickets require admin role,
   your code doesn't check lifecycle state"
3. **The permissions problem is solved** — the obligation mechanism
   surfaces lifecycle/permissions constraints that pure facade
   discovery misses
4. **Repair is bounded** — most agents need 0-1 rounds, never more
   than 2

## Risk

**finish_check might be too noisy.** If it surfaces 20 obligations
per module, the agent can't prioritize and the repair round is
wasted on irrelevant fixes. Precision matters more than recall —
better to surface 3 real obligations than 15 that include 3 real ones.

**finish_check might just be a better prompt.** If the obligation
report is effectively "here's what you missed, go fix it," this
could be replicated by a smarter system prompt without the graph.
The control for this: the obligation report must reference specific
graph claims, not just general advice. If it works, a follow-up
ablation can test prompt-only vs graph-backed obligations.

## Implementation plan

### Reuse from E24b

- Runner infrastructure: daemon, init_graph, agent launch, code
  extraction, test execution, discovery metrics
- facade-tools.py MCP server
- All 15 tests
- File condition runner (worktrees, merge, repair)
- Agent prompts

### New for E25

1. **finish_check tool** — graph query that analyzes code against
   claims, returns structured obligation report
2. **Repair loop in runner** — call finish_check, feed report back
   to agent, extract fixed code, repeat once
3. **Four-condition runner** — file_first_pass, file_repair,
   cnf_facade, cnf_repair
4. **Obligation quality metrics** — specificity scoring for reports

### Estimated effort

| Component | Lines |
|-----------|-------|
| finish_check implementation | ~120 |
| Repair loop in runner | ~80 |
| Four-condition orchestration | ~60 |
| Obligation metrics / analysis | ~40 |
| **Total new** | **~300** |

Reused from E24b: ~1300 lines (runner + facade + tests + file condition).

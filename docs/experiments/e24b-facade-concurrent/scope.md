# E24b: Concurrent Facade Agents — Scope

**Date:** 2026-05-22

## What E24a proved

A semantic facade (discover_all + discover) reliably eliminates
info-gap bugs. 0% failure rate across 10 facade runs vs 60% without.
Agents discover hidden workflow knowledge through tool exploration
without being told what to look for.

## What E23b proved

Shared daemon MVCC works for concurrent semantic edits. Two agents
on one daemon, zero conflicts, both changes compose. File-based
agents: 4 merge conflicts, repair round needed.

## What E24b tests

E24a tested discovery. E23b tested concurrent composition. E24b
combines them:

> **Facade + shared graph + concurrent agents + realistic app slice.**

Three agents build ClaimDesk modules simultaneously. All need hidden
workflow knowledge. Their modules have overlapping concerns (archived
tickets affect all three). The facade is their only information
channel.

## Conditions

| Condition | Graph | Tools | Coordination |
|-----------|-------|-------|--------------|
| **cnf** | shared daemon | facade (discover_all, discover, dependencies, verify_references, discover_lifecycle) | implicit via graph |
| **file** | none | full source tools (Read, Bash, Write) | git worktrees, merge, repair agent |

### CNF condition

- 1 shared daemon, graph loaded with models.py + core.py + workflow.py
- 3 agents, each gets its own facade MCP server process
- Built-in tools disabled (`--tools ""`)
- MCP tools whitelisted (`--allowedTools`)
- Agents see models.py + core.py in prompt, must discover workflow.py

### File condition

- 3 agents, each in an isolated git worktree
- Full source tools enabled (Read, Bash, Write, Edit)
- Agents see models.py + core.py + workflow.py (it's a file they can read)
- After all agents finish: three-way merge
- If merge conflicts or test failures: repair agent gets one round

## Agents

### Agent A: notifications.py

Suppress notifications for archived tickets. Notify on status
transitions. Track subscribers per ticket.

Required API:
- `notify_transition(ticket_id, old_status, new_status) -> None`
- `subscribe(ticket_id, user_email) -> None`
- `get_notifications(ticket_id=None) -> list[dict]`
- `reset_notifications() -> None`

### Agent B: analytics.py

Ticket summary by status, active count, unassigned list. Must
correctly categorize all statuses including on_hold and archived.

Required API:
- `ticket_summary() -> dict` (every status → count)
- `active_ticket_count() -> int` (exclude terminal)
- `unassigned_tickets() -> list[Ticket]` (exclude terminal)

### Agent C: permissions.py

Role-based access control. Agents can manage assigned tickets.
Admins can manage all. Archive requires admin role. Reassignment
requires admin or current assignee.

Required API:
- `can_manage(user_id, ticket_id) -> bool`
- `can_archive(user_id) -> bool`
- `can_reassign(user_id, ticket_id) -> bool`
- `check_permission(user_id, ticket_id, action) -> bool`

## Hidden knowledge surface

All three agents need knowledge from workflow.py:

| Knowledge | notifications | analytics | permissions |
|-----------|:---:|:---:|:---:|
| TERMINAL_STATUSES | must suppress | must exclude | archive gate |
| ACTIVE_STATUSES | — | must use for active_count | — |
| archived as terminal | must silence | must exclude | must require admin |
| on_hold as active | — | must include | — |
| VALID_TRANSITIONS | — | — | transition validation |

## Integration tests

### Info-gap tests (the ones that matter)

```
test_01: archived tickets don't trigger notifications
test_02: active_ticket_count excludes archived
test_03: ticket_summary includes on_hold and archived
test_04: unassigned_tickets excludes archived
test_05: archive requires admin role
test_06: can_manage returns False for archived tickets (agent role)
test_07: notifications imports from workflow (not hardcoded)
test_08: permissions imports from workflow (not hardcoded)
```

### Cross-module tests

```
test_09: analytics + permissions: admin sees all tickets in summary
test_10: notifications + permissions: only permitted users get notified
```

### Basic functionality tests

```
test_11: basic notification fires on transition
test_12: basic ticket_summary counts correctly
test_13: basic can_manage for assigned agent
test_14: subscribe adds subscriber
test_15: unassigned returns only unassigned active tickets
```

~15 tests total. 8 info-gap, 2 cross-module, 5 basic.

## Measurements

### Primary: info-gap bugs

Same as E24a. Count info-gap test failures across conditions.
Run 3 times per condition minimum.

### Secondary: coordination cost

| Metric | CNF | File |
|--------|-----|------|
| Merge conflicts | N/A (shared graph) | count |
| Repair rounds needed | 0 expected | count |
| Total wall clock | measure | measure |
| Total cost | measure | measure |
| First-pass test score | measure | measure |
| Final test score (after repair) | measure | measure |

### Discovery metrics (from E24a)

Per-agent: imports_workflow, knows_archived, knows_on_hold, turns,
cost, hardcoded_statuses.

## Prompts

Same minimal style as E24a. ~40 words each. No mention of workflow.py,
specific constants, or tool names.

CNF agents get: "Use the available tools to discover the codebase
structure before writing code."

File agents get: "Read the existing codebase files to understand the
project structure before writing code."

Both see models.py and core.py inline.

## Architecture

### CNF condition

```
                    ┌──────────────┐
                    │   Runner     │
                    └──────┬───────┘
              ┌────────────┼────────────┐
              ▼            ▼            ▼
         ┌────────┐  ┌────────┐  ┌────────┐
         │Agent A │  │Agent B │  │Agent C │
         │notif.  │  │analyt. │  │perms.  │
         └───┬────┘  └───┬────┘  └───┬────┘
             │           │           │
         ┌───▼────┐  ┌───▼────┐  ┌───▼────┐
         │Facade A│  │Facade B│  │Facade C│
         └───┬────┘  └───┬────┘  └───┬────┘
             │           │           │
             └───────────┼───────────┘
                         │ TCP :7891
                    ┌────▼─────┐
                    │  Daemon  │
                    │  (MVCC)  │
                    └──────────┘
```

### File condition

```
                    ┌──────────────┐
                    │   Runner     │
                    └──────┬───────┘
              ┌────────────┼────────────┐
              ▼            ▼            ▼
         ┌────────┐  ┌────────┐  ┌────────┐
         │Agent A │  │Agent B │  │Agent C │
         │notif.  │  │analyt. │  │perms.  │
         │(wt-1)  │  │(wt-2)  │  │(wt-3)  │
         └────────┘  └────────┘  └────────┘
              │           │           │
              ▼           ▼           ▼
         ┌────────────────────────────────┐
         │  git merge (three-way)         │
         └────────────┬───────────────────┘
                      ▼
         ┌────────────────────────────────┐
         │  Repair agent (if needed)      │
         └────────────────────────────────┘
```

## Implementation plan

### Reuse from E24a

- facade-tools.py (the MCP server) — unchanged
- Runner infrastructure: daemon start/stop, init_graph, agent launch,
  code extraction, test execution, discovery metrics
- MCP config generation, `--tools ""`, `--allowedTools`

### New for E24b

1. **permissions.py tests** — ~5 new info-gap tests + basic tests
2. **File condition runner** — git worktree setup, merge, repair agent
3. **Third agent** — prompts, API spec, test wiring
4. **Cross-module tests** — tests that import from 2+ agent modules
5. **Multi-condition comparison** — run both conditions, aggregate

### Estimated effort

| Component | Lines |
|-----------|-------|
| permissions tests | ~60 |
| File condition (worktree + merge + repair) | ~150 |
| Third agent integration | ~40 |
| Cross-module tests | ~30 |
| Runner updates (3 agents, 2 conditions) | ~80 |
| **Total new** | **~360** |

Reused from E24a: ~960 lines (runner + facade server).

## Success criteria

1. **CNF 0% info-gap failure rate** across 3+ runs (extending E24a's
   result to 3 agents)
2. **File condition has >0 info-gap bugs** or merge conflicts requiring
   repair
3. **File condition needs repair rounds** that CNF does not
4. **The cost/correctness tradeoff favors CNF** when repair time is
   included

## Risk

The file condition might do well. With full source access, agents can
read workflow.py directly — they don't need discovery tools because
the file IS visible. The info-gap only exists in the CNF condition
where agents can't read files.

This means E24b's info-gap comparison may not be apples-to-apples.
The file condition's challenge is coordination (merge conflicts), not
discovery. E24b might prove: "CNF eliminates info-gap bugs via facade"
AND "file eliminates info-gap bugs via file access" AND "the
difference is coordination cost."

That's still a valid result — it means the graph's value at this
scale is coordination, not discovery (discovery is already proven by
E24a). If file agents get 0 info-gap bugs but need 2 repair rounds
while CNF agents get 0 bugs with 0 repairs, that's the E23b result
replicated at facade scale.

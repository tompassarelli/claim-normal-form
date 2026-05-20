# F4: Overlapping Edits — Shared File Coordination

## The question

What happens when multiple agents modify the same files? F2 and F3
proved that shared semantic state eliminates information-gap bugs when
agents write separate files. F4 tests the harder case: agents modify
shared configuration, shared workflow code, and must incorporate a
mid-run requirement change.

## Setup

Same ClaimDesk codebase. Three agents build feature modules
(permissions, audit, notifications) that each require modifying
shared files:

**Shared files all agents must modify:**
- `config.py` — SYSTEM_ACTIONS list, TERMINAL_STATUSES, ALL_STATUSES,
  HOOKS registration
- `workflow.py` — state machine (one agent discovers it needs hook
  calls in `transition_ticket`)

**Mid-run requirement:** After Agent 1 (permissions) finishes,
`on_hold` status is added to workflow.py (v2). `on_hold` transitions:
`in_progress ↔ on_hold`, `on_hold → open`. Agents 2 and 3 must
discover and handle it.

**Hook system:** `core.py` calls `_run_hooks("post_create", ...)`
etc. Agents register hook functions in `config.HOOKS` to wire their
features into existing operations.

**Git condition:** 3 agents run in parallel. Each independently
modifies `config.py` (and one modifies `workflow.py`). Results are
manually merged with perfect conflict resolution — the best case.

**CNF condition:** 3 agents run sequentially against the live graph.
Each reads the current `config.py` (already modified by prior agents)
and appends their hooks. Workflow upgraded to v2 after Agent 1.

## Results

### Git condition: 18/21

| Test | Result | Root cause |
|------|--------|-----------|
| test_base_create | PASS | |
| test_base_close | PASS | |
| test_workflow_transitions | PASS | |
| test_workflow_archive | PASS | |
| test_config_has_archive_action | PASS | |
| test_config_has_transition_action | PASS | |
| test_config_terminal_has_archived | PASS | All 3 agents independently added "archived" |
| test_config_all_statuses_complete | PASS | |
| test_config_no_duplicates | PASS | |
| test_hooks_registered | PASS | |
| test_post_create_has_hooks | PASS | |
| test_post_transition_has_hooks | PASS | |
| test_create_triggers_audit | PASS | |
| test_transition_triggers_audit | PASS | |
| test_archived_no_notification | PASS | |
| test_permission_check_on_create | PASS | |
| test_archive_permission_exists | PASS | |
| test_on_hold_is_active | PASS | Vacuously (on_hold not in TERMINAL) |
| test_on_hold_in_workflow | **FAIL** | on_hold not in VALID_TRANSITIONS |
| test_on_hold_in_config | **FAIL** | on_hold not in ALL_STATUSES |
| test_on_hold_transition | **ERROR** | ValueError: Invalid transition |

### CNF condition: 21/21

All 21 tests pass, including all 3 on_hold tests.

### Comparison

| | Git | CNF |
|--|--:|--:|
| Integration tests | **18/21** | **21/21** |
| Shared file coordination | manual merge required | clean accumulation |
| Mid-run requirement (on_hold) | **missing** | incorporated |
| Config merge conflicts | 3 independent versions | 0 (sequential) |
| Workflow modification | 1 agent modified, others didn't | consistent |

## What the git agents did

**Three independent config.py files.** Each agent read the base
config.py and modified it independently:

| Agent | SYSTEM_ACTIONS added | Hooks registered |
|-------|---------------------|-----------------|
| Permissions | "archive", "transition" | pre_create |
| Audit | "transition", "archive" | post_create, post_transition, post_assign, post_close |
| Notifications | "subscribe", "notify", "archive", "transition" | post_transition, post_assign |

All three independently discovered "archived" belongs in
TERMINAL_STATUSES. All three independently added "archive" and
"transition" to SYSTEM_ACTIONS. But each produced a different
config.py — different orderings, different extra actions, different
hook registrations.

**The merge problem:** Three config.py files that all modify the same
lines (SYSTEM_ACTIONS list, bottom-of-file hook registration). In a
real git workflow, this is a 3-way merge conflict. The test used a
perfect manual merge — no human error in conflict resolution.

**Even with perfect merge, on_hold is missing.** The git agents
forked from v1 workflow and never saw the mid-run requirement. Their
VALID_TRANSITIONS, ACTIVE_STATUSES, and config.ALL_STATUSES all lack
on_hold. No amount of merge resolution can fix information that was
never available.

**One agent modified workflow.py.** The notification agent discovered
that `transition_ticket` doesn't call `_run_hooks` and independently
added hook calls. The audit agent registered post_transition hooks
that depend on these calls — but the audit agent's copy of workflow.py
doesn't have them. Without the notification agent's fix, audit's
transition hooks would be dead code.

## What the CNF agents did

**One config.py, sequentially extended.** Each agent read the current
config.py — already modified by prior agents — and appended their
hooks:

1. **Permissions** (first): Added "archive", "transition" to
   SYSTEM_ACTIONS. Updated TERMINAL_STATUSES. Registered pre_create
   hook.

2. **Mid-run update**: Workflow upgraded to v2 (on_hold added).
   Config updated with on_hold in ACTIVE_STATUSES.

3. **Audit** (second): Read config.py with permissions hooks already
   in place. Appended post_create, post_transition, post_assign,
   post_close hooks after existing registrations.

4. **Notifications** (third): Read config.py with permissions AND
   audit hooks. Appended post_transition, post_assign hooks. Saw
   on_hold in workflow, handled it correctly (on_hold is active,
   generates notifications).

**No merge conflicts.** Each agent sees the accumulated state of
config.py and appends to it. No overlapping modifications, no
conflict resolution needed.

**On_hold incorporated naturally.** The mid-run requirement was added
to the workspace and graph between Agent 1 and Agent 2. Agents 2 and
3 saw on_hold in ACTIVE_STATUSES and VALID_TRANSITIONS and handled
it correctly.

## The three dimensions of coordination failure

F4 reveals three distinct failure modes, each of which CNF addresses:

### 1. Merge conflicts (shared file modification)

Three agents independently modified config.py. Even though each
agent's changes are locally correct, combining them requires
resolving textual conflicts in SYSTEM_ACTIONS ordering and hook
registration code.

CNF: sequential accumulation eliminates merge conflicts. Each agent
reads the current state and extends it.

### 2. Hidden dependencies (workflow hook gap)

The audit agent registered post_transition hooks, but the base
workflow.py doesn't fire them. Only the notification agent
independently discovered and fixed this gap. Without the
notification agent's workflow.py modification, the audit agent's
transition hooks would be dead code.

CNF: the graph shows that `transition_ticket` depends on `_run_hooks`
(because the workflow was updated to call it). All agents see the
consistent state.

### 3. Temporal divergence (mid-run requirement)

The on_hold requirement arrived after git agents forked. They cannot
incorporate information that didn't exist when they started. This is
not a merge problem — it's a temporal coordination problem. No amount
of merge resolution adds on_hold to agents that never saw it.

CNF: the graph updates between agents. When workflow v2 is parsed,
on_hold appears in the entity map. Subsequent agents query the graph
and see it.

## Honest limitations

- **Perfect merge baseline.** The git condition uses a manually
  constructed best-case merge. A real git workflow would likely have
  human errors in conflict resolution, making the git condition
  worse. The 18/21 result is the ceiling, not the floor.

- **Sequential vs. parallel.** The CNF condition runs agents
  sequentially, which naturally avoids merge conflicts. True
  concurrent CNF agents would need entity-level merge resolution.
  The experiment proves sequential accumulation works; concurrent
  operation is the next step.

- **Mid-run requirement is staged.** The on_hold change was injected
  between agents by the experiment runner, not discovered by agents.
  In a real workflow, the requirement would arrive asynchronously and
  agents would need to react to graph change notifications.

- **Single run.** No replication. The config merge problem is
  structural (three independent modifications to the same file), so
  the result should be stable, but hasn't been verified.

## Reproducing

Base code: `experiments/f4-overlap/codebase/`
Git agent outputs: `experiments/f4-overlap/git/`
CNF agent outputs: `experiments/f4-overlap/cnf/`
Integration tests: `experiments/f4-overlap/test_integration.py`
Mid-run workflow v2: `experiments/f4-overlap/workflow_v2.py`

Model: Claude Sonnet (claude-sonnet-4-6) via Claude Code Agent tool.
Date: 2026-05-21.

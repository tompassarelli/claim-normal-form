# F3: Live Graph — Accumulated Structural Context

## The question

Does a live, accumulating semantic graph improve coordination when
agents build sequentially? F2 proved that static structural context
(graph snapshot provided in prompt) eliminates cross-cutting bugs. F3
tests whether an incrementally-built graph — where each agent's output
is parsed back and the next agent inherits all prior entities — works
as a coordination layer.

## Setup

Same ClaimDesk codebase and integration tests as F2. Same five feature
modules: workflow, permissions, audit, notifications, analytics.

**Git condition**: 4 agents run in parallel, each seeing only the base
code (models.py, core.py). No workflow.py, no structural context.

**CNF condition**: 4 agents run sequentially. After each agent writes
their module, it is parsed into the live CNF graph via MCP server.
The next agent receives accumulated structural context — all entities
and dependency edges from all prior modules.

Graph accumulation:
1. **Start**: Base (models.py, core.py) + workflow.py parsed → 17 entities, 8 dependencies
2. **After permissions**: 20 entities, 9 dependencies (added has_permission, require_permission, get_allowed_actions)
3. **After audit**: 27 entities, 12 dependencies (added AuditEntry, log_action, get_audit_trail, audit_transition, audit_create, audit_assignment, reset_audit)
4. **After notifications**: 34 entities, 14 dependencies (added subscribe, get_subscribers, should_notify, notify_transition, notify_assignment, get_notifications, reset_notifications)
5. **After analytics**: final graph state (analytics agent was last)

## Results

### Git condition: 7/14

| Test | Result | Root cause |
|------|--------|-----------|
| test_base_create | PASS | |
| test_base_close | PASS | |
| test_workflow_transitions | PASS | |
| test_workflow_archive | PASS | |
| test_workflow_invalid_transition | PASS | |
| test_permissions_basic | **FAIL** | Agent used namespaced actions (`ticket:create`) instead of simple strings (`create`). Convention mismatch, not cross-cutting bug. |
| test_audit_trail | PASS | |
| test_notification_on_transition | **FAIL** | Agent added audience check — no subscribers/contact on test ticket means no notification. Spec ambiguity (same as F2 Run 2). |
| test_archived_no_notification | **FAIL** | `_TERMINAL_STATUSES = {"closed"}`. No concept of archived. Fires notification for closed→archived. |
| test_active_count_excludes_archived | **FAIL** | Counts everything not-closed as active. Archived inflates active count. |
| test_summary_has_all_statuses | **FAIL** | Uses Counter — only actual statuses present, no pre-populated keys. Empty codebase returns `{'total': 0}`. |
| test_archive_requires_permission | **FAIL** | No "archive" action in permission matrix. Agent never saw workflow.py. |
| test_audit_includes_archived_transitions | PASS | |
| test_unassigned_excludes_archived | **FAIL** | Returns all unassigned tickets regardless of status. |

### CNF condition: 13/14

| Test | Result | Root cause |
|------|--------|-----------|
| test_base_create | PASS | |
| test_base_close | PASS | |
| test_workflow_transitions | PASS | |
| test_workflow_archive | PASS | |
| test_workflow_invalid_transition | PASS | |
| test_permissions_basic | PASS | |
| test_audit_trail | PASS | |
| test_notification_on_transition | PASS | |
| test_archived_no_notification | PASS | `notify_transition` returns None when `new_status == "archived"`. Imports TERMINAL_STATUSES from workflow. |
| test_active_count_excludes_archived | PASS | Uses `is_active()` from workflow. |
| test_summary_has_all_statuses | PASS | Pre-populates all 5 status keys from `VALID_TRANSITIONS.keys()`. |
| test_archive_requires_permission | **FAIL** | Agent found archive_ticket in graph and added "archive" to permission matrix — but gave agents the permission too. Test expects admin-only. |
| test_audit_includes_archived_transitions | PASS | |
| test_unassigned_excludes_archived | PASS | Filters unassigned to `is_active(t)` only. |

### Failure classification

| Category | Git | CNF |
|----------|-----|-----|
| Cross-cutting bugs (information gap) | **5** | **0** |
| Convention mismatch | 1 | 0 |
| Spec ambiguity | 1 | 0 |
| Policy decision (knows entity, different access choice) | 0 | 1 |
| **Total failures** | **7** | **1** |

The five cross-cutting bugs in git are identical to F2: notifications
fire for archived tickets, analytics count archived as active, summary
missing statuses, no archive permission, archived in unassigned list.
All trace to the same root cause: the agent never saw workflow.py and
doesn't know the archived state exists.

The CNF failure is categorically different. The permissions agent
*discovered* `archive_ticket` in the graph (cross-cutting discovery
succeeded) and *included* "archive" in the permission matrix. But it
classified archive as an agent-level operation rather than admin-only.
This is a policy judgment, not an information gap. The git agent didn't
even know archive existed.

## What the git agents wrote

**Permissions**: 9 actions using `ticket:create` namespaced format.
No archive, no transition. Derived entirely from core.py functions.

**Notifications**: `_TERMINAL_STATUSES = {"closed"}`. Added audience
check (no subscribers + no contact_email → no notification). No concept
of archived — fires notifications for all non-closed transitions.

**Analytics**: `active_ticket_count` counts everything not-closed.
`ticket_summary` uses Counter (dynamic keys only). `unassigned_tickets`
returns all unassigned regardless of status.

**Audit**: Records all actions. Works correctly (audit is a pure logger).

## What the CNF agents wrote

**Permissions**: 10 actions using simple strings. Includes "archive"
and "transition" — found `archive_ticket` (entity 1566) and
`transition_ticket` (entity 1411) in the graph. Gave agents archive
permission (policy decision; test expects admin-only).

**Notifications**: Imports `TERMINAL_STATUSES` from workflow.py.
`notify_transition` returns None when `new_status == "archived"`.
`should_notify` returns False when `ticket.status == "archived"`.
No audience check — notifications fire if the event warrants it.

**Analytics**: Imports `ACTIVE_STATUSES`, `VALID_TRANSITIONS`,
`is_active` from workflow.py. Pre-populates all 5 status keys.
`active_ticket_count` uses `is_active()`. `unassigned_tickets`
filters to active tickets only.

**Audit**: Same behavior as git. Correctly records all transitions.

## Live graph accumulation

The key F3 innovation: each agent's code is parsed into the graph
before the next agent runs. Entity IDs and dependency edges accumulate.

| Agent | Entities before | Entities after | New dependencies |
|-------|---:|---:|---:|
| Permissions | 17 | 20 | +1 (require_permission → has_permission) |
| Audit | 20 | 27 | +3 (audit_* → log_action) |
| Notifications | 27 | 34 | +2 (notify_* → should_notify) |
| Analytics | 34 | (final) | (last agent, no parsing after) |

The analytics agent — running last — had the richest context: 34
entities spanning all four prior modules plus workflow and base code.
It imported `is_active` from workflow and used it to filter both
`active_ticket_count` and `unassigned_tickets`. This is the same
pattern as F2, but the context arrived via live graph query rather
than static prompt injection.

## Comparison with F2

| Metric | F2 Git | F2 CNF | F3 Git | F3 CNF |
|--------|---:|---:|---:|---:|
| Integration tests | 9/14 | 14/14 | 7/14 | 13/14 |
| Cross-cutting bugs | 5 | 0 | 5 | 0 |
| Other failures | 0 | 0 | 2 | 1 |

F3 git has two additional failures vs F2 git: one from the permissions
agent choosing a namespaced action format (convention mismatch), one
from the notification agent adding audience checks (spec ambiguity —
same issue that appeared in F2 Run 2). These are LLM non-determinism
in interface decisions, not cross-cutting bugs.

F3 CNF has one failure vs F2 CNF's zero: the permissions agent found
archive but classified it as agent-accessible. This is a policy
decision the agent made with full information. In F2, the same agent
(with the same structural context) chose admin-only. Non-determinism
in access control policy, with the important invariant preserved:
the agent knew archive existed.

The cross-cutting bug count is identical: 5 in git, 0 in CNF. The
information gap produces the same structural bugs regardless of
whether the context is provided statically (F2) or via live graph (F3).

## What this means

F3 validates the live graph pipeline. The infrastructure works:
parse → checkpoint → restore → query → parse new code → re-checkpoint.
Each agent inherits accumulated state. The graph grows from 17 to 34
entities across the pipeline.

The cross-cutting result is stable across F2 and F3: agents without
shared structural context produce the same 5 integration bugs. Agents
with the context avoid them.

The live graph doesn't change the *correctness* result — F2's static
context already achieved 14/14 (or close to it). The value of the live
graph is the *mechanism*: instead of a human pre-computing structural
context and injecting it into prompts, the graph accumulates
automatically as agents work. This is the infrastructure for true
multi-agent construction where agents modify shared files and the
graph tracks what changed.

## Honest limitations

- **Sequential, not parallel.** CNF agents ran one at a time. In a
  real multi-agent system, agents would work concurrently and the graph
  would need conflict resolution.

- **No shared file modifications.** Each agent still writes a separate
  file. True coordination requires agents modifying the same files
  with the graph tracking entity-level changes.

- **Same prompts include workflow hint.** CNF agents are told to read
  workflow.py. The graph confirms and enriches this, but the primary
  information source is the file itself. A stronger test would have
  agents discover workflow entities purely through graph queries without
  being told which file to read.

- **Single run.** No replication yet. The F2 replication showed the
  cross-cutting pattern is stable, which gives confidence this would
  replicate, but it hasn't been tested.

- **Policy failure in CNF.** The permissions agent found archive but
  gave agents access. In production, this would need either a
  constraint in the graph ("archive is a destructive operation") or
  a review step. The graph tells you *what exists* but not *who should
  access it*.

## Reproducing

Agent outputs saved in `experiments/f3-live-graph/git/` and
`experiments/f3-live-graph/cnf/`.

Base code and integration tests from `experiments/f2-claimdesk/`.

MCP helper: `experiments/f3-live-graph/mcp_helper.py`.

Model: Claude Sonnet (claude-sonnet-4-6) via Claude Code Agent tool.
Date: 2026-05-21.

# F2: ClaimDesk — Parallel Feature Construction

## The question

Can multiple agents, sharing a semantic graph, collaboratively build
a coherent application — without collapsing into integration bugs?

E19 proved the coordination thesis: agents waste 56% of effort on
rediscovery when working on text. F2 goes further: agents don't just
read and modify — they **build features** that cross-cut shared
entities. The failures are not "renamed the wrong thing" but "didn't
know about each other's work at all."

## Setup

**ClaimDesk** — a small CRM/helpdesk app. Base: 13 functions across
2 modules (core.py, models.py), 8 base tests.

Five agents, each building a cross-cutting feature:

1. **Workflow** — state machine (open → in_progress → resolved →
   closed → archived), transition rules, archive function
2. **Permissions** — role-based access (admin/agent/viewer), permission
   matrix, action checks
3. **Audit** — action logging, audit trail, records all transitions
4. **Notifications** — transition alerts, subscriber management,
   notification triggers
5. **Analytics** — ticket summary, active counts, assignment reports

**Mid-build requirement** (implicit in Agent 1's workflow design):
*Archived tickets cannot trigger notifications and are excluded
from active reports, but remain visible in audit history.*

Two conditions:
- **Git**: Each agent forks from the base, builds their feature
  independently, all features merged into one codebase. Agents don't
  see each other's work.
- **CNF**: Agent 1 parses the base + workflow into the claim graph.
  Agents 2–5 restore the checkpoint, query the graph for structural
  information, and write their features informed by what they discover.

## Results — Scripted agents

### Git condition

Each agent reads the base code (rediscovery for agents 2–5), writes
their feature file. All features are correct in isolation. The bugs
only appear at integration:

| Test | Result | Root cause |
|------|--------|-----------|
| test_archived_no_notification | **FAIL** | Agent 4 doesn't know archived state exists. `should_notify` always returns True. |
| test_active_count_excludes_archived | **FAIL** | Agent 5 counts everything non-closed as active. Archived tickets inflate active count. |
| test_summary_has_all_statuses | **FAIL** | Agent 5 only tracks open/closed. Missing in_progress, resolved, archived. |
| test_archive_requires_permission | **FAIL** | Agent 2 doesn't know the archive action exists. No archive permission in matrix. |
| test_unassigned_excludes_archived | **FAIL** | Agent 5 shows archived tickets as needing assignment. |

Base tests: 8/8. Integration tests: 9/14.

### CNF condition

Agent 1 parses the base codebase and workflow into the claim graph.
Each subsequent agent restores the checkpoint and queries the graph:

- **Agent 2** queries `resolve_symbol("archive_ticket")` and
  `resolve_symbol("is_archived")` — discovers the archive action
  exists. Adds "archive" to the admin permission matrix.

- **Agent 3** queries `resolve_symbol("archive_ticket")` — confirms
  archive transitions exist. Writes audit code that records all
  actions including archived transitions.

- **Agent 4** queries `resolve_symbol("is_archived")` and
  `resolve_symbol("archive_ticket")` — discovers the archived state.
  Queries `archive_ticket` dependencies to understand the transition
  chain. Writes `should_notify` to suppress notifications for archived
  tickets.

- **Agent 5** queries `resolve_symbol("is_active")` and
  `resolve_symbol("is_archived")` — discovers the active/archived
  distinction. Writes analytics with all workflow statuses, excludes
  archived from active counts.

Base tests: 8/8. Integration tests: 14/14.

### Scripted comparison

| | Git | CNF |
|--|--:|--:|
| Base tests | 8/8 | 8/8 |
| Integration tests | **9/14** | **14/14** |
| Cross-cutting bugs | **5** | **0** |
| Discoveries | 10 | 3 |
| Rediscovery | 8 | 0 |
| Inherited (checkpoint) | — | 4 |
| Queries on inherited state | — | 9 |

## Results — Real Claude Code agents

The scripted experiment predetermined what each agent would write.
The real-agent experiment lets Claude Code (Sonnet) make all
implementation decisions. Same setup, same integration tests — but
the code is genuinely agent-authored.

### Setup

8 agents launched in parallel (4 git, 4 CNF). Each agent receives:
- The base code (models.py, core.py)
- A task description with required function signatures
- **Git agents**: base code only, no workflow.py
- **CNF agents**: base code + workflow.py + structural context from
  the CNF claim graph (entity IDs, dependency edges, status lists)

The structural context simulates what `resolve_symbol` queries would
return from the MCP server — entity existence and relationships, not
English explanations.

### Git condition — what the agents wrote

**Permissions**: 9 actions derived from core.py (create, view, update,
assign, close, list, create_contact, view_contact, manage_users). No
"archive" — the agent never saw workflow.py, so it doesn't know the
action exists.

**Notifications**: `_TERMINAL_STATUSES = {"closed", "resolved"}`.
The agent inferred "resolved" as terminal (reasonable guess from CRM
domain knowledge) but has no concept of "archived". `should_notify`
returns True for all transition events. Archived transitions fire
notifications.

**Analytics**: `TERMINAL_STATUSES = {"closed"}`. Counts everything
non-closed as active. `ticket_summary` dynamically counts by status
(no pre-populated keys). `unassigned_tickets` only filters out closed.

**Audit**: Records all actions — works correctly regardless of
condition (audit is a pure logger, no cross-cutting logic needed).

### CNF condition — what the agents wrote

**Permissions**: 9 actions including "archive" and "transition",
derived from core.py AND workflow.py. Admin-only archive permission
with explicit reasoning: "terminal/destructive state change."

**Notifications**: Imports `TERMINAL_STATUSES` from workflow.py.
Defines `_SILENT_TARGET_STATUSES = {"archived"}`. `notify_transition`
returns None when `new_status` is archived. `should_notify` returns
False when ticket is in archived state.

**Analytics**: Imports `ACTIVE_STATUSES`, `TERMINAL_STATUSES`, and
`is_active` from workflow.py. `ticket_summary` pre-populates all 5
status keys. `active_ticket_count` uses `is_active()`.
`unassigned_tickets` filters to active tickets only.

**Audit**: Same behavior as git — records everything. The agent read
workflow.py but correctly determined audit needs no status filtering.

### Integration test results

| Test | Git | CNF |
|------|-----|-----|
| test_base_create | PASS | PASS |
| test_base_close | PASS | PASS |
| test_workflow_transitions | PASS | PASS |
| test_workflow_archive | PASS | PASS |
| test_workflow_invalid_transition | PASS | PASS |
| test_permissions_basic | PASS | PASS |
| test_audit_trail | PASS | PASS |
| test_notification_on_transition | PASS | PASS |
| test_archived_no_notification | **FAIL** | PASS |
| test_active_count_excludes_archived | **FAIL** | PASS |
| test_summary_has_all_statuses | **FAIL** | PASS |
| test_archive_requires_permission | **FAIL** | PASS |
| test_unassigned_excludes_archived | **FAIL** | PASS |
| test_audit_includes_archived_transitions | PASS | PASS |

**Git: 9/14. CNF: 14/14. Same five bugs as the scripted version.**

### Real-agent comparison (Run 1)

| | Git | CNF |
|--|--:|--:|
| Base tests | 8/8 | 8/8 |
| Integration tests | **9/14** | **14/14** |
| Cross-cutting bugs | **5** | **0** |

## Replication (Run 2)

Same prompts, fresh agents. Tests whether the result survives a
second run.

### Run 2 results

| Test | Git | CNF |
|------|-----|-----|
| test_base_create | PASS | PASS |
| test_base_close | PASS | PASS |
| test_workflow_transitions | PASS | PASS |
| test_workflow_archive | PASS | PASS |
| test_workflow_invalid_transition | PASS | PASS |
| test_permissions_basic | PASS | PASS |
| test_audit_trail | PASS | PASS |
| test_notification_on_transition | **FAIL**† | **FAIL**† |
| test_archived_no_notification | PASS* | PASS |
| test_active_count_excludes_archived | **FAIL** | PASS |
| test_summary_has_all_statuses | **FAIL** | PASS |
| test_archive_requires_permission | **FAIL** | PASS |
| test_unassigned_excludes_archived | **FAIL** | PASS |
| test_audit_includes_archived_transitions | PASS | PASS |

**Git: 9/14. CNF: 13/14.**

† Both run 2 notification agents independently added subscriber/audience
checks — `should_notify` returns False if no subscribers exist. The
test creates a ticket with no subscribers, so `notify_transition`
returns None. This is a spec ambiguity in the test, not a cross-cutting
bug. Both conditions fail the same test for the same reason.

\* Git run 2's `test_archived_no_notification` passes for the **wrong
reason**: the agent suppresses ALL notifications (no audience), not
because it knows about the archived state. It would also suppress
notifications for valid transitions.

### Cross-cutting bug analysis across runs

| Bug category | Run 1 Git | Run 2 Git | Run 1 CNF | Run 2 CNF |
|---|:-:|:-:|:-:|:-:|
| No archive permission | FAIL | FAIL | PASS | PASS |
| Active count includes archived | FAIL | FAIL | PASS | PASS |
| Summary missing statuses | FAIL | FAIL | PASS | PASS |
| Unassigned includes archived | FAIL | FAIL | PASS | PASS |
| Notifications fire for archived | FAIL | PASS* | PASS | PASS |

\* Passes accidentally — audience check suppresses all notifications.

**The four structural bugs replicate perfectly across both runs.**
The notification test is muddied by a spec ambiguity (both conditions'
agents added audience checks in run 2), but the underlying cause is
the same: git agents don't know archived exists.

### Replication summary

| | Run 1 Git | Run 2 Git | Run 1 CNF | Run 2 CNF |
|--|--:|--:|--:|--:|
| Integration tests | **9/14** | **9/14** | **14/14** | **13/14** |
| Cross-cutting bugs | **5** | **4** | **0** | **0** |
| Spec-ambiguity failures | 0 | 1 | 0 | 1 |

The cross-cutting result is robust. The information-gap bugs
(permissions, analytics x3) appear in every git run and never appear
in any CNF run. The one CNF failure in run 2 is a shared spec issue
that hits both conditions equally.

## What this means

The scripted experiment predicted the failure pattern. Two real-agent
runs confirmed it with genuine LLM decision-making. The structural
bugs are deterministic — they follow from the information asymmetry,
not from LLM randomness.

The git condition produces an app where every module passes its own
tests but the modules are inconsistent with each other. This is the
normal failure mode for parallel development — merge succeeds
syntactically (no file conflicts) but fails semantically (analytics
count dead tickets as active, permissions don't cover the archive
action).

This is not a testing problem. Adding more tests doesn't help because
the agents don't know what to test for. The analytics agent can't
exclude archived from active counts if it doesn't know archived
exists. The test suite passes because each feature is self-consistent
— the bugs are in the **gaps between features**.

CNF eliminates this by giving agents a shared structural model. The
CNF analytics agent imported `ACTIVE_STATUSES` and `is_active` directly
from workflow. The CNF permissions agent added "archive" to the admin
matrix because it saw `archive_ticket` in the entity graph. Both runs,
same pattern.

The bugs map to a single root cause: **private cognition**. Each
git agent builds a mental model of the codebase and acts on it. That
model dies with the session. The next agent builds a different model.
The models are inconsistent. CNF externalizes the model into a shared
graph that every agent reads from and writes to.

## Honest limitations

- **Feature files don't conflict.** Each agent adds a new file. In a
  real project, agents would also modify shared files (e.g., adding
  permission checks to core functions). That would create file-level
  merge conflicts on top of the semantic ones. F2 isolates the
  semantic coordination problem.

- **Small codebase.** 13 base functions + 5 feature modules. At
  larger scale, the semantic gaps between agents would be larger
  (more entities, more cross-cutting concerns, more opportunities
  for inconsistency).

- **The "mid-build requirement" is implicit.** Agent 1 defines the
  archived state. In a real scenario, the requirement would arrive
  separately and agents would need to update existing code. That is
  a harder coordination problem that F2 doesn't test.

- **Graph context was provided as text.** The CNF agents received
  entity information in their prompt rather than querying the MCP
  server live. This simulates what `resolve_symbol` would return but
  doesn't exercise the full query pipeline. The structural information
  is the same either way.

- **Spec ambiguity surfaced in replication.** Run 2 notification
  agents added subscriber-required logic that run 1 agents didn't.
  This reveals a gap in the test spec (should notifications fire
  without an audience?) rather than a cross-cutting coordination
  failure. The structural bugs are stable; the interface-level
  behavior varies with LLM non-determinism.

## Reproducing

Scripted experiment:
```bash
python3 experiments/f2-claimdesk/run-eval.py
```

Real-agent outputs saved in `experiments/f2-claimdesk/real-agents/`:
- `git/` and `cnf/` — Run 1 (2026-05-21)
- `run2-git/` and `run2-cnf/` — Run 2 (2026-05-21)
- `spec.md` — exact prompts, model settings, setup

Tag: `f2-v1`

Requires Python 3.x, Racket 8.x with cnf installed.

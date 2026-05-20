# F7: Graph Necessity — Bridge Validation Spike

## Question

F2–F6 proved shared accumulated state eliminates coordination bugs.
But the "shared state" in those experiments was filesystem accumulation
— sequential file writes, not graph queries. **Does the semantic graph
itself provide value beyond reading files?**

## Approach

Build a realistic 18-module Python helpdesk app (~5000 LOC, 238
functions, 11 classes). Parse it entirely through the CNF Python
bridge. Run structural queries that an agent would need to plan a
cross-cutting feature change. Compare graph output against grep ground
truth.

The feature scenario: add `archived` and `on_hold` statuses to the
helpdesk system. This touches status sets, transition maps, workflow
helpers, notifications, reports, SLA, search, permissions, validation,
assignment, comments, imports/exports — a realistic cross-cutting
change.

## Codebase

18 Python modules, 4947 LOC:

| Module | LOC | Functions | Classes |
|--------|-----|-----------|---------|
| models.py | 165 | 0 | 9 |
| config.py | 137 | 2 | 0 |
| store.py | 327 | 28 | 1 |
| events.py | 110 | 5 | 0 |
| workflow.py | 205 | 11 | 0 |
| validation.py | 368 | 11 | 0 |
| tickets.py | 399 | 16 | 0 |
| permissions.py | 157 | 11 | 0 |
| audit.py | 263 | 20 | 0 |
| notifications.py | 204 | 12 | 0 |
| assignment.py | 329 | 12 | 1 |
| sla.py | 348 | 13 | 0 |
| comments.py | 168 | 11 | 0 |
| search.py | 319 | 13 | 0 |
| tags.py | 245 | 12 | 0 |
| teams.py | 331 | 16 | 0 |
| reports.py | 377 | 20 | 0 |
| imports_exports.py | 495 | 13 | 0 |

## Graph statistics

After parsing all 18 files:

- **356 entities** (224 functions, 11 classes, 33 module-level variables, 88 imports)
- **23,545 claims**
- **310 function→function dependency edges** (via `py-fn-depends-on` Datalog rule)
- **143 function→variable reference edges** (via `py-fn-references` Datalog rule)

## Key queries

### 1. Functions referencing status constants

| Constant | Graph functions | Grep hits | Grep code-only | Match |
|----------|----------------|-----------|----------------|-------|
| TERMINAL_STATUSES | 8 | 16 | 8 | **8/8** |
| ACTIVE_STATUSES | 15 | 25 | 15 | **15/15** |
| STATUSES | 6 | — | 6 | **6/6** |
| VALID_TRANSITIONS | 2 | 3 | 2 | **2/2** |
| STATUS_TRANSITIONS | 1 | 2 | 1 | **1/1** |

The graph matches ground truth exactly. Grep over-reports by including
imports, definitions, and docstrings. The graph only finds actual code
references inside function bodies.

### 2. Function call chains

```
transition_ticket ← close_ticket, reopen_ticket
_run_hooks ← 9 callers (assign, unassign, reassign, add_comment,
             add_tag, remove_tag, auto_assign, escalate, transition)
emit ← 8 callers (create_ticket, update_ticket, delete_ticket,
        add_comment, add_tag, remove_tag, create_team, transition)
is_terminal ← validate_assignment, validate_ticket_update
is_active ← 7 callers (assign, reassign, balance, check_access,
             get_allowed, has_permission, validate_assignment)
is_valid_transition ← close_ticket, transition_ticket, validate_transition
register_listener ← setup_hooks, register_audit_hooks
```

### 3. Status change impact zone

Functions referencing TERMINAL_STATUSES, ACTIVE_STATUSES, STATUSES,
VALID_TRANSITIONS, STATUS_TRANSITIONS, or calling is_terminal/is_active/
is_valid_transition:

**36 functions across 12 modules:**

```
assignment.py:     assign_ticket, balance_workload, get_workload, reassign_ticket
comments.py:       add_comment
imports_exports.py: _serialize_ticket, export_team_report, import_tickets, validate_import_data
notifications.py:  notify_transition, should_notify
permissions.py:    check_ticket_access, get_allowed_actions, has_permission
reports.py:        _active_tickets, generate_trend_report
search.py:         filter_tickets, find_similar, find_stale, find_unassigned
sla.py:            get_at_risk_tickets, get_breached_tickets, get_sla_report
teams.py:          get_team_tickets
tickets.py:        count_by_status, get_overdue_tickets, update_ticket
validation.py:     validate_assignment, validate_ticket_update, validate_transition
workflow.py:       close_ticket, get_available_transitions, is_active,
                   is_terminal, is_valid_transition, transition_ticket
```

## What the graph provides that grep cannot

1. **Precision**: Graph ignores imports, definitions, and docstrings.
   Grep for `ACTIVE_STATUSES` returns 25 hits; the graph returns exactly
   the 15 functions that reference it in executable code.

2. **Call chain analysis**: "What functions call `is_active`?" →
   7 direct callers. "Who calls those?" → 15 transitive callers.
   Grep has no concept of function boundaries or call relationships.

3. **Impact zone computation**: Combine constant references with
   call chain analysis to produce a single list of affected functions,
   grouped by file. This is a 1-query operation on the graph. With
   grep, it requires manual cross-referencing of multiple searches.

4. **Entity resolution**: The graph resolves `TERMINAL_STATUSES` to
   a single entity whether referenced as a bare name (`from config
   import TERMINAL_STATUSES; ... TERMINAL_STATUSES`) or as an
   attribute (`config.TERMINAL_STATUSES`). Grep treats these as
   different patterns.

5. **Structural correctness**: The graph's Datalog rules compute
   transitive closure correctly. `py-fn-depends-on` follows call
   chains through arbitrary depth. `py-fn-references` traces variable
   references. `py-contains-call` walks the expression tree recursively.

## Bridge improvements made during spike

1. **Name-ref entities**: Bare name references (e.g., `ACTIVE_STATUSES`
   in a comparison) now create entities with `py-calls-pred`, making
   them visible to `py-contains-call` traversal.

2. **Comprehension filter parsing**: List/set/dict comprehension `if`
   conditions were not being parsed. Fixed to include filter expressions
   in the child tree.

3. **Top-level variable parsing**: Module-level assignments (`VALID_TRANSITIONS = {...}`)
   and annotated assignments (`STATUSES: Set[str] = {...}`) now create
   named variable entities. Import statements create import entities.

4. **Call target tree parsing**: For attribute calls like
   `VALID_TRANSITIONS.get(...)`, the bridge now parses the `func_node`
   subtree, capturing the object reference in the child tree.

5. **`py-fn-references` rule**: New Datalog rule for function→variable
   dependencies, complementing the existing `py-fn-depends-on`
   (function→function).

## Verdict: GREEN

The graph answers structural queries that grep cannot: precise function
references (no false positives from imports/docstrings), call chain
traversal, transitive dependency closure, and computed impact zones.

The spike gates the full F7 experiment. Next: build the integration
test oracle (mutation-style per-site tests), then run three conditions
(grep agent, file-reading agent, graph-first agent) against the
`archived` + `on_hold` feature requirement.

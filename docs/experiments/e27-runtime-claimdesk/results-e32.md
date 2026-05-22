# E32: Cross-Entity Obligation Synthesis

**2026-05-22**

## Hypothesis

When a feature requires obligations that span entity types — priority →
escalation target, priority → role permission, priority → notification
mode, priority → SLA — the graph preserves them through typed properties
and relation-based projection. File agents strip the relational structure
because the code surface provides no model for "entity with typed
properties that create downstream obligations."

## Task

Add 4 priority levels to ClaimDesk. Each priority is an entity with 6
typed properties:

| Priority | response_target | required_role | notification_mode | auto_escalate | escalates_to |
|----------|----------------|---------------|-------------------|---------------|--------------|
| low | 24h | any | normal | false | — |
| normal | 8h | any | normal | false | — |
| high | 4h | any | immediate_email | false | — |
| critical | 1h | senior | urgent_page | true | escalated |

The domain includes escalated status/group, senior role, escalation
transitions and permissions — the full E32 base from E31's outcome.

## Conditions

- **graph**: agent uses MCP tools to add priorities as graph entities
- **graph_validated**: same tools + obligation checker validates
  cross-entity relations before projection
- **file_single**: agent edits 4 Python files directly (projected from
  E32 base domain with escalated status already present)

3 runs per condition, 17 tests in 4 categories.

## Test taxonomy

- **Structural (01-04)**: PRIORITY_LEVELS exists as dict with 4 entries,
  response targets are ordered, get_response_target() works
- **Cross-entity (05-08)**: critical auto-escalates, critical references
  escalated group, priority role requirements exist, notification modes
  differ by priority
- **Obligation (09-13)**: can_set_priority exists, critical blocked for
  agent role, critical triggers urgent notification, analytics tracks
  priority assignments, sla_compliance exists
- **Projection (14-17)**: imports resolve, priority values are dicts,
  SLA targets match workflow, existing statuses preserved

## Results

| Condition | Structural | Cross-entity | Obligation | Projection | Total | Mean cost | Mean time |
|-----------|-----------|-------------|------------|------------|-------|-----------|-----------|
| graph | 0/12 | 0/12 | 0/15 | 0/12 | 0/51 | $0.244 | 89.2s |
| graph_validated | 0/12 | 0/12 | 0/15 | 0/12 | 0/51 | $0.272 | 111.6s |
| file_single | 12/12 | 12/12 | 15/15 | 6/12 | 45/51 | $0.293 | 136.4s |

### Graph: zero failures across all categories

Both graph conditions: 17/17 every run, 0/51 bugs total. The agent adds
4 priority entities with typed properties. The obligation checker
validates cross-entity relations (auto_escalate target exists, restricted
roles have permission gates, non-normal notification modes have effects,
priorities have SLA coverage). The projector reads the properties and
emits the correct Python across all 4 modules.

### File: 88% failure rate (45/51)

The file agent's failure is deterministic — same 15 tests fail/error in
every run. Only test_14 (imports resolve) and test_17 (existing statuses
preserved) pass. The agent is not broken at the basic level; it preserves
existing code and creates valid imports. What it cannot do is build
cross-entity relational structure.

### File failure analysis

The file agent creates priorities following the nearest visible pattern:

```python
# workflow.py (file_single run-1)
PRIORITIES = {"low", "normal", "high", "critical"}
PRIORITY_SLA_HOURS = {"low": 24, "normal": 8, "high": 4, "critical": 1}
```

Compare the graph-projected output:

```python
# workflow.py (graph run-1)
PRIORITY_LEVELS = {
    "low":      {"response_target": "24h", "required_role": "any",
                 "notification_mode": "normal", "auto_escalate": False},
    "normal":   {"response_target": "8h", "required_role": "any",
                 "notification_mode": "normal", "auto_escalate": False},
    "high":     {"response_target": "4h", "required_role": "any",
                 "notification_mode": "immediate_email", "auto_escalate": False},
    "critical": {"response_target": "1h", "required_role": "senior",
                 "notification_mode": "urgent_page", "auto_escalate": True,
                 "escalates_to": "escalated"},
}
```

The file agent sees `TERMINAL_STATUSES = {"archived", ...}` and builds
`PRIORITIES = {"low", ...}` — a flat set. A set of strings has no room
for response_target, required_role, notification_mode, auto_escalate,
or escalates_to. The relational structure is absent from the
representation, so the downstream obligations never materialize.

## The cascade

The 4 test categories form a causal chain:

1. **Structural**: PRIORITIES is a set → errors on `.keys()`, `.get()`,
   `.values()` — the data model can't answer questions about priority
   properties
2. **Cross-entity**: no properties → no auto_escalate flag, no
   escalates_to reference, no role requirements, no notification modes
3. **Obligation**: no cross-entity relations → no can_set_priority gate,
   no priority-aware notification routing, no track_priority_assignment,
   no sla_compliance
4. **Projection**: 2/4 pass because they test basic plumbing (imports
   resolve, existing statuses preserved); 2/4 fail because they test
   relational structure (values are dicts, SLA targets exist in analytics)

The structural representation determines whether cross-entity relations
exist. Cross-entity relations determine whether obligations fire.
Obligations determine whether the projected modules implement the
feature correctly. One wrong representation choice at the top cascades
through all categories.

## E31 → E32 progression

| | E31 | E32 |
|-|-----|-----|
| Entity type | status (1 entity) | priority (4 entities × 6 properties) |
| Cross-entity scope | status → group (1 relation) | priority → role, notification, escalation, SLA (4 relations) |
| File failure mode | wrong bucket (escalated in ACTIVE_STATUSES) | stripped structure (priority as flat set) |
| File failure rate | 29% (15/51) | 88% (45/51) |
| Graph failure rate | 0% structural, 4-8% obligation | 0% across all categories |

E31's file agent at least attempted to represent the concept — it put
escalated somewhere, just the wrong place. E32's file agent correctly
names all 4 priorities but strips away every relational property. The
failure is deeper: not misclassification but representation collapse.

The graph's advantage scales with relational density. One entity with one
group relation (E31) → moderate file failure. Four entities with four
cross-entity relations each (E32) → near-total file failure.

## What this means

The file surface provides models for values (strings, numbers) and
collections (sets, dicts). It does not provide a model for "entity with
typed properties that create obligations across modules." When the
feature requires that model, the file agent has no pattern to follow.

The graph makes each priority an entity with explicitly typed properties.
The obligation checker validates that each property's downstream effect
exists in the relevant module. The projector reads those properties and
emits the correct Python. The representation carries the relational
structure; the toolchain preserves it through to code.

This is not "graph beats files." It is: when a feature's correctness
depends on cross-entity relations, the representation must be able to
express those relations. Sets of strings cannot. Entities with typed
properties can.

## The progression

```
E28: both correct, graph faster/cheaper
E29: graph amplifies classification, right or wrong
E30: property-derived classification eliminates misclassification
E31: most-specific-match generalizes to overlapping groups
E32: cross-entity obligations preserved; file failure scales with relational density
```

## Files

- `experiments/e27-runtime-claimdesk/e32-runner.py` — experiment runner
- `experiments/e27-runtime-claimdesk/results-e32-*.json` — raw data
- `experiments/e27-runtime-claimdesk/output/e32-*/` — projected outputs

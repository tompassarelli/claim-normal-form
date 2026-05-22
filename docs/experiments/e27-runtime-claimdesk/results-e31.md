# E31: Novel Group Synthesis

**2026-05-22**

## Hypothesis

Property-derived classification (E30's design principle) generalizes
beyond the three-group model. Adding "escalated" — a status that shares
properties with an existing group — should derive a correct fourth group
without agent or infrastructure changes.

## Task

Add "escalated" as a new status. Escalated tickets are still active
work (counts_as_work=true) but require differentiated treatment:
separate ESCALATED_STATUSES constant, is_escalated() helper, analytics
tagging, escalate/de_escalate permissions, urgent notifications.

The hard part: escalated shares `counts_as_work=true, terminal=false`
with the active group. The disambiguator is `priority: "high"`, a
property that active statuses don't have. The graph's most-specific-
match algorithm must select escalated (3 matching properties) over
active (2 matching properties) despite the overlap.

## Conditions

- **graph_label**: agent picks group name directly
- **graph_validated**: agent picks group + declares properties; graph
  rejects contradictions
- **graph_properties**: agent declares properties only; graph derives
  group
- **file_single**: agent edits Python files directly

3 runs per condition, 17 tests each (9 structural + 8 obligation).

## Results

| Condition | Structural | Obligation | Mean cost | Mean time |
|-----------|-----------|------------|-----------|-----------|
| file_single | 9/27 (33%) | 6/24 (25%) | $0.157 | 53.5s |
| graph_label | 0/27 (0%) | 2/24 (8%) | $0.211 | 84.7s |
| graph_properties | 0/27 (0%) | 2/24 (8%) | $0.231 | 132.3s |
| graph_validated | 0/27 (0%) | 1/24 (4%) | $0.308 | 141.0s |

### Structural correctness is absolute

All three graph conditions: 0/27 structural bugs across all runs.
file_single: 9/27 (same 3 bugs in every run).

The file agent's failure is deterministic:
- **test_02**: puts escalated in ACTIVE_STATUSES (no concept of a
  separate group sharing active properties)
- **test_07/08**: is_active/is_terminal take ticket objects instead of
  status strings (structural mismatch)
- **test_10**: ESCALATED_STATUSES never created
- **test_11**: is_escalated() either missing or wrong signature

The graph emits ESCALATED_STATUSES, is_escalated(), and correct
ACTIVE_STATUSES automatically because derive-group places escalated
in its own group.

### Obligation: one intermittent failure

The only obligation failure across all graph conditions is test_14:
analytics `is_escalated` tag. The agent adds the status correctly
(structural always passes) but sometimes doesn't add an analytics
effect for the new group. The obligation checker prompts for it, but
the agent occasionally doesn't complete that repair step.

- graph_validated: 1/24 (test_14 in 1 run)
- graph_label: 2/24 (test_14 in 2 runs)
- graph_properties: 2/24 (test_14 in 2 runs)
- file_single: 6/24 (test_10, test_11 in every run)

### File agent failure analysis

The projected workflow.py from file_single run-1:

```python
ACTIVE_STATUSES = ["open", "in_progress", "resolved", "on_hold", "escalated"]
TERMINAL_STATUSES = ["closed", "archived"]
```

No ESCALATED_STATUSES. The agent sees "escalated is like active" (both
count as work, both are non-terminal) and puts it in the existing
bucket. It cannot invent the separation because no template or pattern
in the codebase suggests a third non-terminal group.

### Graph agent projected output

graph_properties run-1 (17/17):

```python
TERMINAL_STATUSES = {"archived", "resolved", "closed"}
ACTIVE_STATUSES = {"on_hold", "in_progress", "open"}
ESCALATED_STATUSES = {"escalated"}
```

The most-specific-match algorithm selects escalated (3 properties) over
active (2 properties) despite both having counts_as_work=true. The
projector emits separate constants and helpers automatically.

## E30 → E31 progression

E30 tested "blocked" — a clean third group with no property overlap
(counts_as_work=false, terminal=false is unique to blocked). E31 tests
"escalated" — a fourth group that shares 2/3 properties with active.

Both get 0 structural bugs across all graph conditions. The most-
specific-match derive-group algorithm handles overlapping property
sets correctly. The file agent's structural failure rate stays constant
(33% in both E30 and E31) because the root cause is the same: the
missing abstraction.

## What E31 separates

E31 cleanly separates structural representation from behavioral
follow-through.

**Structural**: CNF eliminated all structural ambiguity by deriving
groups from status properties. 0/27 across all graph conditions. The
graph conditions differ in how the agent supplies intent (label,
validated, properties), but all share the same derivation/projection
machinery. That machinery is what eliminates structural bugs.

**Behavioral**: The remaining failures (test_14) are obligation-
execution failures, not classification failures. The agent sometimes
doesn't complete the repair loop for the analytics effect. The domain
model is correct by construction; downstream behavior coverage is not.

This distinction matters. The graph is not magically completing every
downstream behavior. It is making the domain model correct by
construction.

## The representation-induced failure

The file agent's failure is not "forgot a file" or "made a random
mistake." It is:

> The file representation did not expose the right abstraction, so the
> agent generalized incorrectly.

The code surface shows two buckets (ACTIVE_STATUSES, TERMINAL_STATUSES).
When a new concept shares properties with one bucket but is semantically
distinct, the file agent collapses it into the nearest existing bucket.
Same 3 bugs every run. That's not variance — it's representation-induced
failure.

The graph representation exposes properties and derivation. The agent
declares what the status means; the graph derives where it belongs.
That's the actual win.

## Conclusion

When a new concept does not fit the visible code pattern, file agents
collapse it into the nearest existing bucket. CNF derives the correct
bucket from properties.

E30 proved this for clean groups (no property overlap). E31 proves it
generalizes to overlapping groups where most-specific-match is required.
The design principle compounds.

## Files

- `experiments/e27-runtime-claimdesk/e31-runner.py` — experiment runner
- `experiments/e27-runtime-claimdesk/results-e31-*.json` — raw data
- `experiments/e27-runtime-claimdesk/output/e31-*/` — projected outputs

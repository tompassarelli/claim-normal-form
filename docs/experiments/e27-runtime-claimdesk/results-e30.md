# E30 — Semantic Authority Transfer

## Headline

E30 shows that property-derived graph classification eliminates the
bimodal failure mode from E29. Agents express business semantics; the
graph derives structure, obligations, and projections.

## Context

E29 found the graph acts as a semantic commitment amplifier — correct
classification cascades to downstream correctness, wrong classification
cascades to downstream catastrophe. In 2/6 graph runs the agent
classified "suspended" as "active" instead of "blocked", producing
6-7 obligation bugs per run. File agents consistently missed the
absent abstraction (BLOCKED_STATUSES, is_blocked) but failed locally,
not globally.

E30 moves classification authority from the agent into the graph.

## Changes

### 1. Property-derived classification

The group model encodes what each group means:

```
active:   counts_as_work = true,  terminal = false
terminal: counts_as_work = false, terminal = true
blocked:  counts_as_work = false, terminal = false
```

Three interfaces tested:

- **graph_label**: agent picks group directly (E29 control)
- **graph_validated**: agent picks group AND declares properties; graph
  rejects contradictions
- **graph_properties**: agent declares properties only; graph derives
  group

### 2. Effect vocabulary fix

E29 had a projector vocabulary mismatch: agents wrote "blocked" but the
projector checked for "tag-blocked". Fixed by accepting group names as
valid effect conditions. Both "blocked" and "tag-blocked" now match.

## Design

Same task as E29: add "suspended" as a blocked status. Same 17
integration tests (9 structural + 8 obligation). Same file baseline.

4 conditions, 3 runs each. All agents Claude Sonnet. Same business
requirement prompt across all conditions.

## Results

### Aggregate

| Condition | Structural bugs | Obligation bugs | Mean time | Mean cost |
|-----------|----------------|-----------------|-----------|-----------|
| graph_label | 0/27 | 0/24 | 53s | $0.151 |
| graph_validated | 0/27 | 0/24 | 47s | $0.120 |
| graph_properties | 0/27 | 0/24 | 50s | $0.109 |
| file_single | 0/27 | 14/24 | 59s | $0.149 |

### Per-run

**graph_label** (agent picks group directly)
```
Run 1:  17/17  46.7s  $0.189
Run 2:  17/17  52.1s  $0.132
Run 3:  17/17  59.2s  $0.131
```

**graph_validated** (agent picks group + properties, graph validates)
```
Run 1:  17/17  46.0s  $0.113
Run 2:  17/17  56.3s  $0.133
Run 3:  17/17  38.3s  $0.113
```

**graph_properties** (agent declares properties, graph derives group)
```
Run 1:  17/17  59.4s  $0.118
Run 2:  17/17  39.5s  $0.101
Run 3:  17/17  50.0s  $0.110
```

**file_single** (edit Python files)
```
Run 1:  13/17  65.4s  $0.160  FAILED: 09,10,14,16
Run 2:  12/17  51.8s  $0.139  FAILED: 09,10,14,15,16
Run 3:  12/17  59.8s  $0.148  FAILED: 09,10,14,15,16
```

### Comparison with E29

| Condition | E29 obligation bugs | E30 obligation bugs |
|-----------|---------------------|---------------------|
| graph_single/label | 7/24 (bimodal) | 0/24 |
| file_single | 13/24 | 14/24 |

Graph improved from 7/24 to 0/24. File baseline unchanged (13-14/24).

## Analysis

### Property-derived classification eliminates misclassification

graph_properties achieved 0/24 obligation bugs across 3 runs. The agent
declared `counts_as_work=false, terminal=false`. The graph derived
`group=blocked`. The projector emitted BLOCKED_STATUSES, is_blocked(),
analytics tagging automatically. Zero misclassification because there
is no group parameter to get wrong.

### graph_label also got 0/24

Two factors: the effect vocabulary fix eliminated test_14 failures that
occurred even with correct classification in E29, and misclassification
is stochastic (E29's 33% rate means 3/3 correct has ~30% probability).
graph_properties structurally cannot misclassify — that is the
architectural difference.

### File agents unchanged

Same failures as E29:

- test_09 (BLOCKED_STATUSES): 0/3
- test_10 (is_blocked): 0/3
- test_14 (analytics blocked tag): 0/3
- test_15/16 (suspend/resume permissions): 1/3 and 0/3

File agents add "suspended" as an orphan — not in either group, not in
a third group. They handle it as a one-off case rather than a structural
category. The concept is implied by the business rule but absent from
the code surface.

### Cost

`graph_properties` is the cheapest condition: $0.109/run vs $0.149/run
for file_single (27% cheaper) and $0.151/run for graph_label (28%
cheaper). The property interface is simpler — fewer decisions, fewer
tokens spent deliberating.

## What E30 shows

1. **Semantic authority transfer works.** Moving classification from
   agent to graph eliminates the missing-abstraction failure that file
   agents repeatedly exhibit.

2. **The graph compiles, not just amplifies.** In E29 the graph
   amplified whatever the agent chose. In E30 (properties mode) the
   graph compiles semantic properties into structural classification.

3. **File agents still do not invent absent abstractions.** The
   three-group gap persists across 9 file runs (E29 + E30). No file
   agent in any run produced BLOCKED_STATUSES or is_blocked().

4. **The effect vocabulary fix matters.** Stringly-typed protocols
   create real, consistent failures.

## The progression

```
E28 (simple task):
  graph 0/36 bugs, file 0/36 bugs
  → both correct, graph faster/cheaper

E29 (obligation pressure):
  graph 7-8/24 obligation bugs (bimodal)
  file 9-13/24 obligation bugs (consistent)
  → graph amplifies classification, right or wrong

E30 (semantic authority transfer):
  graph 0/24 obligation bugs (all conditions)
  file 14/24 obligation bugs (unchanged)
  → graph compiles agent intent, file repeats the missing abstraction
```

## Raw data

- JSON results: `experiments/e27-runtime-claimdesk/results-e30-{condition}.json`
- Agent artifacts: `experiments/e27-runtime-claimdesk/output/e30-{condition}-run-{N}/`
- Domain model: `experiments/e27-runtime-claimdesk/claimdesk.rkt`
- MCP server: `experiments/e27-runtime-claimdesk/claimdesk-mcp.rkt`
- Runner: `experiments/e27-runtime-claimdesk/e30-runner.py`

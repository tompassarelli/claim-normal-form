# E16: Agent Grounding Evaluation

## Status: harness ready, agent runs pending

The codebase, tasks, ground truth, hidden tests, and CNF baseline are
built. The actual agent-vs-agent runs need to be conducted.

## Setup

4-module Python order processing system:
- `pricing.py` — 18 functions, 5 layers of dependencies
- `validation.py` — 8 functions, with known bug
- `processing.py` — 8 functions, with 3 shadowed names
- `reporting.py` — 11 functions, with 3 dead code functions

45 top-level forms, 2969 objects, 2119 claims, 69 direct dependency
edges, 281 transitive pairs. 26 passing tests.

## CNF baseline (ground truth from claim graph)

```
round_cents transitive impact:  23 functions
full_report dependency tree:    25 functions
Functions with no callers:      10 (7 dead + 3 entry points)
```

## 10 tasks

Each designed with a specific trap that text search falls into:

| # | Task | Text trap |
|---|------|-----------|
| 01 | Rename `subtotal` | Dict keys, display strings |
| 02 | Blast radius of `round_cents` | 5 layers of indirect callers |
| 03 | Fix wrong `process` | 5 shadowed name pairs |
| 04 | Remove dead code | `total(` matches 4 functions |
| 05 | Add tax exemption | Downstream impact analysis |
| 06 | Extract helper | Pattern variants don't all fit |
| 07 | Fix validation bug | Cross-module import chain |
| 08 | Map dependency tree | 25+ functions, manual recursion |
| 09 | Rename `order_total` | `processing.total()` is different |
| 10 | Cross-session memory | CNF-only — impossible for text |

## Running

```bash
# Verify baseline
cd experiments/e16-agent-grounding/codebase
python3 test_orders.py

# CNF baseline
cd experiments/e16-agent-grounding
racket cnf-parse.rkt

# Hidden tests (after agent completes a task)
python3 ground-truth/hidden_tests.py
```

## Reproducing

Full instructions in `experiments/e16-agent-grounding/README.md`.

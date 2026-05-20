# E16: Agent Grounding Evaluation

Same repo. Same bugs. Same model. Same prompts. Same tests.

One agent gets text tools: read, grep, edit, run tests.
One agent gets CNF MCP: parse, dependencies, rename, rules, render.

Measure who actually fixes the code.

## Structure

```
codebase/           Python order processing system (4 modules, 50+ functions)
  models.py         Domain types
  pricing.py        Pricing calculations (5 layers deep)
  validation.py     Order validation (with known bug)
  processing.py     Order pipeline (with shadowed names)
  reporting.py      Analytics (with dead code)
  test_orders.py    26 passing tests
tasks/              10 tasks requiring structural understanding
ground-truth/       Expected answers + hidden test suite
```

## The codebase

Designed with specific traps:
- **Shadowed names**: `process()` vs `process_order()`, `total()` vs
  `subtotal()`/`order_total()`, `validate()` vs `validate_order()`,
  `summary()` vs `build_summary()`
- **String/dict key false positives**: `"subtotal"` as dict key and
  display string, `"total"` as dict key, `"status"` as string
- **Deep dependency chains**: `full_report` → 5 layers → `unit_price`
- **Dead code**: 7 functions with no callers
- **Known bug**: 100% discount validation gap (commented)

## Tasks

| # | Task | Requires | Trap |
|---|------|----------|------|
| 01 | Rename `subtotal` | Entity resolution | Dict keys named "subtotal" |
| 02 | Blast radius of `round_cents` | Transitive closure | 5 layers of indirect callers |
| 03 | Fix wrong `process` call | Name disambiguation | 5 shadowed names |
| 04 | Remove dead code | Exhaustive caller analysis | `total(` matches 4 functions |
| 05 | Add tax exemption rule | Downstream impact | Threshold vs test fixtures |
| 06 | Extract helper pattern | Pattern recognition | Group-by variants don't fit |
| 07 | Fix validation bug | Cross-module reasoning | Need to compute subtotal - discount |
| 08 | Map full dependency tree | Transitive analysis | 25+ functions, 5 layers |
| 09 | Rename `order_total` | Entity resolution + shadows | `processing.total()` is different |
| 10 | Cross-session memory | Persistent rules + checkpoint | CNF-only (text agent scores 0) |

## Running the experiment

### Text agent

```bash
cd experiments/e16-agent-grounding/codebase
# Give agent: read, grep, edit, run tests
# For each task, paste the prompt from tasks/task-NN.md
# Record: tool calls, tokens, time, result
python3 test_orders.py  # verify tests pass after each task
```

### CNF agent

```bash
# Start MCP server
racket mcp-server.rkt
# Give agent: CNF MCP tools
# First: parse_program(source from all 4 .py files)
# For each task, paste the prompt from tasks/task-NN.md
# Record: tool calls, tokens, time, result
```

### Scoring

```bash
python3 ground-truth/hidden_tests.py           # run all checks
python3 ground-truth/hidden_tests.py "task 01"  # run one check
```

## Metrics

| Metric | How measured |
|--------|-------------|
| Correct fix | Hidden tests pass/fail |
| False-positive edits | Dict keys/strings wrongly changed |
| Missed affected functions | Compare to ground truth dep list |
| Tool calls | Count from session log |
| Tokens used | From API/session metrics |
| Wall time | Timestamp diff |

## The headline we're looking for

```
Text agent:  X/10 tasks correct, Y false-positive edits
CNF agent:   X/10 tasks correct, 0 false-positive edits
```

Task 10 is CNF-only (cross-session memory). The text agent cannot
attempt it. That alone is a qualitative gap no benchmark closes.

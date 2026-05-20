# E6: Multi-Round Arena — The Compounding Test

**Date:** 2026-05-20

## Setup

Same arena as E5, but with **5 sequential tasks** instead of 1.
Two real Claude agents, same 20-function program. The question:
does the CNF agent's accumulated structural understanding compound
across tasks?

**Program:** 20 functions in a linear algebra DSL (same as E5).

**Tasks:**
1. Discover dependencies, find duplication bug, rename dot to
   dot-product, define transitive rules, find affected functions
2. Find all functions that transitively depend on `scale`
3. Which function is the biggest hub (most callers)?
4. Rename `project` to `vector-project`, verify propagation
5. Classify all functions as leaves, roots, or interior

**CNF agent:** mcp__cnf__* tools (parse, query, define_rule, rename,
render, inspect). State persists between tasks.

**Text agent:** grep, sed, awk, Python scripts. Conversation context
persists but no structural index.

## Results

Both agents completed all 5 tasks correctly. Same answers:
- 10 transitive dependents of dot-product
- 14 transitive dependents of scale
- scale is biggest hub (6 callers)
- 4 leaves (distance, dot-product, scale, translate)
- 6 roots (midpoint, lerp, decompose, recompose, invert-transform, pipeline)

### Per-task tool calls

| Task | CNF | Text | Winner |
|------|----:|-----:|--------|
| 1    |  27 |    5 | Text   |
| 2    |   1 |    1 | Tie    |
| 3    |   1 |    2 | CNF    |
| 4    |   2 |    3 | CNF    |
| 5    |   1 |    1 | Tie    |
| **Tasks 2-5** | **5** | **7** | **CNF** |
| **Total** | **32** | **12** | **Text** |

### Wall time

| | CNF | Text |
|---|---:|---:|
| Total time | 192s | 110s |
| Task 1 (est.) | ~160s | ~50s |
| Tasks 2-5 (est.) | ~32s | ~60s |

## Analysis

### Text agent wins total. Again.

12 tool calls vs 32. 110s vs 192s. On a 5-task session against a
20-function program, the text agent wins handily. Same story as E5.

### But the per-task story is different from E5

In E5 (single task), text won 8-to-42. A 5.3x advantage.

In E6, tasks 2-5 show a different pattern:
- **CNF: 5 calls** (1, 1, 2, 1)
- **Text: 7 calls** (1, 2, 3, 1)

After the first task, CNF is *cheaper per task*. The accumulated
rules (`depends-on`, `trans-depends`, `contains`) answer follow-up
questions without redefinition. The matview stays current through
renames — task 4's rename didn't require the CNF agent to recompute
anything.

### Where the 27 calls went

Task 1 breakdown for the CNF agent:
- 1 reset + 1 parse = 2 calls (unavoidable)
- ~13 schema discovery calls (inspecting entities to find predicate IDs)
- ~8 rule definition + query calls
- ~4 render/rename/verify calls

**Schema discovery alone was ~13 of 27 calls.** This is the exact
bottleneck identified in the interface redesign (devlog 008). The
`parse_program` tool now returns the schema — but this change wasn't
active in the running MCP server during the test.

### What the interface improvements would change

Three changes are built but weren't active during E6:
1. `parse_program` returns schema (eliminates ~13 discovery calls)
2. Named symbol resolution (eliminates lookup round-trips)
3. `batch` tool (multiple operations per call)

**Estimated task 1 with improvements:**
- 1 parse (includes schema) + 1 batch (define all rules + query) +
  1 rename + 1 render = **~4-6 calls**

**Estimated total with improvements: ~9-11 calls.**

That would beat the text agent's 12.

### The crossover math

Current (no interface improvements):
- CNF overhead in task 1: 22 extra calls (27 vs 5)
- CNF savings per subsequent task: ~0.5 calls (1.25 vs 1.75 avg)
- Crossover: ~44 additional tasks

With interface improvements:
- CNF overhead in task 1: ~1 extra call (6 vs 5)
- CNF savings per subsequent task: ~0.5 calls
- Crossover: ~2 additional tasks (i.e., by task 3)

### The text agent surprise

The text agent was smarter than expected. It used Python inline
scripts for transitive closure (BFS), caller counting, and
leaf/root classification — all in single tool calls. And it
reused the call graph structure from conversation context across
tasks 2-5 without re-parsing.

Conversation context is an effective short-term memory for text
agents. The CNF matview advantage shows up when:
1. The graph changes (rename invalidates text's cached knowledge)
2. The session is long enough for context to compress
3. Queries are complex enough that Python scripts become unwieldy

### What this proves about the thesis

1. **The compounding effect is real.** Tasks 2-5: CNF 5 calls vs
   text 7 calls. Rules defined once, used many times.

2. **The investment cost is too high.** 27 calls in task 1 vs 5.
   The interface, not the engine, is the bottleneck.

3. **The interface redesign is the critical path.** With schema +
   batch + symbols, CNF task 1 drops to ~5 calls. Total drops to
   ~10 — beating text's 12.

4. **Text agents are smarter than benchmarks suggest.** Python
   scripts and conversation memory are powerful. The CNF advantage
   is real but smaller than E1-E4 scripted benchmarks implied.

5. **The capability gap persists.** The CNF agent's rename is
   semantic (1 call, matview auto-updates). The text agent's rename
   is textual (sed + verify + read = 3 calls, no structural
   guarantee). At larger scale, this gap widens.

## Comparison with E5

| | E5 (1 task) | E6 (5 tasks) |
|---|---:|---:|
| CNF total calls | 42 | 32 |
| Text total calls | 8 | 12 |
| CNF calls/task | 42 | 6.4 |
| Text calls/task | 8 | 2.4 |
| CNF tasks 2-5 | — | 5 (1.25/task) |
| Text tasks 2-5 | — | 7 (1.75/task) |

The CNF agent's per-task cost drops from 42 (task 1) to 1.25
(tasks 2-5). The text agent's stays relatively flat. The curves
cross — but only after the interface improvements reduce task 1.

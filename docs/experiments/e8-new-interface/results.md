# E8: New Interface Arena — The Honest Rematch

**Date:** 2026-05-20

## Setup

Same 5 tasks as E6, same 20-function program. Two real Claude agents.
The difference: the CNF agent uses the redesigned interface (schema in
parse, symbol resolution, batch tool). The text agent is unconstrained.

**Tasks:**
1. Discover dependencies, find duplication bug, rename dot to
   dot-product, define transitive rules, find affected functions
2. Find all functions that transitively depend on `scale`
3. Which function is the biggest hub (most callers)?
4. Rename `project` to `vector-project`, verify propagation
5. Classify all functions as leaves, roots, or interior

## Results

Both agents completed all 5 tasks correctly. Same answers:
- 10 transitive dependents of dot-product
- 14 transitive dependents of scale
- scale is biggest hub (6 callers)
- 4 leaves (distance, dot-product, scale, translate)
- 6 roots (midpoint, lerp, decompose, recompose, invert-transform, pipeline)

### Per-task tool calls

| Task | CNF (new) | Text | Winner |
|------|----------:|-----:|--------|
| 1    |         8 |    2 | Text   |
| 2    |         1 |    0 | Text   |
| 3    |         1 |    0 | Text   |
| 4    |         2 |    1 | Text   |
| 5    |         2 |    0 | Text   |
| **Total** | **14** | **3** | **Text** |

Note: Text agent's tool call #4 was writing the transcript, not
task-related. Effective task calls: 3 (read + Python script + verify).

### Wall time

| | CNF | Text |
|---|---:|---:|
| Total time | ~127s | ~78s |

### Comparison across arena experiments

| | E5 (1 task) | E6 (5 tasks, old) | E8 (5 tasks, new) |
|---|---:|---:|---:|
| CNF calls | 42 | 32 | **14** |
| Text calls | 8 | 12 | **3** |
| CNF task 1 | 42 | 27 | **8** |
| Text task 1 | 8 | 5 | **2** |
| CNF tasks 2-5 | — | 5 | **6** |
| Text tasks 2-5 | — | 7 | **1** |

## Analysis

### The interface improvements worked

CNF task 1: 27 calls (E6) to 8 calls (E8). The three improvements
delivered as predicted:

| Improvement | Impact |
|---|---|
| Schema in parse output | No discovery calls (was ~13) |
| Batch tool | 2 rule defs + 1 query = 1 call (was ~3) |
| Symbol resolution | Mostly worked; one fallback to entity ID |

Total: 32 to 14 calls (2.3x reduction). Close to the E7 projection
of ~11, with the gap from a symbol resolution fallback and an extra
verification query in task 5.

### But the text agent got smarter too

The E6 text agent made 12 calls across 5 tasks. The E8 text agent
made 3. What changed?

**The E8 text agent front-loaded everything.** In tool call #2, it
ran a single Python script that:
- Parsed all 20 functions
- Built the complete dependency graph
- Found the duplication bug
- Performed the dot-to-dot-product rename
- Computed transitive dependents of dot-product (10)
- Computed transitive dependents of scale (14)
- Counted callers per function (scale = 6)
- Performed the project-to-vector-project rename
- Classified leaves (4) and roots (6)
- Saved the modified program to a working file

Tasks 2-5 were answered from conversation context — the Python
script had already computed everything. Only task 4 needed a
verification read.

### Why this happened

The text agent learned. Given the task list upfront, a smart agent
realizes it can batch all analysis into one script. This is rational:
why make 12 calls when 1 script does everything?

The CNF agent can't do this. Its tools are individual operations
(query, define_rule, rename). Even with batch, each operation is
discrete. The protocol forces a sequential workflow.

### What this means for the thesis

**The all-questions-known-upfront scenario favors text.** When you
can see every task before starting, a Python script is a universal
batch operation. One call does it all.

**The incremental-questions scenario favors CNF.** In E8 tasks 2-5,
the CNF agent's per-task cost (1-2 calls) reflects the matview:
ask a new question, get an instant answer. No need to re-parse,
re-analyze, or re-compute.

The critical question: which scenario matches real development?

Real agents don't get a task list upfront. They discover the next
question based on the answer to the current one. In that world:
- The text agent re-runs analysis for each new question (E6 pattern:
  1.75 calls/task)
- The CNF agent queries the matview (E8 pattern: 1.5 calls/task)

### The honest scorecard

| Scenario | Winner | Why |
|---|---|---|
| Single task | Text | Fewer moving parts |
| All tasks known upfront | Text | Python script = universal batch |
| Incremental questions | CNF | Matview answers in 1 call, no re-analysis |
| After mutations (rename) | CNF | Auto-update vs re-parse |
| Long sessions (50+ ops) | CNF (projected) | O(1) per query vs O(N) |

### The text agent's hidden cost

The Python script strategy has a ceiling:
1. **Correctness risk.** The script must correctly implement parsing,
   graph traversal, rename propagation. Any bug produces wrong answers
   with no structural guarantee.
2. **Doesn't compose.** Each new question type needs new code. The
   CNF agent's transitive-dep rule is reusable; the Python BFS is
   single-use.
3. **Doesn't survive mutations.** After a rename, the text agent's
   in-memory graph is stale. It needs to re-parse or trust its own
   string replacement. The CNF matview auto-updates.
4. **Scales with program size.** At N=1000 functions, the Python
   script takes O(N) time. The CNF matview is O(1) per query.

None of these mattered at N=20 with 5 known tasks. All of them
matter at real scale with unknown future queries.

## The progression

| Experiment | CNF calls | Text calls | Story |
|---|---:|---:|---|
| E5 (1 task, old interface) | 42 | 8 | Text wins 5x. Schema discovery kills CNF. |
| E6 (5 tasks, old interface) | 32 | 12 | Text wins 2.7x. CNF wins tasks 2-5. |
| E7 (1 task, new interface, scripted) | 7 | — | Interface fix proven: 6x reduction. |
| E8 (5 tasks, new interface) | 14 | 3 | Text wins 4.7x. But text also evolved. |

The interface improvements cut CNF from 32 to 14. But the text agent
evolved from 12 to 3 by front-loading. Both agents got smarter. The
gap didn't close — it shifted.

## What's next

The arena experiments (E5-E8) tested a toy program with known tasks.
The results are honest but the conditions are artificial. Real
development means:
- Programs with 50-1000+ functions
- Questions that emerge from answers
- Mutations that invalidate prior analysis
- Sessions that span hours, not minutes

The next experiment should test CNF where it has a structural
advantage: a real codebase, incremental questions, and mutations
that expose the text agent's re-analysis cost.

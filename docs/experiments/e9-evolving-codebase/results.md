# E9: Accumulated Knowledge at Scale — Results

**Date:** 2026-05-20

## Setup

50 functions, 4 layers, 81 dependency edges. Two real Claude agents,
7 tasks given upfront but designed to build on each other (task 4
renames a function, tasks 5+ work on the renamed codebase).

**CNF agent:** MCP tools (batch, query, define_rule, rename, render).
Symbol resolution was broken for function names during this test —
agent used entity IDs from parse output.

**Text agent:** Bash (Python scripts, sed) + Read.

## Results

Both agents completed all 7 tasks correctly.

### Per-task tool calls

| Task | CNF | Text | Notes |
|------|----:|-----:|-------|
| 1 — Structure | 2 | 3 | CNF: batch(reset+parse) + query. Text: Read + 2 Python scripts. |
| 2 — Duplicates | 2 | 0 | CNF: render x2. Text: front-loaded into T1 scripts. |
| 3 — Transitive deps | 2 | 0 | CNF: batch(define rules) + query. Text: front-loaded. |
| 4 — Rename | 1 | 1 | CNF: batch(rename+render). Text: sed. |
| 5 — Post-rename | 1 | 1 | CNF: query existing matview. Text: Python re-analysis. |
| 6 — Shared deps | 2 | 0 | CNF: define_rule + query. Text: front-loaded. |
| 7 — Final report | 0 | 0 | Both: answered from accumulated context. |
| **Total** | **10** | **~6** | |

### Wall time

| | CNF | Text |
|---|---:|---:|
| Duration | ~136s | ~124s |

### Correctness

Both agents produced identical key answers:
- 12 leaves, 10 roots, normalize=biggest hub (7 callers)
- 2 duplicate pairs: lower/upper, validate/negate
- 16 transitive dependents of normalize
- Rename propagated correctly (7 callers updated)
- 6 shared-dependency pairs
- 81 edges, depth 4, 3 hub functions (normalize 7, to-int 5, clamp 4)

Minor difference: the CNF agent initially miscounted roots as 12
(included ingest/process, which pipeline calls) but self-corrected
in Task 7. Text agent got 10 from the start.

## Analysis

### Text agent front-loads, again

The text agent's Task 1 included 3 tool calls: 1 Read + 2 Python
scripts. Those 2 scripts computed answers for Tasks 1, 2, 3, 6,
and 7 — five of seven tasks answered in the initial batch.

The only additional calls were Task 4 (sed rename, 1 call) and
Task 5 (Python re-analysis after rename, 1 call).

This is the same front-loading strategy from E8, scaled to 50
functions. It works because: (1) all tasks are visible upfront,
(2) a Python script can do arbitrary analysis in one call, and
(3) 50 functions is still trivial for Python.

### CNF batching helps but doesn't match Python generality

The CNF agent used batch for 4 of its 10 calls:
- batch(reset + parse_program) — 2 ops in 1 call
- batch(define_rule x2) — but then needed a separate query
- batch(rename + render) — 2 ops in 1 call

Batch combines MCP operations, but each operation is a defined
tool. A single Python script can implement transitive closure,
duplicate detection, shared-dependency analysis, and structural
reporting — all in one call.

### Where CNF won individual rounds

- **Task 1**: CNF 2 calls vs text 3. The batch(reset+parse) + single
  dep query is efficient. Text needed Read + 2 separate Python scripts.
- **Task 5**: CNF 1 call vs text 1 — a tie, but qualitatively different.
  CNF queried the existing transitive-dep rule (matview auto-updated
  through rename). Text re-ran the BFS from scratch. At 50 functions
  this costs the same. At 5000, it wouldn't.
- **Task 7**: Both 0 calls. Both answered from context.

### Where text won

- **Tasks 2, 3, 6**: Text 0 calls vs CNF 2 each. The text agent
  pre-computed these answers in Task 1's Python scripts. The CNF
  agent had to define rules and query separately for each.

### The marginal cost convergence

After initial setup, both agents converge to ~1 call per new task:

| Phase | CNF | Text |
|---|---:|---:|
| Setup (Tasks 1-3) | 6 | 3 |
| Mutation (Task 4) | 1 | 1 |
| Post-mutation (Tasks 5-7) | 3 | 2 |

The difference is entirely in setup cost. CNF needs 3 more calls
to set up (define rules, render for comparison). Once rules exist,
queries are 1 call each — same as a Python script.

**The crossover never happens** because Python scripts are also
O(1) per query at this scale. A text agent with the analysis in
conversation context can answer follow-up questions from memory.

## Comparison across all arena experiments

| Experiment | CNF | Text | Ratio | Scale |
|---|---:|---:|---:|---|
| E5 (1 task, old) | 42 | 8 | 5.3x | 20 fn |
| E6 (5 tasks, old) | 32 | 12 | 2.7x | 20 fn |
| E8 (5 tasks, new) | 14 | 3 | 4.7x | 20 fn |
| **E9 (7 tasks, new)** | **10** | **~6** | **1.7x** | **50 fn** |

The gap is narrowing: 5.3x → 2.7x → 1.7x (ignoring E8 where text
also evolved). The interface improvements (E7-E8) and larger task
count (E9) both help CNF.

## What this proves

### 1. Python scripts are the universal batch

A single Bash call executing a Python script can do unlimited
computation. This makes tool-call-count comparisons fundamentally
asymmetric: one Python call ≈ one MCP batch of N operations, for
any N.

The only way CNF wins on call count is if the task requires
something Python can't easily do (semantic rename with structural
guarantees, incremental view maintenance after mutations).

### 2. Marginal cost converges

After setup, both approaches cost ~1 call per new question.
CNF queries the matview; text answers from context or runs a
script. At 50 functions, these are equivalent.

### 3. The gap is setup cost

CNF pays 3 extra calls for setup (rule definition, rendering for
comparison). This is the irreducible cost of building the claim
graph vs reading text. It amortizes over more tasks but never
reaches zero.

### 4. The missing piece is incremental update

The one scenario where CNF should decisively win — codebase
mutation between tasks — couldn't be tested. The engine doesn't
support incremental parse (reset loses all rules). With incremental
update:
- Text agent: re-read + re-analyze = 2+ calls per mutation
- CNF agent: incremental parse + matview auto-update = 0-1 calls

This is the thesis that remains unvalidated. E9 shows CNF is
competitive (1.7x, down from 5.3x). Incremental parse would
close or invert the remaining gap.

### 5. Symbol resolution bug matters

The CNF agent used entity IDs ("366") instead of names
("normalize") because bare symbol resolution was broken for
parsed function names. This was fixed during the experiment
(commit `84f1274`) but the fix wasn't active in the running
server. With the fix, the agent's prompts would be cleaner
and it might save 1-2 exploratory calls.

## What's next

The bottleneck is no longer the interface (E7-E8 fixed that) or
the engine (entries 001-007 fixed that). It's **incremental parse**.

Without it, every codebase mutation requires reset + full reparse,
which destroys accumulated rules and matviews. With it, mutations
flow through the claim graph incrementally, and the matview stays
valid.

That's the experiment that would show CNF winning: E10 with
incremental parse, external mutations, and 20+ tasks where each
mutation invalidates text's prior analysis but CNF's matview
auto-updates.

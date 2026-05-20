# CNF Experiments

Empirical benchmarks for the CNF thesis. The point is to replace
argument ("graphs are better than text") with measurement ("agent
completes the task in X seconds with CNF vs Y seconds with text").

## Why this exists

CNF's claim is that agents code faster against a maintained semantic
index than against text files. Microbenchmarks (rename speed, query
latency) are necessary but not sufficient. The real test is agent
task wall-time at scale.

## Planned experiments

### E1: Agent Task Wall-Time (rename + verify)

The first real experiment. Compare agent performance on a structural
editing task across CNF and text representations.

**Task:** Given N functions with chain dependencies:
1. Rename a shared function
2. Find all affected callers
3. Update one dependent expression
4. Render affected source
5. Verify the dependency graph changed correctly

**Scale:** N = 200, 500, 1000, 2000 functions

**Compare:**
- **CNF agent** using MCP tools: rename!, query (fn-depends-on),
  render, inspect
- **Text agent** using standard tools: grep, read, sed/edit,
  grep again to verify

**Measure:**
- Wall-time (end-to-end)
- Tool calls (total count)
- Tokens consumed (input + output)
- Files/chunks read (text agent only)
- Wrong edits / verification failures
- Time spent on verification vs mutation

**Hypothesis:** CNF agent is faster at all scales. The gap widens
with N because:
- CNF rename is O(1), text find-replace is O(N)
- CNF dep query is O(1) (materialized), text grep is O(N)
- CNF verification is structural (query the graph), text
  verification requires re-scanning

**Expected crossover:** CNF overhead (parse + materialize) is
amortized after 2-3 operations. By N=500, CNF should be 2-3x
faster. By N=2000, 5-10x.

### E2: Incremental Edit Throughput

How fast can each system handle a burst of small edits?

**Task:** Apply 20 sequential renames to different functions,
querying dependencies after each rename.

**Measure:** Total wall-time for 20 × (rename + query). CNF
should show near-constant per-operation cost. Text agent's
per-operation cost grows with N.

### E3: Cold Start vs Warm Graph

Compare the cost of building the semantic index once (parse +
materialize) vs re-deriving structure from text on every query.

**Task:** Parse N functions, then answer 10 dependency questions.

**Measure:**
- CNF: parse + materialize (one-time) + 10 × query (cache hits)
- Text: 10 × (grep + parse output + reason about results)

### E4: Error Recovery

When the agent makes a mistake, how quickly does each system
recover?

**Task:** Rename a function incorrectly, detect the error via
tests/verification, undo, rename correctly.

**Measure:** Recovery time and token cost. CNF has supersession
history built in. Text agent must re-read, re-grep, re-edit.

# E5: Arena — Real Agent Comparison

**Date:** 2026-05-20

## Setup

Two actual Claude agents given the same task on the same 20-function
program. Not scripted benchmarks — real agents using real tools,
making real decisions about how to approach the problem.

**Program:** 20 functions in a linear algebra DSL. Layered call graph
from leaf primitives (distance, scale) through compound operations
(project, reject) to high-level compositions (chain, pipeline).

**Task:**
1. Discover the dependency structure
2. Find that `distance` and `dot` have identical implementations
3. Figure out which functions are affected by the duplication
4. Rename `dot` to `dot-product`
5. Define a rule for transitive dependents of `dot-product`
6. Render the affected functions

**CNF agent:** mcp__cnf__* tools (parse, query, define_rule, rename, render)
**Text agent:** grep, sed, awk, file operations

## Results

Both agents completed the task correctly. Same answers:
- 10 transitive dependents of dot/dot-product
- Same call graph structure
- Same rename applied

### Raw numbers

| | CNF agent | Text agent |
|---|---:|---:|
| Tool calls | 42 | 8 |
| Wall time | 191s | 82s |
| Correct | Yes | Yes |

### What each agent did

**Text agent (8 calls):**
1. Read the file
2. grep for function definitions → built call map
3. Compared distance and dot bodies → confirmed duplication
4. grep for `dot` in all function bodies → found `project`
5. Walked callers recursively via grep → 10 transitive dependents
6. sed to rename dot → dot-product in refactored file
7. Wrote transcript

Simple, direct, effective.

**CNF agent (42 calls):**
1. Reset workspace
2. Parsed program into claim graph (503 objects, 331 claims)
3. Inspected entities to discover schema (predicate IDs for body, calls, left, right)
4. Defined `sub-expr` rules (left/right child traversal)
5. Defined `contains` rule (transitive expression tree closure)
6. Defined `fn-calls` rules (function-to-function dependency)
7. Defined `depends-on` rules (transitive call graph closure)
8. Queried dependencies, rendered functions, confirmed duplication
9. Renamed via `mcp__cnf__rename` (O(1) claim supersession)
10. Defined `uses-dot-product` rule
11. Queried and rendered affected functions
12. Wrote transcript

Thorough, structural, but expensive.

## Honest analysis

### Text agent wins this task

On a 20-function program with a known bug, the text agent is faster,
simpler, and equally correct. grep is the right tool for "find which
functions mention dot." sed is the right tool for "rename dot to
dot-product." The text agent finished in half the time with one-fifth
the tool calls.

### What the CNF agent built that the text agent didn't

The CNF agent left behind:
- A claim graph with 503 objects and full structural decomposition
- 6 composable Datalog rules (sub-expr, contains, fn-calls, depends-on, uses-dot-product)
- A materialized view where any dependency query is O(1)
- Supersession history (old name preserved)

The text agent left behind:
- A sed command
- A refactored text file

### When the difference matters

If the session ends here, the text agent wins. No question.

If the session continues — "now find functions that transitively
depend on `scale`", "rename `project` to `vector-project`", "which
functions would be affected?" — the CNF agent answers each question
in one tool call (O(1) matview hit). The text agent re-greps
everything from scratch.

The CNF agent's 42 tool calls were an *investment*. The text agent's
8 were *expenditure*. The investment pays off only if the session is
long enough.

### What this reveals about the thesis

The thesis isn't "CNF is faster for every task." It's:

1. **CNF agents build persistent structural understanding.** The
   Datalog rules accumulate as reusable knowledge. The text agent's
   grep results are single-use.

2. **The payoff is in sustained sessions.** The CNF agent's upfront
   cost (schema discovery, rule definition) amortizes over subsequent
   queries. Short sessions favor text.

3. **The capability gap is real but doesn't always matter.** The CNF
   agent can compose rules, version definitions, and query the graph
   declaratively. For "find and rename a function," that's overkill.

4. **Schema discovery is the hidden cost.** The CNF agent spent
   significant effort figuring out predicate IDs and expression
   structure. This is a one-time cost per session, but it's not free.

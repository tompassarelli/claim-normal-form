# E9: The Evolving Codebase

## Thesis under test

CNF agents maintain structural understanding incrementally through
mutations. Text agents must re-analyze from scratch. The cost gap
grows with codebase size, mutation frequency, and session length.

E5–E8 held these variables constant (small, stable, known-questions)
and text won. E9 varies them.

## Protocol

**Two agents.** Same tasks, same codebase, same mutations. One uses
CNF MCP tools, one uses text tools (read, grep, sed, Python).

**Sequential revelation.** Tasks are given one at a time. The agent
completes a task, reports the answer, and receives the next task.
No lookahead. This prevents the front-loading strategy that dominated
E8.

**External mutations.** Between some tasks, the codebase changes.
New functions appear, existing functions are modified, functions are
renamed. For the text agent, the file is updated. For the CNF agent,
the claim graph is updated via `parse_program` on the new source.

**Measurement:** tool calls per round, correctness, total calls,
wall time.

## Program

50 functions across 4 layers in a data processing pipeline DSL:

**Layer 1 — Primitives (12 functions):**
Leaf operations with no dependencies. String manipulation, math,
type conversion, validation. These are the stable foundation.

**Layer 2 — Transforms (14 functions):**
Each calls 2-3 primitives. Data cleaning, normalization, formatting.
Medium fan-out.

**Layer 3 — Combinators (14 functions):**
Each calls 2-4 transforms. Pipeline stages, filter chains, mappers.
This is where the interesting dependency structure lives.

**Layer 4 — Pipelines (10 functions):**
Top-level compositions calling combinators. Entry points. Some share
combinators, creating overlapping dependency cones.

Properties:
- ~120 dependency edges (avg 2.4 per function)
- 3-4 hubs with 6+ callers
- 2-3 pairs of suspiciously similar functions (planted bugs)
- Some mutual dependencies between combinators (cycles)
- 1 unreachable function (dead code)

## Rounds

### Round 1: Orientation (no mutation)

Parse the 50-function program.

**Task:** "Map the dependency layers. Which functions are leaves?
Which are roots? Which function has the most callers?"

*What this tests:* Initial setup cost. CNF pays parse + rule
definition. Text pays read + one analysis script. Similar to E8
task 1 but at 2.5x scale.

### Round 2: Deep query (no mutation)

**Task:** "Find all pairs of functions that have identical or
near-identical implementations. For each pair, list which functions
would be affected if we merged them."

*What this tests:* Multi-step reasoning. The CNF agent can define
a `similar-body` rule and compose it with `transitive-dep`. The
text agent needs custom comparison logic. Both should manage, but
the CNF rule persists for later.

### Round 3: First mutation

**Mutation:** 8 new functions added (2 primitives, 3 transforms,
3 combinators). Some call existing functions; some are called by
existing pipelines that are updated.

**Task:** "What changed? Which existing functions are now affected
by the new code? Did any of the duplication pairs from Round 2
change?"

*What this tests:* Incremental analysis after addition. The CNF
matview propagates the new dependencies automatically. The text
agent must re-read, re-analyze, and diff against its prior results.
The question explicitly references Round 2's findings — the agent
must either remember or recompute.

### Round 4: Targeted rename

**Task:** "Rename `normalize` to `normalize-v2` and rename
`clean-whitespace` to `strip-ws`. Show all affected code for both
renames."

*What this tests:* Semantic rename. CNF does this in 2 calls
(rename + render). Text does sed + verify, but at 58 functions,
there's more risk of partial matches and more verification needed.

### Round 5: Second mutation + rule evolution

**Mutation:** 5 functions refactored — their implementations change
but their signatures stay the same. A new shared helper is extracted.

**Task:** "Did the refactoring change any dependency edges? Did it
fix any of the duplication from Round 2? Define or update a rule
for 'functions with shared implementation patterns' and report the
current groups."

*What this tests:* This is the CNF showcase. The `similar-body`
rule from Round 2 needs supersession — the refactored functions
have new bodies. The CNF agent uses `supersede_rule` and the
matview auto-updates. The text agent rewrites its comparison
logic.

### Round 6: Impact analysis after cumulative changes

**Task:** "Since the beginning of the session, which dependency
edges were added, removed, or changed? Produce a delta report."

*What this tests:* Historical reasoning. CNF has supersession
history — every old claim is preserved. Comparing current vs
original claims is a query. The text agent has no history; it
must diff the original file against the current one and re-derive
the dependency graph for both.

### Round 7: Third mutation (scale stress)

**Mutation:** 12 more functions added. Program is now 70 functions.

**Task:** "Recompute the layer map. Which layer has the most
internal dependencies? Are there any dependency cycles?"

*What this tests:* Scale sensitivity. At 70 functions with ~170
edges, re-analysis is getting expensive for text. The CNF matview
absorbs the new functions incrementally.

### Round 8: Synthesis

**Task:** "Produce a structural health report: total functions,
dependency depth, hub functions (>5 callers), orphans (unreachable),
remaining duplication, and any cycles. Compare to Round 1's
baseline."

*What this tests:* Cumulative knowledge. Everything the CNF agent
defined (rules, matviews) feeds directly into this report. The
text agent must either remember its Round 1 results from context
or recompute everything.

## What we expect

### CNF agent

- **Round 1:** 4-6 calls (parse, query deps, define layer rules,
  query results). Higher than text's initial setup.
- **Rounds 2-8:** 1-3 calls each. Queries hit matview. Mutations
  are absorbed by re-parse. Rule evolution via supersede_rule.
- **Round 6:** This is where CNF should shine — historical query
  over supersession history is a built-in capability.
- **Estimated total:** 15-25 calls.

### Text agent

- **Round 1:** 2-3 calls (read + Python analysis). Fast.
- **Rounds 3, 5, 7 (mutations):** Must re-read and re-analyze.
  2-3 calls each to rebuild understanding.
- **Round 6 (history):** Must re-derive the original graph from
  the original file and diff. 3-4 calls.
- **Round 2, 4, 8:** 1-2 calls each (Python script or grep).
- **Estimated total:** 15-22 calls.

### The honest prediction

The totals may be close. The per-round pattern is what matters:
- Text agent's cost is ~constant per round (re-analyze every time)
- CNF agent's cost drops after Round 1 (matview absorbs changes)

If we see CNF at 2 calls/round for rounds 3-8 while text stays at
2-3 calls/round, the incremental thesis is validated at real scale
with real mutations.

If the text agent finds a way to maintain state across mutations
(e.g., incremental Python scripts that patch their own data
structures), that's also a meaningful finding — it would mean the
CNF architecture can be replicated in ad-hoc code, which challenges
the thesis in a different way.

## Implementation requirements

### Program generation

Hand-write the 50-function program. It must be:
- Large enough that re-analysis is non-trivial
- Structured enough that the dependency graph has interesting properties
- Contain planted bugs (duplication, dead code, cycles) for tasks to find
- Written in the arena S-expression DSL

### Mutation scripts

Pre-define the 3 mutations (rounds 3, 5, 7):
- Each is a new version of the source file
- Mutations are realistic (additions, refactors, extractions)
- The CNF agent sees the delta; the text agent sees the new file

### Harness

A coordinator script that:
1. Gives the agent a task
2. Collects the response (tool calls + answer)
3. Applies the next mutation if applicable
4. Gives the next task

For real agents, this is the human operator (us). For scripted
validation, this could be a bash script piping tasks through.

### Fairness

Both agents must:
- See the same source at each round
- Answer the same questions
- Not see future tasks
- Have their tool calls counted consistently

The CNF agent's re-parse after mutation counts as a tool call.
The text agent's re-read after mutation counts as a tool call.

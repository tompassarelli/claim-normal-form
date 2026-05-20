# CNF Roadmap

## DONE: Agent Interface (MCP Server)

18 MCP tools over JSON-RPC 2.0 / stdio. Claude connects, parses
programs into claims, queries dependencies, renames functions,
renders results — all through tool calls. Shipped `a12dce7`.

## DONE: Materialized Views (Reactive Datalog)

`materialize!` caches derived facts and registers hooks on `claim!`.
New claims delta-propagate through rules incrementally. Views stay
current without re-running the fixpoint.

Results at N=200: dep query drops from 67ms (cold) to 0ms (cache hit).
Incremental parse maintains views live — query after parse is O(1).
Shipped `a12dce7`.

## DONE: E1 Scripted Benchmark + Provenance-Tracked Deletion

First pass: CNF lost at every scale (0.04x at N=1000). Root cause:
supersession nuked the matview cache → full fixpoint recompute.

Built provenance-tracked deletion. Each derived tuple records which
claim IDs supported its derivation. On supersession, retract only
affected tuples and re-derive through alternate paths.

Results: "Find affected" dropped from 1062ms to 0.1ms at N=1000.
Total improved 4.1x. Post-load operations: CNF is 1.4x faster than
text. Crossover at ~35 operations. See `docs/experiments/e1-scripted/`.

Discovery: incremental delta propagation during parse (O(1) per claim)
is cheaper than cold fixpoint after parse (O(N²)). The live semantic
index thesis validated.

## DONE: E2 Multi-Operation Benchmark

20 sequential renames + dep queries. CNF wins at every scale:
3.05x at N=200, 2.19x at N=500, 1.43x at N=1000. Per-operation
speedup: 115-268x. Text cost is O(N) per-op, CNF is O(1).
Results in `docs/experiments/e2-multi-op/`.

## DONE: Homoiconic Rules (Rules as Claims)

Datalog rules are first-class entities in the claim graph. Rules
defined via MCP `define_rule` create entities with `rule-head-rel`
and `rule-source` claims. Rules are:
- Versionable (`supersede_rule` replaces a rule, old claims superseded)
- Queryable (`list_rules`, `inspect`, or Datalog query over rule claims)
- Composable (rule A references rule B's derived relation)

20 MCP tools (was 18: added `list_rules`, `supersede_rule`).
44 passing tests. See `docs/devlog/003-homoiconic-rules.md`.

## DONE: E3 Agent Comparison

18-operation benchmark across 5 phases: discovery, renames, custom
rule definition, sustained queries, schema evolution. CNF vs text.

CNF loses total wall time (0.24-0.53x) — fixpoint recompute after
rule definition is expensive. But Phase 4 (rename + query custom rule)
shows the real story: **115-1025x per-operation advantage**. CNF is
O(1) per query (matview cache hit), text is O(N²) (rebuild from scratch).

Crossover at ~11 operations (N=200). 50-op session: CNF wins 3.6x.
Results in `docs/experiments/e3-agent-comparison/`.

Capability gap: CNF agents define, evolve, and compose derived
relations as first-class claims. Text agents do ad-hoc computation.
See `docs/devlog/004-agent-comparison.md`.

## DONE: Incremental Rule Addition

`propagate-new-rule/prov!` evaluates new rules against the existing
matview incrementally. No full fixpoint recompute when the matview is
valid. Phase 3 at N=200: ~183ms → ~50ms. Total speedup: 0.53x → 0.77x.
Crossover dropped from ~11 to ~5-6 operations.

Tradeoff: for rules with O(N²) output (shared-dep at N=500: 10,399
tuples), delta propagation is more expensive than batch fixpoint.
Supersession still forces full recompute (by design — no rule-level
provenance). See `docs/devlog/005-incremental-rule-addition.md`.

## DONE: E4 Live Agent Session

Side-by-side transcript: 7-step refactoring task, CNF vs text.
Both agents compute identical results at every step (verified).

After incremental supersession: CNF wins total 3.26x (was 0.1x).
307x per-op sustained advantage. No crossover — CNF wins from start.

The qualitative gap: CNF agent built 3 composable, persistent,
inspectable rules. Text agent wrote 5 ad-hoc computations.
See `docs/experiments/e4-live-session/` and `docs/devlog/006-live-agent-session.md`.

## DONE: Incremental Rule Supersession

`try-supersede-incremental!` retracts the affected relation's tuples
and re-derives via the replacement rule. No full fixpoint recompute
when the head relation has no IDB dependents (typical case).

E4 Step 6: 256ms → 16ms (16x). E3 Phase 5 at N=200: 110ms → 3.5ms
(31x). CNF now wins total wall time at N=100 (1.95x, was 0.53x).
60 tests passing. See `docs/devlog/007-incremental-supersession.md`.

## DONE: E5 Arena — First Real Agent Comparison

Two real Claude agents, same task, same 20-function program. CNF agent
(42 calls, 191s) vs Text agent (8 calls, 82s). Both correct. Text wins
the single task. CNF builds persistent structural understanding.

Key finding: **the bottleneck shifted from compute to protocol**. The
engine is 100-1000x faster per-op, but the MCP interface forces 42
round-trips where 5 would do. Schema discovery alone was ~15 calls.
See `docs/experiments/e5-arena/` and `docs/devlog/008-interface-redesign.md`.

## DONE: Interface Redesign (Schema + Symbols + Batch)

Three changes targeting the real bottleneck (tool call count):
1. `parse_program` returns full schema (predicate names → IDs)
2. Bare symbols in queries resolve to named entities automatically
3. `batch` tool: multiple operations in one call

Predicted impact: 42 calls → ~5 for E5's task. 21 MCP tools (was 20).

## DONE: E6 Multi-Round Arena

Five sequential tasks, two real agents. Text wins total (12 vs 32
calls), but CNF wins tasks 2-5 (5 vs 7). Compounding thesis validated.
Schema discovery ate 13 of 27 task-1 calls. See `docs/experiments/e6-multi-round/`.

## DONE: E7 Interface Proof

Same E5 task with the new interface: **7 calls instead of 42** (6x
reduction). Schema in parse eliminates discovery. Batch combines rule
definitions + query into 1 call. Projected E6 total: ~11 (CNF) vs 12
(text). **CNF wins total for the first time.** See `docs/experiments/e7-interface-proof/`.

## DONE: E8 New Interface Arena

Real rematch with interface improvements active. CNF: 14 calls, ~127s.
Text: 3 calls, ~78s. Both correct. Interface cut CNF from 32→14, but
text agent also evolved (12→3) by front-loading all analysis into one
Python script.

Key insight: text wins when all questions are known upfront. CNF wins
in the incremental-questions scenario — matview answers in 1 call vs
re-analysis. The next test needs conditions that expose the real
advantage: larger codebase, emergent questions, mutations.
See `docs/experiments/e8-new-interface/`.

## DONE: E9 — Accumulated Knowledge at Scale

50 functions, 4 layers, 81 edges, 7 tasks with agent-initiated rename.
CNF: 10 MCP calls, ~136s. Text: ~6 calls, ~124s. Text wins 1.7x.

Closest result yet (was 5.3x in E5). Gap narrowing: 5.3x → 2.7x → 1.7x.
Marginal cost converges to ~1 call/task for both after setup. The
remaining gap is setup cost (rule definitions vs front-loaded Python).

The missing piece: incremental parse. Without it, mutations require
reset + full reparse, destroying accumulated rules. With it, mutations
flow through the claim graph and matviews auto-update — the scenario
where CNF should decisively win. Results: `docs/experiments/e9-evolving-codebase/`.

## LATER: Real Codebase Demo

Run the MCP server against a non-toy Racket project (50+ functions).
Show the full workflow: parse, discover, define rules, refactor,
evolve. Honest timing and capability assessment at real scale.

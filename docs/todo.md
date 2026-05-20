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

## NOW: Live Agent Session

Two actual Claude sessions doing the same refactoring task. The
benchmark numbers show the tool-level advantage. The live session
shows the workflow-level difference: what each agent attempts, how
it reasons, what it can't do.

**Done when:** transcript comparison with honest analysis.

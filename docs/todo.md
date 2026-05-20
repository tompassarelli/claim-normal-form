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

## DONE: Persistence Layer (Checkpoint/Restore + Daemon)

Built cross-session persistence for the claim graph:
- `checkpoint` tool: serializes all objects, values, claims, supersession
  history to JSON. `restore` tool: rebuilds full graph + ext table +
  built-in rules + user-defined rules (from claim-stored source) +
  matview. Round-trip verified end-to-end.
- Daemon mode (`--daemon PORT`): TCP server, auto-restores from checkpoint,
  serialized multi-client access via semaphore.
- Bridge mode (`--connect PORT`): stdio↔TCP proxy for Claude Code.
- 24 MCP tools (was 22: added `checkpoint`, `restore`).

## DONE: E10 — The Shared Substrate

Two sessions, same 50-function codebase. Session 1: both agents parse
and build understanding. Session 2: fresh context, 5 tasks composing
Session 1's analysis.

CNF: 6 calls, Text: ~5 calls. Text wins 1.2x — the closest yet, and
call count is now noise. The real finding:

The CNF agent INHERITED 3 rules from Session 1, INSPECTED them via
list_rules, QUERIED matviews it didn't build, got AUTO-UPDATED results
through a rename, and COMPOSED new rules on existing derived relations.

The text agent reimplemented everything from scratch. And got several
answers wrong (22 roots instead of 10, wrong biggest hub) because
one-off scripts are unvalidated. The matview is a tested artifact.

Call count is the wrong metric. The question is what the agent CAN DO.
Results: `docs/experiments/e10-shared-substrate/`.

## DONE: Transactions (Datomic-inspired)

Every claim now belongs to a transaction. Transactions add:
1. **Tx entities** — every `claim!` creates or joins a tx. Implicit
   (one per claim) or explicit (`begin-tx!`/`commit-tx!`). Queryable
   via `claim-tx`, `tx-claims`, `claims-since`, `all-txs`.
2. **Temporal queries** — `claims-visible-as-of` filters to claims
   that existed at tx seq N, respecting supersession as of that point.
   Datalog EDB: `as-of-triple`, `as-of-claim`, `tx-info`, `tx-claims-rel`.
3. **Batch atomicity** — `call-with-transaction` wraps multiple
   operations; hooks deferred to commit, full rollback on error via
   snapshot/restore of all mutable state. MCP `batch` gets `atomic` flag.

26 MCP tools (was 24: added `tx_log`, `current_tx_seq`). Serialization
format v2 preserves tx data; v1 imports get a synthetic tx. 72 tests
(13 new tx tests).

## DONE: Multi-Agent Concurrent Access

Daemon mode supports multiple TCP clients. Three pieces completed:

1. **Agent identity on transactions.** `set_agent` MCP tool sets
   the current agent name. All subsequent claims (implicit or explicit
   tx) are attributed. `tx_log` shows `agent: name`. Survives
   serialization. 27 MCP tools (was 26).

2. **E11: Multi-agent experiment.** Two agents on the same daemon
   building complementary understanding. Agent A (structural-analyst)
   defines trans-dep + shared-dep rules. Agent B (quality-checker)
   restores, inspects Agent A's rules, defines high-impact rule
   composing Agent A's derived relations. CNF 11 calls vs text ~8.
   Text still wins count, but the scenario is structurally impossible
   for text agents — no shared substrate to inherit or compose on.
   Discovery: queries within atomic batches read pre-mutation derived
   state (hooks deferred to commit). Results: `docs/experiments/e11-multi-agent/`.

3. **Concurrency refinement.** Current semaphore serializes entire
   requests — two simultaneous queries block each other. Fine for the
   experiment (sequential agents, shared graph). True parallelism needs
   read/write locking or MVCC. Not needed yet but could be a big unlock
   for real multi-agent workflows.

## DONE: MVCC (Snapshot Isolation)

Replaced the global semaphore and read/write lock in daemon mode with
MVCC. `snapshot-ctx` creates an independent deep copy of the claim
graph (all 13 struct hashes + mutable ext values). Daemon maintains a
"committed snapshot" that readers use without any lock.

- **Readers**: `parameterize` with committed snapshot, no lock needed.
  Multiple readers run truly concurrently with zero contention.
- **Writers**: serialized via semaphore on the live context. After each
  write, a new snapshot is created and published for future readers.
- **Isolation**: readers that started before a write complete on their
  snapshot unaffected. New readers see the write's effects.

11 read-only tools run lock-free. Writers serialize. 6 MVCC tests
verify snapshot independence, matview preservation, concurrent reads.

## DONE: Incremental Parse

Three new MCP tools: `add_function`, `remove_function`, `modify_function`.
30 MCP tools (was 27).

- `add_function`: parses a single function definition and adds it to the
  existing claim graph. Matview hooks fire incrementally.
- `remove_function`: finds the function entity by name, walks its expression
  tree, and invalidates all owned claims via supersession. Derived relations
  (fn-depends-on, contains-call) retract affected tuples automatically.
- `modify_function`: preserves the function entity ID (so other functions'
  call references still work), retracts old params + body, parses new
  definition reusing the entity. Can rename simultaneously.

15 lang tests (was 8). All 68 tests passing.

## DONE: Real Codebase Demo (E12)

100-function financial analytics program, 5 layers. Full workflow:
parse (37ms) → discover (245 edges) → define rules (trans-dep,
shared-dep, hub-pair) → refactor (rename, 0.1ms) → evolve via
incremental parse (add/modify/remove functions, rules survive).

Key numbers: 2399 objects, 1672 claims, 1655 transitive dep pairs,
firm-pnl depends on 62 of 100 functions. All queries <1ms after
materialization. Results: `docs/experiments/e12-real-demo/`.

## DONE: Package for External Use

README updated with full MCP server documentation:
- Quick start (stdio, daemon, bridge modes)
- Claude Code configuration (MCP settings JSON)
- Tool reference (30 tools across 8 categories)
- Key workflows (parse/query, custom rules, incremental edit,
  persistence, multi-agent collaboration)
- Updated performance numbers from E12 (100-function codebase)
- Updated test counts (88 tests across 8 files)

## DONE: Beagle Integration (Bridge Module)

`beagle-lang.rkt` — bridge from beagle's parser to CNF's claim graph.
Parses real beagle source via `(require beagle/private/parse)`, walks
AST structs, creates entities and claims. Beagle doesn't change.

Claim mapping implemented:
- `defn-form` → function entity + typed params + return type + body
- `defn-multi` → function entity (first arity) + arity count
- `def-form` → binding entity + type + value expression
- `defrecord` → record entity + typed fields with positions
- `call-form` → calls predicate (resolves to function entities)
- `if-form` → condition/then/else with has-child traversal
- `let-form` → bindings with scope, has-child traversal
- `fn-form` → anonymous function with params and body
- `match-form`, `cond-form`, `when-form`, `do-form` → has-child
- `for-form`, `loop-form`, `try-form` → has-child traversal
- `method-call`, `kw-access` → calls predicate
- `vec-form`, `map-form` → collection with children
- Other forms → entity with form-kind claim

18 predicates. Datalog rules: `contains-call` walks `has-child`
transitively, `fn-depends-on` derived from body + contains-call.

Rendering reconstructs beagle syntax from claims: typed params,
return types, call expressions, if/let/do/fn forms. Rename propagates
automatically through entity references.

Incremental operations: `add-beagle-function!`, `remove-beagle-function!`,
`modify-beagle-function!`. Same pattern as toy lang but walks beagle AST.

`parse-beagle-file!` reads `.bgl`/`.bclj` files directly (strips
`#lang` line automatically).

Upstream fix: `resolve-symbol` in cnf.rkt now checks both
`symbol-predicate-id` (kernel naming) and `name-pred` (graph naming),
with supersession filtering. Was a latent bug — entities named via
`give-name!` were invisible to `resolve-symbol`.

Tested against beagle's `examples/demo.bclj` (15 forms, records,
unions, enums, multi-arity, threading, match). 381 objects, 220 claims,
cross-function dependencies detected.

15 beagle-lang tests. 103 tests total across 9 files.

MCP server wired to beagle-lang: `parse_program`, `render`, `rename`,
`add_function`, `remove_function`, `modify_function` all use beagle's
parser and claim mapping. `fn-depends-on` rule filtered to form-kind
"defn" for accurate function-to-function dependencies.

## DONE: E13 — Beagle Bridge Demo

9-form financial analytics program in real beagle syntax (2 records,
7 functions with types, generics, if-let, let, fn, match). Parse 2.3ms →
565 objects, 384 claims. 7 direct deps, 15 transitive pairs.

Full workflow: parse → discover (fn-depends-on) → custom rules (trans-dep) →
materialize (15ms) → rename (0.04ms, propagates to 3 callers) → incremental
edit (add 0.9ms, modify+rename 1.2ms) → render round-trip.

30+ beagle form types handled in expression walker. Renderer reconstructs
typed params, return types, records, if/if-let, let, fn, match, call
expressions. Run `racket beagle-demo.rkt` to reproduce.

Results: `docs/experiments/e13-beagle-bridge/`.

## DONE: Python Bridge

`python-lang.rkt` — second language bridge, proving the pattern is
language-agnostic. Python source → `python3` subprocess (AST → JSON)
→ Racket bridge → claim graph. 14 predicates, 2 Datalog rules.

Parser helper: `python-ast-helper.py` (~390 lines) handles 30+ AST
node types via Python's `ast` module. Bridge: `python-lang.rkt`
(~550 lines) creates entities and claims from JSON.

Same incremental operations: `add-python-function!`,
`remove-python-function!`, `modify-python-function!`. Same renderer
pattern. 15 Python-specific tests.

Subprocess adds ~50ms per parse. Post-parse operations identical to
beagle — same engine, same speed. Results: `docs/experiments/e14-python-bridge/`.

## DONE: MCP Resources

Four resources exposed via `resources/list` and `resources/read`:
`cnf://summary`, `cnf://dependencies`, `cnf://functions`, `cnf://rules`.

Push structured data into agent context instead of requiring tool calls.
Eliminates the status/query/list_rules round-trips that dominated E5-E8.

## DONE: Language-Agnostic MCP Server

`mcp-server.rkt` auto-detects Python vs beagle from source syntax.
All 30 tools work with both languages. Single agent session can parse
and analyze code in either language through the same interface.

## DONE: E14 — Python Bridge Demo

Same financial analytics domain as E13, in Python. 2 classes, 7 typed
functions. Parse (55ms) → 542 objects, 338 claims → 7 direct deps,
15 transitive pairs → rename (0.03ms) → incremental edit (add + modify
+ rename). Run `racket python-demo.rkt` to reproduce.

## LATER: Concurrent Writers (Multi-Writer MVCC)

Current MVCC gives snapshot isolation for reads with serialized writes.
True multi-writer MVCC would allow multiple agents to mutate the claim
graph simultaneously, each seeing a consistent snapshot, with conflict
detection on commit.

Requires: write-set tracking per transaction, conflict detection
(overlapping write sets → abort), retry logic. The existing tx-seq
numbering is the foundation. Not needed until multiple agents are
actively mutating the same codebase in parallel.

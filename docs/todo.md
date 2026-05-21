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

## DONE: E15 — Correctness Evaluation (CNF vs Grep)

50-function Python codebase, 5 structural tasks with ground truth.
CNF correct on all 5. Grep wrong on all 5:

1. Transitive impact: CNF finds 17, grep finds 9 (misses 47%)
2. Rename safety: CNF 6 exact sites, grep has false positives from strings
3. Shadowed names: CNF resolves per-entity, grep conflates 5 name pairs
4. Dead code: CNF definitive (7 uncalled), grep unreliable
5. Full dep tree: CNF finds 21, grep finds 7 (misses 67%)

This is the experiment the reviewer asked for: not speed, correctness.
Results: `docs/experiments/e15-correctness/`.

## DONE: E16 — Agent Grounding Evaluation

45-function Python codebase, 10 tasks with ground truth. CNF correct
on 7/7 structural tasks. Text search wrong on 5, unprovable on 2.
Tasks 05–07 (local code changes) doable by both.

Key results:
- Rename subtotal: CNF 1 site / 0 FP, text 30 matches / 8+ FP
- Blast radius: CNF 23 affected, text misses 11 (48%)
- Full dep tree: CNF 25 functions, text misses 20 (80%)
- Cross-session: CNF 10/10, text 0/10 (structurally impossible)

See `experiments/e16-agent-grounding/` and
`docs/experiments/e16-agent-grounding/results.md`.

## DONE: E17 — Agent-in-the-Loop Evaluation

Both agents make actual code changes, both run the test suite.
4 tasks: rename subtotal, dead code removal, tax exemption, rename order_total.

Results: both pass all 26 original tests on every task. Hidden tests
(API contracts the test suite doesn't cover): CNF 30/30 (100%),
text 26/30 (87%).

Failures: text renames dict keys alongside function calls (Task 01),
misses dead code whose names appear as dict keys (Task 04). Tasks 05
and 09 are ties — CNF doesn't win on local changes or unique names.

See `experiments/e17-agent-in-the-loop/` and
`docs/experiments/e17-agent-in-the-loop/results.md`.

## DONE: F2 — Parallel Feature Construction (ClaimDesk)

Five agents build a CRM/helpdesk app (workflow, permissions, audit,
notifications, analytics). Mid-build requirement: archived tickets
are silent and excluded from active reports.

**Scripted experiment**: Git 9/14 integration tests (5 cross-cutting
bugs). CNF 14/14 (0 bugs). Bugs: notifications fire for archived,
analytics count archived as active, permissions miss archive action.

**Real Claude Code agents**: 8 Sonnet agents (4 git, 4 CNF) launched
in parallel with identical task specs. Git agents see base code only.
CNF agents see base + workflow.py + structural context from claim graph.

Result: **Git 9/14 (5 bugs), CNF 14/14 (0 bugs).** Same five failures
as scripted. The bugs are structural — they follow from the information
gap, not from agent randomness.

Agent-generated code saved in `experiments/f2-claimdesk/real-agents/`.
Full results: `docs/experiments/f2-claimdesk/results.md`.

## DONE: F3 — Live Graph Pipeline

Sequential agents, accumulated graph. Each agent's code parsed into
the CNF graph after writing; next agent queries the accumulated state.
Graph grows from 17 to 34 entities across 4 modules.

**Git 7/14 (5 cross-cutting bugs + 2 convention/spec issues).
CNF 13/14 (0 cross-cutting bugs, 1 policy decision).**

Cross-cutting result stable across F2 and F3: information-gap bugs
appear in every git run and never in CNF. Live graph pipeline
validated: parse → checkpoint → restore → query → parse new code.

Agent outputs: `experiments/f3-live-graph/git/` and `cnf/`.
Results: `docs/experiments/f3-live-graph/results.md`.

## DONE: F4 — Overlapping Edits

Agents modify shared files (config.py, workflow.py). Three agents
independently produce three different config.py files. Mid-run
requirement (on_hold status) added after Agent 1.

**Git 18/21 (3 on_hold failures, required manual merge of 3 config
versions). CNF 21/21 (sequential accumulation, no merge conflicts,
on_hold incorporated naturally).**

Three failure modes exposed: merge conflicts (3 independent config.py
versions), hidden dependencies (audit hooks depend on notification
agent's workflow fix), temporal divergence (on_hold added after git
agents forked).

Agent outputs: `experiments/f4-overlap/{git,cnf}/`.
Results: `docs/experiments/f4-overlap/results.md`.

## DONE: F5 — Coordination Curve

Eight agents, 28 tests, three tiers (3, 5, 8 agents). Git 25/28
(89%), CNF 28/28 (100%). All three git failures: temporal divergence
— on_hold mid-run requirement invisible to forked agents. The
escalation agent adds on_hold to config.ACTIVE_STATUSES but can't
add it to workflow.VALID_TRANSITIONS — the merged system is
internally inconsistent.

Across F2-F5: CNF holds at 100% (or 93% with one F3 policy decision)
while git ranges from 50% to 89%. All failures are structural.

See `docs/experiments/f5-curve/results.md` and
`docs/devlog/024-f5-coordination-curve.md`.

## DONE: F6 — Time to Correct App

Real Claude Code agents, wall clock to 28/28. Git 276s (parallel
build + 1 repair round). CNF 500s (sequential build, 0 repairs).
Git 1.8x faster. Parallelism beats correctness when the repair
loop is cheap. The repair agent fixed 6 failures in 56s — clear
error messages, local fixes, non-interfering.

CNF needs its own parallelism to compete on wall clock. Sequential
accumulation trades speed for correctness. At this scale, the
speed cost exceeds the correctness benefit.

See `docs/experiments/f6-time-to-correct/results.md` and
`docs/devlog/025-f6-time-to-correct.md`.

## DONE: F7 — Graph Necessity

18-module helpdesk app (4947 LOC), 49 integration tests from feature
spec, 7 edit sites across 4 files. Three-condition agent experiment:
grep-only, file-reading, graph-first.

Results: Same recall (6/7, 86%) across all conditions — the 7th site
is a latent crash bug only discoverable by execution. Graph precision
60% vs grep 35% (2.8x fewer false positives). Graph 11 tool calls vs
grep 35 (3.2x fewer). The graph doesn't help agents FIND more sites —
it helps them SKIP more non-sites and work more efficiently.

See `docs/experiments/f7-graph-necessity/results.md` and
`docs/devlog/027-f7-agent-experiment.md`.

## DONE: F8 — Parallel Race

Git-parallel vs CNF-parallel at 2 and 5 agent scales. Same ClaimDesk
app, 18 integration tests. All agents build in parallel — both
conditions take the same 26s for agent inference.

Results: CNF 3x faster (28s vs 82s projected). Git agents produce 4
cross-cutting bugs requiring a 56s repair round. CNF agents query the
shared graph via live graph accumulation and build correctly — zero
repair. The entire delta is repair cost.

The advantage compounds with scale: more agents → more bugs → more
repair rounds, while CNF's graph infrastructure stays constant (~2s).
At 10 agents, projected ~5x. At 20, ~7x.

See `docs/experiments/f8-parallel-race/results.md` and
`docs/devlog/028-f8-parallel-race.md`.

## DONE: F9 — Real Parallel Race

Real Claude Sonnet agents, parallel execution, wall clock measured.
Six agents (audit, escalation, analytics, notifications, comments,
permissions), 22 integration tests. Launched via `claude -p --model
sonnet --tools ""` — real LLM inference, no pre-written code.

Two runs. Git 18/22 → 22/22 after repair, both times. CNF 22/22,
both times. Same 4 structural bugs every run (notifications,
permissions, analytics, escalation). Mean: Git 68s (build + 48s
repair), CNF 34s (build, 0 repairs). CNF 2x faster.

Confirms F8's projected result with real agents. The bugs are
deterministic given the information gap — identical to F2/F8.

See `docs/experiments/f9-real-race/results.md` and
`docs/devlog/029-f9-real-race.md`.

## DONE: F10 — Live Graph Race

Real agents, live CNF daemon, graph-derived context from live queries.
Six agents, 22 integration tests. Daemon runs on localhost with Python
source parsed into the claim graph (1685 objects, 1130 claims, 11
Datalog rules). Six MCP bridges connect simultaneously via lightweight
Python bridge processes.

Coordinator queries the live graph for entity names, types, and
dependencies, formats 3357 chars of structural context. Same
correctness result: 20/22 CNF vs 16.5/22 git (mean first-pass).
Four information-gap bugs eliminated in every CNF run.

Key finding: direct agent graph queries work technically (all bridges
connect) but agents can't navigate the Datalog schema — they use wrong
predicate names and get empty results. Coordinator-mediated context is
the practical approach. Higher-level query tools are the next step.

See `docs/experiments/f10-live-race/results.md` and
`docs/devlog/030-f10-live-race.md`.

## DONE: F11 — Agent Tools

Graph-only tools, no file access. Four conditions tested:

| Condition | Info-gap bugs | First-pass |
|-----------|--------------|------------|
| Git       | 4/4          | 16/22      |
| Wrapped   | 1/4          | 17/22      |
| Raw       | 4/4          | 15/22      |
| Discover  | **0/4**      | **20/22**  |

First 0/4 info-gap result. Three things required:

1. **Tool abstraction**: `discover("TERMINAL_STATUSES")` returns
   values + module + import in one call (vs 4-step Datalog chain)
2. **Prompt engineering**: "values differ from what you would guess"
   blocks agents from skipping the tool call
3. **MVCC bug fix**: `reset-store!` replaced current-ctx parameter,
   making writes invisible to new connections. Only affects
   multi-connection scenarios (F11 is the first). Prior experiments
   unaffected.

See `docs/devlog/032-f11-agent-tools.md` and
`experiments/f11-agent-tools/results.json`.

## NOW: Graph Runtime — The Graph Is the Program

The graph is no longer a mirror of source code. It IS the program.
Agents construct program shapes as claims. A reducer evaluates the
claim graph directly. Files become projections, not sources.

Three layers, one graph:
1. **Claim store** — canonical program representation as EAV triples
2. **Datalog** — derived semantic truth (types, deps, validity)
3. **Reducer** — evaluates executable claim-graph terms

### DONE: Core calculus

literal, var, lambda, apply, binop, let, if. Provenance-preserving
reductions. Environment-based closures. Structural bindings. 11 tests.
Victory condition met: `((λ x (+ x 1)) 5) → 6` with full provenance.
See `docs/devlog/033-graph-is-the-program.md`.

### DONE: Letrec + fuel

`letrec` via two-phase env patching. Shared fuel budget with queryable
exhaustion claims. `exn:fuel` exception carries the incomplete node ID.
Factorial(5) = 120. Infinite loop bounded without hanging. 15 tests.
See `docs/devlog/034-letrec-and-fuel.md`.

### DONE: Unified graph (lang.rkt → graph-eval nodes)

lang.rkt constructs graph-eval nodes directly (`lit!`/`var!`/`binop!`/`app!`).
Compat shim (`expr!`/`run!`/`eval-step!`) deleted. One representation,
two uses: same nodes for Datalog analysis and graph-eval reduction.
Parse → render → evaluate → query dependencies, all against one graph.
17 lang tests (was 8), 376 total. See `docs/devlog/034-letrec-and-fuel.md`.

### DONE: MCP evaluate tool + eval-function!

Agent loop closed. `evaluate` MCP tool runs `graph-eval` against parsed
functions and records the outcome as queryable claims (eval-run entity
with status, result, fuel, reason, error-node). `eval-function!` builds
curried lambdas, mutual env with placeholder patching, evaluates the call.

Runtime failure is graph data, not just an exception. 31 MCP tools
(was 30). 23 lang tests (was 17), 396 total.
See `docs/devlog/034-letrec-and-fuel.md`.

### DONE: E20 — Graph-Native Agent Loop

10-step demo: parse → query deps → evaluate → rename → re-evaluate →
add function → evaluate across boundaries → break (div/zero) → diagnose
error as graph data → fix → re-evaluate. All against one claim graph.
6 eval runs retained as queryable entities. Run
`racket experiments/e20-graph-loop.rkt`. See
`docs/experiments/e20-graph-loop/results.md`.

### DONE: E21 — Live Agent Race

Head-to-head: text agent (files + shell + eval-helper) vs graph agent
(MCP tools). Same Sonnet model, same 10-step task: parse → reproduce
div-by-zero → add safe-div → wire it in → verify → query deps → rename
→ verify post-rename → query error history.

Both agents completed all 10 steps. Text: 64.7s. Graph: 103.6s.

The graph agent's structural advantage showed on step 10 (error
history from step 3 still queryable as run entity 1240 with status,
reason, function ID) and step 8 (semantic rename — one operation, all
call sites auto-update). The text agent correctly identified error
history as architecturally impossible ("cross-invocation history is an
architectural limitation of the in-memory store").

Text wins on speed at toy scale. Graph wins on capabilities that
compound with scale.

Bug found and fixed during the race: server.rkt `add_function` and
`modify_function` didn't route to cnf toy lang (only Python/Beagle).
Also added `if` and `=` to the toy lang parser (eval already supported
both). 396 tests green.

See `experiments/e21-graph-race/` and
`docs/experiments/e21-graph-race/results.md`.

### DONE: E22 — Semantic Rename at Scale

58 functions, name-ambiguity traps (5 trap function names, 4 parameter
shadows, 9 true call sites). Rename `helper` → `safe-helper`.

Text: 157.3s. Graph: 138.2s. **Graph faster for the first time.**

Both agents scored perfectly: 9/9 call sites, 0 false positives, all
trap names preserved, all parameters untouched. The graph rename is
correct by construction (one entity operation); the text rename required
careful structural understanding of the 58-function program.

Error history: graph retains eval-run entity 25674 (division by zero
from step 3), queryable after fix + rename. Text has no mechanism.

Bug found: `resolve-fn-name` couldn't distinguish function entities from
parameter entities sharing the same name. Fixed via `position-pred`
filtering. Only surfaced at scale with name collisions.

Speed crossover: E21 (5 fn) text 1.6x faster → E22 (58 fn) graph 1.1x
faster. Text rename cost scales O(N); graph rename cost is O(1).

See `experiments/e22-semantic-rename/` and
`docs/experiments/e22-semantic-rename/results.md`.

### DONE: E23 — Concurrent Agents

Two agents, overlapping tasks, 51-function program. Agent A adds safe
division (8 functions guarded). Agent B renames helper → utility (11
call sites). Five overlap functions need both changes.

Graph: 104.5s. Text: 137.7s. Both correct. Graph 1.3x faster.

Speed trend: E21 text 1.6x faster → E22 graph 1.1x faster → E23
graph 1.3x faster. Entity-level operations compound.

Graph agents used independent servers (not shared daemon). Daemon MVCC
has a cross-connection snapshot visibility bug — snapshots published by
one connection aren't visible to subsequent connections. Blocks the
true shared-graph concurrent coordination test.

Text agents accidentally edited the same file (best-case coordination)
but were still slower. Error history: graph queryable (run 14595),
text not retained.

See `experiments/e23-concurrent-agents/` and
`docs/experiments/e23-concurrent-agents/results.md`.

### DONE: Fix daemon MVCC cross-connection bug

The committed snapshot box was clobbered when non-tool messages
(initialize, ping, notifications) from new connections fell to the
write-path else branch and overwrote committed with the new thread's
stale context. Write tools from new connections also operated on stale
thread-local state instead of committed.

Fix: restructured daemon handler from 2-branch if/else to 3-branch
cond. Read-only tools parameterize from committed. Write tools take
semaphore, deep-copy committed into working context, process, save
snapshot back. Non-tool messages parameterize from committed without
updating it. Test: `tests/test-daemon-mvcc.py` — Connection A parses,
Connection B sees A's state, Connection B writes build on A's state,
Connection C sees accumulated state.

### DONE: E23b — Shared daemon re-run

Both agents on same daemon. Graph: 0 conflicts, 26/26 verification,
both changes integrated (`(safe-div (utility a b) b)` in overlap zone).
Text (fixed isolation): 4 conflicts, definition lost in merge. MVCC
witness: fresh TCP connection sees pre-agents 2474 objects → post-agents
24714 objects. Error history (run 35249) queryable by fresh connection.

See `experiments/e23-concurrent-agents/` and
`docs/experiments/e23-concurrent-agents/results.md`.

### OPEN: Totality as a per-node queryable property

Fuel is scaffold. It answers "can the evaluator avoid hanging?" not
"does this program terminate?" The strongest version classifies each
node: provably total, fuel-bounded, effectful, unknown. That makes
"which parts are guaranteed vs empirical?" a query the substrate can
answer — a property no normal language has.

Not building now. Holding the question open. The fuel-exhaustion claim
infrastructure is already the skeleton of this feature.

## LATER: BEAM Runtime

CNF is the data model. Datalog is the reasoning layer. BEAM is the
concurrency substrate. Entity/process/message maps onto
program-entity/claim/update. Each entity serializes its own claim
updates locally while the whole system remains massively parallel.

Not needed to prove the thesis. Needed when the question shifts from
"does the claim model work?" to "can N agents use it simultaneously
at production scale?"

## LATER: Concurrent Writers (Multi-Writer MVCC)

Current MVCC gives snapshot isolation for reads with serialized writes.
True multi-writer MVCC would allow multiple agents to mutate the claim
graph simultaneously, each seeing a consistent snapshot, with conflict
detection on commit.

Requires: write-set tracking per transaction, conflict detection
(overlapping write sets → abort), retry logic. The existing tx-seq
numbering is the foundation. Not needed until multiple agents are
actively mutating the same codebase in parallel.

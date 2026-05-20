# Claim Normal Form

Shared semantic substrate for parallel software construction.

## The thesis

Software construction doesn't scale with agent count because
coordination cost dominates:

```
1 agent  → productive
2 agents → coordination overhead
5 agents → merge hell
```

The cost comes from rediscovery, inconsistent assumptions, hidden
dependencies, and local-only cognition. **CNF attacks exactly those
things.** The claim: shared semantic state makes software construction
composable across many concurrent agents — the coordination curve
flattens instead of exploding.

## The problem: private cognition

When multiple agents build software in parallel, each agent
understands the program privately — which functions exist, what calls
what, what states are possible. That understanding dies when the
session ends. The next agent starts from scratch. The bugs that
result are not in any single module. **The failures are in the gaps
between features** — each module is correct in isolation but
inconsistent with others.

This is not a testing problem. You cannot test for states you don't
know exist. An analytics agent can't exclude archived tickets from
active counts if it doesn't know the archived state exists. A
permissions agent can't gate the archive action if it never saw the
workflow module. The test suite passes because each feature is
self-consistent. The bugs are in the gaps.

The enemy is not text, not grep, not git. The enemy is **cognition
trapped inside isolated agent sessions**.

## What CNF does

CNF externalizes reasoning into durable shared structure.

Instead of treating source code as text, CNF treats it as claims about
stable identities. A function is an entity with a current name claim,
not a string. A call site points at the entity, not at matching
characters. This model persists across sessions, spans agents, and
updates incrementally as the program changes.

The value proposition is the same as a type system: not "catch trivial
errors" but give the agent a stable model to reason against while the
program is changing. Types stabilize reasoning during construction.
CNF stabilizes coordination during collaboration.

**[How CNF works](docs/overview.md)** — a concrete walkthrough.

## Evidence

### F2: Parallel feature construction

[Five agents build a CRM app](docs/experiments/f2-claimdesk/results.md)
— workflow, permissions, audit, notifications, analytics. The features
cross-cut: notifications must suppress for archived tickets, analytics
must exclude them from active counts, permissions must include the
archive action.

| | Git | CNF |
|--|--:|--:|
| Integration tests | **9/14** | **14/14** |
| Cross-cutting bugs | **5** | **0** |

The git agents are not wrong. They are locally rational — each builds
a correct module from the information available. The bugs emerge from
fragmented world models. The CNF notification agent imported
`TERMINAL_STATUSES` from the workflow module because the claim graph
told it those entities exist. The git notification agent guessed
terminal states from domain intuition (`{"closed", "resolved"}`) and
missed `"archived"` entirely. Not an intelligence difference. Not a
prompt difference. One system shared semantic structure; the other
relied on local reconstruction.

Replicated across two runs with real Claude Code agents (16 agents
total). The four structural bugs appear in every git run and never
in any CNF run.

### F3: Live graph accumulation

[Sequential agents, accumulated graph](docs/experiments/f3-live-graph/results.md).
Each agent's code is parsed into the live CNF graph after it finishes.
The next agent inherits all prior entities — the graph grows from 17
to 34 entities across the pipeline.

| | Git | CNF |
|--|--:|--:|
| Integration tests | **7/14** | **13/14** |
| Cross-cutting bugs | **5** | **0** |

Same five information-gap bugs in git. CNF's single failure: the
permissions agent *found* `archive_ticket` in the graph but gave
agents the permission too (test expects admin-only). A policy judgment
made with full information — categorically different from the git
failure where the agent doesn't know archive exists at all.

### F4: Overlapping edits

[Agents modify the same files](docs/experiments/f4-overlap/results.md)
— shared config, shared hooks, mid-run requirement change. Three
agents independently modify `config.py`. A new status (`on_hold`)
is added after the first agent finishes.

| | Git | CNF |
|--|--:|--:|
| Integration tests | **18/21** | **21/21** |
| Config merge conflicts | **3 versions** | **0** |
| Mid-run requirement handled | **no** | **yes** |

Even with a perfect manual merge (no human error in conflict
resolution), git agents miss the mid-run requirement entirely —
they forked before `on_hold` existed. CNF agents see the updated
graph and incorporate it naturally. The merge problem scales
quadratically with agent count; sequential accumulation is O(N).

### E19: Coordination cost

[Five agents on a 45-function codebase](docs/experiments/e19-coordination/results.md).
Each agent has a real task: map structure, rename, remove dead code,
add a feature, audit.

| | Git | CNF |
|--|---:|---:|
| Wasted on rediscovery | **50 ops (56%)** | **0 (0%)** |
| Dead code correctly identified | 5/7 | 7/7 |
| Downstream edit silently broken | yes | no |

Regex rename damages downstream work: renames the function *and* an
unrelated parameter sharing the name. A later edit fails silently.
Tests pass. CNF renames the entity — one claim. The parameter entity
is untouched.

### The experiment arc

20 experiments tracked the evolution. Key inflection points:

- **E15–E16**: CNF answers structural queries correctly (entity
  resolution, transitive closure, shadowed names). Text search gets
  them wrong. Not faster — *correct*.
- **E17–E18**: Both agents pass all tests. Hidden contract tests:
  CNF 30/30, text 26/30. Rope (real semantic tool) ties CNF on
  single-language rename but provides no persistent state, no rule
  engine, no cross-session memory.
- **E19**: Shared model eliminates 56% rediscovery *and* prevents
  cascading correctness failures.
- **F2**: Construction, not maintenance. The cross-cutting bugs
  are structural — they follow from the information gap, not from
  agent randomness.
- **F3**: Live graph accumulation. Same correctness result, but the
  context arrives via live MCP queries, not static prompt injection.
  The infrastructure for scaling agent count.
- **F4**: Overlapping edits. Agents modify the same files. Git
  produces merge conflicts and misses mid-run changes. CNF
  accumulates cleanly.

See the full [experiment arc](docs/experiments/README.md).

## Architecture

```
cnf-lib/
  main.rkt             Public API — (require cnf) re-exports core modules
  server.rkt           29 MCP tools over JSON-RPC 2.0 — the agent control surface
  lang.rkt             Toy language bridge — (require cnf/lang)
  racket.rkt           Racket bridge (minimal) — (require cnf/racket)
  python.rkt           Python bridge — (require cnf/python)
  beagle.rkt           Beagle bridge — (require cnf/beagle)
  private/
    kernel.rkt         Entity/Value/Claim kernel — objects, claims, indexed lookups
    datalog.rkt        Semi-naive Datalog — derived facts, materialized views, delta propagation
    eval.rkt           Graph evaluator — Datalog finds redexes, claims record results
    graph.rkt          Names, supersession, rename, dependency tracking
    schema.rkt         Ergonomic CRUD — entity/claims, lookup, find-by, update
    lang.rkt           Toy language — parse/render/rename round-trip
    racket.rkt         Racket bridge — define, struct, let, lambda, cond (no macros)
    python.rkt         Python bridge — AST via subprocess, 30+ node types, 14 predicates
    beagle.rkt         Beagle bridge — real typed Lisp, 30+ form types, 18 predicates
cnf-test/
  tests/               11 test files, 379 tests
cnf/
  info.rkt             Meta package — (define implies '("cnf-lib"))
```

Three language bridges prove the pattern is language-agnostic. Adding a
new language means writing a frontend that maps its AST into entities
and claims. Dependency queries, rename propagation, history, MCP tools,
and materialized views are shared infrastructure.

## The ontology

```
Object = addressable identity
Entity = object only           (entity!)
Value  = object + literal      (value!)  — interned, canonical
Claim  = object + (l p r)      (claim!)  — itself an object
```

The fact shape is `(l p r)` — each slot is an object. This is not EAV
with different names. In EAV, the row is an implementation detail. In
CNF, the claim itself is an object: it can be named, superseded,
explained, attributed to an agent, assigned a transaction, or used as
the subject of later claims. Reification is the default, not a bolt-on.

## Quick start

```bash
# Prerequisites: Racket 8.x, Python 3.x (for Python bridge)

# Install
git clone https://github.com/tom/cnf-racket && cd cnf-racket
raco pkg install cnf/            # meta package — installs cnf-lib + deps

# Beagle bridge requires beagle-lib (optional):
#   git clone https://github.com/tom/beagle && raco pkg install beagle/beagle-lib/

# Verify
raco test cnf-test/tests/

# Use as a library
racket -e '(require cnf) (displayln (make-cnf-ctx))'

# MCP server
racket cnf-lib/server.rkt               # stdio mode
racket cnf-lib/server.rkt --daemon 7888 # daemon mode (multi-client, MVCC)
racket cnf-lib/server.rkt --connect 7888 # bridge to running daemon
```

Claude Code MCP configuration (`.claude/settings.json`):

```json
{
  "mcpServers": {
    "cnf": {
      "command": "racket",
      "args": ["/path/to/cnf-racket/cnf-lib/server.rkt"]
    }
  }
}
```

## Documentation

| Doc | Contents |
|-----|----------|
| **[How CNF works](docs/overview.md)** | Concrete walkthrough — function as claims, rename, deps, agents |
| **[API reference](docs/api.md)** | Kernel, Datalog, eval, schema, graph, lang layer APIs |
| **[MCP server](docs/mcp.md)** | 29 tools, MCP Resources, workflows, daemon mode |
| **[Language bridges](docs/bridges.md)** | Racket, Python, and Beagle bridges, adding new languages |
| **[Performance](docs/performance.md)** | Benchmarks, honest limitations |
| **[Specification](specification.md)** | Full formal spec |
| **[Experiments](docs/experiments/)** | 19 experiments (E1–E19) with raw results |
| **[Devlog](docs/devlog/)** | 20 entries — discoveries, direction changes, honest numbers |
| **[Roadmap](docs/todo.md)** | What's done, what's next |

## Tests

379 tests across 11 files:

```bash
raco test cnf-test/tests/     # run all
```

## Limitations and what's next

F2/F3 are existence proofs, not throughput benchmarks. They establish
that shared semantic state eliminates information-gap bugs during
parallel construction. The important open question is whether this
compounds: does CNF throughput scale near-linearly with agent count
while git throughput plateaus? That requires experiments with
overlapping concurrent edits, not just separate files — and that's
the target for F4.

Benchmarks are at 50–200 functions. The correctness advantage is
structural (entity references vs string matching) and doesn't depend
on scale, but performance at large scale is unproven. Materialization
cost scales with output size. Python bridge adds ~50ms subprocess
overhead per operation.

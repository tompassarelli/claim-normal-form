# Claim Normal Form

A semantic working copy for coding agents.

Instead of treating source code as text, CNF treats it as claims about
stable identities. A function is not the string `"add"`. It is an
entity with a current name claim. A call site points at the function
entity, not at matching characters. Renaming `add` to `sum_two` is one
new claim, not a repository-wide string edit.

**[How CNF works](docs/overview.md)** — a concrete walkthrough of how
a function becomes claims, why rename is O(1), and what this means for
agents.

## The tests passed. The edit was wrong.

[E17](docs/experiments/e17-agent-in-the-loop/results.md) compares two
agents making code changes on the same 45-function Python codebase.

Both agents passed the visible 26-test suite on every task. But hidden
API-contract tests exposed the difference:

| Agent workspace | Visible tests | Hidden contract tests |
|---|---:|---:|
| CNF-backed agent | 26/26 on every task | **30/30 (100%)** |
| Text-backed agent | 26/26 on every task | **26/30 (87%)** |

The failures were structural: the text-backed agent renamed dictionary
keys along with function calls, and missed dead code whose names
appeared in data keys. CI stayed green because the visible tests did
not cover downstream API contracts. CNF avoided those errors because
references point to stable entities, not matching strings.

On local code changes, both approaches tied. CNF is not magic sauce for
all programming. It wins specifically on structural tasks: rename
safety, dead code removal, dependency-aware edits, and API-contract
preservation.

### The proof stack

- [E15](docs/experiments/e15-correctness/results.md): CNF answers
  structural queries correctly; text search does not.
- [E16](docs/experiments/e16-agent-grounding/results.md): CNF handles
  structural tasks correctly (7/7); text search is wrong or unprovable
  (7/7).
- [E17](docs/experiments/e17-agent-in-the-loop/results.md): CNF-backed
  agents make more correct structural edits; text-backed agents pass CI
  while breaking hidden contracts.

### Cross-session memory

Every agent session wakes up with amnesia and re-derives the project
from text. CNF's rules, derived facts, transactions, and agent actions
are all claims in the graph. A second agent restores the first agent's
semantic work instead of rebuilding context from files. Rename
propagates through the restored graph automatically.

This is structurally impossible with text tools — there is no shared
semantic substrate to persist, inherit, or compose on. E16 task 10
scores 10/10 for CNF and 0/10 for text.

See the full [experiment arc](docs/experiments/README.md) (17
experiments, E1–E17).

## Architecture

```
cnf.rkt            Entity/Value/Claim kernel — objects, claims, indexed lookups
datalog.rkt        Semi-naive Datalog — derived facts, materialized views, delta propagation
eval.rkt           Graph evaluator — Datalog finds redexes, claims record results
graph.rkt          Names, supersession, rename, dependency tracking
schema.rkt         Ergonomic CRUD — entity/claims, lookup, find-by, update
lang.rkt           Toy language bridge — parse/render/rename round-trip
beagle-lang.rkt    Beagle bridge — real typed Lisp, 30+ form types, 18 predicates
python-lang.rkt    Python bridge — AST via subprocess, 30+ node types, 14 predicates
mcp-server.rkt     30 MCP tools over JSON-RPC 2.0 — the agent control surface
```

Two language bridges prove the pattern is language-agnostic. Adding a
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
racket mcp-server.rkt           # stdio mode
racket mcp-server.rkt --daemon 7888   # daemon mode (multi-client, MVCC)
racket mcp-server.rkt --connect 7888  # bridge to running daemon
```

Claude Code MCP configuration (`.claude/settings.json`):

```json
{
  "mcpServers": {
    "cnf": {
      "command": "racket",
      "args": ["/path/to/cnf-racket/mcp-server.rkt"]
    }
  }
}
```

CNF exposes the graph over MCP, so agents can parse programs, query
dependencies, rename entities, define Datalog rules, checkpoint state,
and resume across sessions — without rebuilding context from text.

## Demos

```bash
python3 experiments/e17-agent-in-the-loop/run-eval.py  # E17: agent-in-the-loop, hidden tests
racket experiments/e16-agent-grounding/run-eval.rkt    # E16: 10-task agent grounding eval
racket e15-eval.rkt      # E15: correctness eval — CNF vs grep on 5 tasks
racket python-demo.rkt   # E14: Python bridge — parse, deps, rename, incremental edit
racket beagle-demo.rkt   # E13: Beagle bridge — real typed Lisp, full workflow
racket lang-demo.rkt     # Toy language — thesis demonstration
racket demo.rkt          # Graph layer — rename, dependency, incremental recompute
```

## Documentation

| Doc | Contents |
|-----|----------|
| **[How CNF works](docs/overview.md)** | Concrete walkthrough — function as claims, rename, deps, agents |
| **[API reference](docs/api.md)** | Kernel, Datalog, eval, schema, graph, lang layer APIs |
| **[MCP server](docs/mcp.md)** | 30 tools, MCP Resources, workflows, daemon mode |
| **[Language bridges](docs/bridges.md)** | Beagle and Python bridges, adding new languages |
| **[Performance](docs/performance.md)** | Benchmarks, honest limitations |
| **[Specification](specification.md)** | Full formal spec |
| **[Experiments](docs/experiments/)** | 17 experiments (E1–E17) with raw results |
| **[Devlog](docs/devlog/)** | 20 entries — discoveries, direction changes, honest numbers |
| **[Roadmap](docs/todo.md)** | What's done, what's next |

## Tests

118 tests across 10 files:

```bash
racket cnf-test.rkt           # 11 kernel
racket datalog-test.rkt       # 16 datalog (incl. incremental rule add/supersede)
racket eval-test.rkt          # 6 evaluator
racket demo-test.rkt          # 8 graph layer
racket schema-test.rkt        # 10 schema
racket lang-test.rkt          # 15 lang (incl. incremental parse)
racket tx-test.rkt            # 16 transactions (incl. agent identity)
racket rwlock-test.rkt        # 6 MVCC snapshot isolation
racket beagle-lang-test.rkt   # 15 beagle bridge
racket python-lang-test.rkt   # 15 python bridge
```

## Honest limitations

- Materialization cost scales with output size. Rules producing O(N²)
  tuples can take seconds at N=100.
- `modify-function!` at 584ms worst case (retract + reparse + rematerialize).
- Dependency queries via Datalog are slower than grep for simple cases.
  The advantage is correctness (complete transitive closure) and
  persistence (rules compose, matviews cache).
- Python bridge adds ~50ms per operation from subprocess overhead.
- Benchmarks are at 50–200 functions, not 50,000. The correctness
  advantage is structural (entity references vs string matching) and
  doesn't depend on scale, but performance at large scale is unproven.
- History falls out naturally from supersession — it's cheap and
  built in, but not zero-cost.

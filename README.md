# Claim Normal Form

A semantic working copy for coding agents.

Text search can find strings. CNF can answer what the program means.

Instead of treating source code as text, CNF treats it as claims about
stable identities. A function is not the string `"add"`. It is an
entity with a current name claim. A call site points at the function
entity, not at matching characters. Renaming `add` to `sum_two` is one
new claim, not a repository-wide string edit.

Functions, names, parameters, calls, dependencies, history, and agent
actions are all addressable objects in one graph. Text becomes a
projection of the graph, not the source of truth.

**[How CNF works](docs/overview.md)** — a concrete walkthrough of how
a function becomes claims, why rename is O(1), and what this means for
agents. Start here.

## Text search is not program understanding

AI coding agents answer structural questions by searching text: what
calls this function, what breaks if it changes, what should be renamed,
what is dead code, what did a previous agent already learn?

[E16](docs/experiments/e16-agent-grounding/results.md) tests those
questions on a 45-function Python codebase with ground truth.

**CNF answered 7/7 structural tasks correctly.** Text search was wrong
on 5 and unable to prove correctness on 2.

| Task | CNF | Text search |
|------|-----|-------------|
| Rename `subtotal` (call sites only) | **1 site, 0 false positives** | 30 matches, 8+ false positives |
| Blast radius of `round_cents` | **23 affected** | misses 11 (48%) |
| Disambiguate shadowed names | **per-entity resolution** | conflates all |
| Dead code detection | **7 definitive** | 3 of 7 unprovable |
| Full dep tree of `full_report` | **25 functions** | misses 20 (80%) |
| Rename `order_total` (not `total()`) | **3 sites, 0 false positives** | 10 matches, 4+ false positives |
| Cross-session memory | **10/10** | 0/10 (structurally impossible) |

The result is not that CNF is faster than grep. The result is that text
search does not represent identity. On transitive-impact tasks, text
search missed 48–80% of affected functions and produced false positives
on every rename.

Tasks 05–07 (local code changes) are doable by both — CNF is not magic
sauce for all programming. CNF wins where stable identity, dependency
closure, and cross-session structure matter.

### Cross-session memory

Every agent session wakes up with amnesia and re-derives the project
from text. CNF's rules, derived facts, transactions, and agent actions
are all claims in the graph. A second agent restores the first agent's
semantic work instead of rebuilding context from files. Rename
propagates through the restored graph automatically.

This is not an optimization. It is structurally impossible with text
tools — there is no shared semantic substrate to persist, inherit, or
compose on. E16 task 10 scores 10/10 for CNF and 0/10 for text.

[E17](docs/experiments/e17-agent-in-the-loop/results.md) goes further:
both agents make actual code changes and run the test suite. **Both pass
all 26 tests on every task.** The difference only appears in hidden
tests checking API contracts: CNF 30/30 (100%), text 26/30 (87%). The
text agent renames dict keys alongside function calls — CI passes, but
downstream consumers break.

See also [E15](docs/experiments/e15-correctness/results.md) and the
full [experiment arc](docs/experiments/README.md).

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

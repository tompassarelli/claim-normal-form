# Claim Normal Form

A structural reasoning scaffold for coding agents.

Instead of treating source code as text, CNF treats it as claims about
stable identities. A function is not the string `"add"`. It is an
entity with a current name claim. A call site points at the function
entity, not at matching characters. Renaming `add` to `sum_two` is one
new claim, not a repository-wide string edit.

**[How CNF works](docs/overview.md)** — a concrete walkthrough of how
a function becomes claims, why rename is O(1), and what this means for
agents.

## The problem

Coding agents work on text. Their understanding of a program — which
functions exist, what calls what, what depends on what — is private
cognition that dies when the session ends. The next agent starts from
scratch: re-reads every file, re-greps every symbol, re-derives every
dependency. This isn't a performance problem. It's a correctness
problem.

When Agent A renames a function via regex, it also renames unrelated
parameters that happen to share the name. Agent B arrives later to add
a feature, but Agent A's rename silently changed the code Agent B's
edit targets — the edit fails silently, the test suite doesn't catch
it, and nobody knows until production.

Text-based coordination shares *artifacts*. It doesn't share
*understanding*. Every agent reasons alone, from scratch, against
strings.

## What CNF provides

CNF gives agents a shared structural model of the program that
persists while the program changes. The model has four layers:

1. **Program facts** — "function A calls B", "entity X has parameter
   Y." Produced by parsing source into the claim graph.
2. **Derived facts** — "A transitively depends on C", "X is dead
   code." Produced by Datalog rules, materialized and cached.
3. **Agent actions** — "Agent A renamed this entity", "Agent B removed
   that function." Recorded in the transaction log.
4. **Composable rules** — Agent B defines new rules that compose on
   Agent A's derived relations. Knowledge compounds across sessions.

This is the same value proposition as a type system: not "catch trivial
errors" but "give the agent a stable model to reason against while the
program is changing." A type checker prevents invalid compositions
during construction. CNF prevents invalid coordination during
collaboration — rename only the function entity, not the parameter
entity. Identify dead code by entity references, not string matching.
Know the blast radius of a change before making it.

## Evidence

[E19](docs/experiments/e19-coordination/results.md) puts five agents
on a 45-function codebase (6 modules). Each agent has a real task:
map structure, rename a function, remove dead code, add a feature,
audit the result.

| | Git | CNF |
|--|---:|---:|
| Total discoveries | 89 | 6 |
| Wasted on rediscovery | **50 (56%)** | **0 (0%)** |
| Dead code correctly identified | 5/7 | 7/7 |
| Downstream edit silently broken | yes | no |

The rediscovery numbers matter, but the correctness failures matter
more. In the git condition:

- **Regex rename damages downstream work.** Agent B renames function
  `subtotal` → `compute_subtotal` via `\bsubtotal\b`. This also
  renames the `subtotal` *parameter* in an unrelated function. Agent D
  later tries to modify that function — the edit fails silently because
  the parameter name no longer matches. The test suite passes. Nobody
  notices.

- **Dead code detection gets false positives.** Grepping for function
  names finds string matches in dict keys and comments. Agent C keeps
  2 dead functions alive because their names appear in unrelated
  contexts. CNF checks entity references: zero false positives.

In the CNF condition, Agent B renames the function *entity* — one name
claim. The parameter entity (a different object that happens to share
the name) is untouched. Agent D's edit succeeds. Agent C queries
callers via the materialized dependency graph: 7/7 dead functions
identified. Each agent inherits all prior agents' structural knowledge
via one checkpoint restore.

Both conditions pass the same 26 tests. The difference is in
structural correctness that the test suite can't cover.

### The experiment arc

19 experiments tracked the evolution from speed benchmarks to
structural correctness to multi-agent coordination. The key
inflection points:

- **E15–E16**: CNF answers structural queries correctly (entity
  resolution, transitive closure, shadowed names). Text search gets
  them wrong. Not faster — *correct*.
- **E17–E18**: Both agents pass all tests. CNF gets 30/30 hidden
  contract tests; text gets 26/30. Rope (real semantic tool) ties
  CNF on single-language rename, but provides no persistent state,
  no rule engine, no cross-session memory.
- **E19**: Shared structural model eliminates redundant work *and*
  prevents cascading correctness failures across agents.

See the full [experiment arc](docs/experiments/README.md) (E1–E19).

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

## Honest limitations

- Benchmarks are at 50–200 functions, not 50,000. The correctness
  advantage is structural (entity references vs string matching) and
  doesn't depend on scale, but performance at large scale is unproven.
- Materialization cost scales with output size. Rules producing O(N²)
  tuples can take seconds at N=100.
- `modify-function!` at 584ms worst case (retract + reparse +
  rematerialize).
- Python bridge adds ~50ms per operation from subprocess overhead.
  Complex syntax (dicts, generators, f-strings) doesn't round-trip
  through render.
- Experiments use scripted agents, not LLM agents. The structural
  advantages (entity precision, shared state, composable rules) are
  architectural properties that don't depend on the agent
  implementation, but real-agent validation is future work.

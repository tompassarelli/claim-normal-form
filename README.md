# Claim Normal Form

**The graph is the program. Text is a materialized view.**

CNF stores programs as claims in a graph — statuses, transitions, permissions, effects, obligations. Agents edit the graph directly. The system derives structural consequences, checks obligations, and projects executable artifacts. Files are output, not input.

## Why this matters

When agents edit text files, they replicate visible patterns. When the task requires a structural abstraction absent from the code surface, they miss it — consistently, across runs, across experiments.

E30 tested this on a helpdesk domain. Task: add "suspended" as a blocked status. The existing code had two groups (active, terminal). The business rule implied a third group ("not active, not terminal, can come back") but nothing in the code suggested it.

| Condition | Obligation bugs | Cost/run |
|-----------|----------------|----------|
| Graph (property-derived) | 0/24 | $0.109 |
| Graph (all conditions) | 0/72 | — |
| File (direct edit) | 14/24 | $0.149 |

The file agent added the status, defined transitions, excluded it from active counts — structurally correct on visible edits. But it never created `BLOCKED_STATUSES` or `is_blocked()`. Not in any of 9 file runs across two experiments. It handled "suspended" as a one-off case rather than a structural category.

The graph agent declared two business properties: `counts_as_work=false, terminal=false`. The graph derived `group=blocked`, projected `BLOCKED_STATUSES` and `is_blocked()` into the Python module, and fired obligation constraints for missing permissions — all automatically.

The design principle: **agents declare semantic properties; the graph derives internal classification.** Don't make agents pick ontology labels when the graph can infer them.

## The ontology

```text
Object = addressable identity
Entity = object only           (entity!)
Value  = object + literal      (value!)  — interned, canonical
Claim  = object + (l p r)      (claim!)  — itself an object
```

Every fact has the shape `(l p r)`, and every slot is an object. The claim is itself an object — it can be named, superseded, explained, attributed to an agent, assigned to a transaction, or made the subject of further claims. Reification is the default, not a bolt-on.

## What makes it graph-native

Four independent axes:

1. **Source of truth**: the program is stored as a claim graph, not text files
2. **Editing interface**: agents edit structured graph facts, not files
3. **Semantic analysis**: dependencies, obligations, types, permissions are derived from graph structure
4. **Execution strategy**: interpreter, compiled projection, or JIT — secondary to 1-3

The thesis lives in axes 1 + 2 + 3. Compilation to Python does not betray the thesis. It only betrays the thesis if the projected files become the thing agents edit and reason from.

A graph-native program:

```
agent edits claims
→ graph validates claims
→ graph derives consequences (obligations, types, deps)
→ graph projects executable artifact
→ artifact runs
→ failures map back to claims
```

## Evidence

### Graph-canonical programs (E27–E30)

The claim graph IS the program. ClaimDesk helpdesk domain — statuses, transitions, roles, permissions, effects, obligations — all expressed as claims. No parsed Python. No file source of truth.

**E28** — Simple task (add "duplicate" as terminal status). Both graph and file agents get 0/36 bugs. Graph is 2.4x faster, 3x cheaper. At small scale, the structural guarantee doesn't differentiate.

**E29** — Obligation pressure (add "suspended" as blocked status). The existing code has no third group. This breaks the binary partition and exposes whether agents can invent the missing abstraction.

Core finding: the graph acts as a **semantic commitment amplifier**. Correct classification → downstream correctness (0-1 bugs). Wrong classification → downstream catastrophe (6-7 bugs). File agents degrade locally (ad-hoc patches). Graph agents commit globally — for better or worse.

In 6/6 file runs, zero agents introduced `BLOCKED_STATUSES` or `is_blocked()`. In 2/6 graph runs, the agent classified "suspended" as "active" and the wrong structure propagated everywhere.

**E30** — Semantic authority transfer. Fixes E29's failure mode by moving classification from agent into graph. Three interfaces: agent picks group (E29 control), agent picks group + properties with validation, agent declares properties only and graph derives group.

The property-derived interface achieved 0/24 obligation bugs at $0.109/run — 27% cheaper than file editing. Across all graph conditions: 0/72 obligation bugs. File baseline unchanged: 14/24. The agent cannot pick the wrong group because it doesn't pick a group at all.

### Multi-agent coordination (F2–F11)

Earlier evidence showing that when programs are shared graphs, coordination bugs disappear.

**F2/F3** — Five agents build a CRM (workflow, permissions, audit, notifications, analytics). Git agents: 5 cross-cutting bugs every run — notifications fire for archived tickets, analytics counts them as active, permissions misses the archive action. CNF agents: 0 cross-cutting bugs. The git agents aren't dumb — they're locally rational, each building from what they can see. The CNF agents import `TERMINAL_STATUSES` from the graph because the claim graph says those entities exist.

**F4/F5** — Overlapping edits and scaling to 8 agents. A mid-run requirement (`on_hold`) lands after agents fork. Git agents miss it — they forked before it existed. CNF agents read the updated graph. Across F2–F5: CNF holds at 100% while git ranges 50–89%. All failures are structural.

**F8/F9** — Parallel race. Same agents build in parallel. Git agents produce 4 cross-cutting bugs requiring a repair round. CNF agents query the shared graph and build correctly. Real Claude Sonnet agents: CNF 34s vs git 68s (2x). The entire delta is repair cost.

**F11** — Graph-only tools, no file access. Discover-style tools (`discover`, `discover_all`, `dependencies`) each return a complete answer in one call. First 0/4 info-gap-bug result. Tool abstraction + prompt design + reliable infrastructure — all three necessary.

### Structural correctness (E15–E19)

Entity resolution, transitive closure, and shadowed-name disambiguation are qualitatively different from string matching.

- **E15**: CNF correct on 5/5 structural tasks. Text search wrong on 5/5.
- **E17**: Both agents pass all 26 tests. Hidden contract tests: CNF 30/30, text 26/30. The text agent renames dict keys alongside function calls.
- **E19**: Five agents, 45-function codebase. Git agents waste 56% of operations on rediscovery. CNF: 0%.

→ [Full experiment results — 35 experiments with raw data.](docs/experiments/README.md)

## Architecture

```text
cnf-lib/
  main.rkt             Public API — (require cnf) re-exports core modules
  server.rkt           MCP tools over JSON-RPC 2.0 — the agent control surface
  lang.rkt             Toy language bridge
  racket.rkt           Racket bridge
  python.rkt           Python bridge
  beagle.rkt           Beagle bridge
  private/
    kernel.rkt         Entity/Value/Claim kernel — objects, claims, indexed lookups
    datalog.rkt        Semi-naive Datalog — derived facts, materialized views
    eval.rkt           Graph evaluator — Datalog finds redexes, claims record results
    graph.rkt          Names, supersession, rename, dependency tracking
    schema.rkt         Ergonomic CRUD — entity/claims, lookup, find-by, update
    lang.rkt           Toy language — parse/render/rename round-trip
    racket.rkt         Racket bridge — define, struct, let, lambda, cond
    python.rkt         Python bridge — AST via subprocess, 30+ node types
    beagle.rkt         Beagle bridge — real typed Lisp, 30+ form types
cnf-test/
  tests/               11 test files, 379 tests
experiments/
  e27-runtime-claimdesk/  Graph-canonical ClaimDesk — domain model, MCP server,
                          runners, agent outputs for E28–E30
```

Three language bridges prove the pattern is language-agnostic. A new language is just a frontend that maps an AST into entities and claims — everything else is shared infrastructure.

## Quick start

```bash
# Prerequisites: Racket 8.x, Python 3.x (for the Python bridge)

git clone https://github.com/tom/cnf-racket && cd cnf-racket
raco pkg install cnf/

# Verify
raco test cnf-test/tests/

# MCP server (semantic index mode)
racket cnf-lib/server.rkt               # stdio
racket cnf-lib/server.rkt --daemon 7888 # daemon (multi-client, MVCC)

# ClaimDesk domain server (graph-canonical mode)
racket experiments/e27-runtime-claimdesk/claimdesk-mcp.rkt
racket experiments/e27-runtime-claimdesk/claimdesk-mcp.rkt --mode properties
```

Claude Code MCP config (`.claude/settings.json`):

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
| --- | -------- |
| [How CNF works](docs/overview.md) | Concrete walkthrough — claims, rename, deps, agents |
| [API reference](docs/api.md) | Kernel, Datalog, eval, schema, graph, lang layer APIs |
| [MCP server](docs/mcp.md) | Tools, MCP Resources, workflows, daemon mode |
| [Language bridges](docs/bridges.md) | Racket, Python, and Beagle bridges |
| [Specification](specification.md) | Full formal spec |
| [Experiments](docs/experiments/README.md) | 35 experiments with raw results |
| [Devlog](docs/devlog/README.md) | 46 entries — discoveries, direction changes, honest numbers |
| [Roadmap](docs/todo.md) | What's done, what's next |

## Limitations

The correctness story is solid; scale is unmeasured.

The graph-canonical results (E27–E30) are on a small domain — 6 statuses, 4 projected modules. The property-derived classification works for a three-group model. Whether it generalizes to richer ontologies, novel groups the graph hasn't seen, and multi-entity features is the open question (E31–E33).

The multi-agent results (F2–F11) top out at 8 agents on a ~200-LOC app. The structural advantage should compound with scale (more agents → more info-gap bugs → more repair rounds), but that's projected, not measured.

The projected Python passes integration tests but has never served a live request. The graph-canonical claim is stronger if the projected artifact actually runs as an application.

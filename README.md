# Claim Normal Form

**Programs as executable facts.**

*spooky action in the substrate*

CNF stores program structure as claims, derives semantic relations with Datalog, and evaluates graph-native programs directly. Source files are projections; the claim graph is the substrate.

That one design choice has a consequence the rest of this README is about: when the program *is* a shared graph instead of a pile of text, many agents can build on it at once without colliding.

## Why this matters

Software construction doesn't scale with agent count. Coordination cost does.

- **1 agent** — productive
- **2 agents** — coordination overhead
- **5 agents** — merge hell

The cost is rediscovery, inconsistent assumptions, hidden dependencies, and cognition that lives and dies inside a single session. Every agent rebuilds a private model of the program; that model evaporates when the session ends; the next agent starts over.

The bugs that follow live in no single module. They live in the **gaps between features** — each module correct on its own, inconsistent with the others.

You can't test your way out of this. You can't write a test for a state you don't know exists. An analytics agent won't exclude archived tickets from active counts if it never learned `archived` is a state. A permissions agent won't gate the archive action if it never saw the workflow. Every feature passes its own suite. The system still breaks.

The enemy isn't text, or grep, or git. It's reasoning trapped inside isolated sessions.

> **Git agents fork reality. CNF agents accumulate it.**

## What CNF does

It externalizes reasoning into durable shared structure.

Source code stops being text and becomes claims about stable identities. A function is an entity carrying a current name claim — not a string. A call site points at the entity, not at matching characters. The model persists across sessions, spans agents, and updates incrementally as the program changes.

The payoff is the same as a type system's, one level up. Types give you a stable model to reason against while you're *writing* code. CNF gives every agent a stable model to reason against while everyone is *changing* the code at once. Types stabilize construction; CNF stabilizes coordination.

→ [How CNF works — a concrete walkthrough.](docs/overview.md)

## The ontology

```text
Object = addressable identity
Entity = object only           (entity!)
Value  = object + literal      (value!)  — interned, canonical
Claim  = object + (l p r)      (claim!)  — itself an object
```

Every fact has the shape `(l p r)`, and every slot is an object. This is not EAV with the columns renamed. In EAV the row is plumbing. In CNF the claim is itself an object — it can be named, superseded, explained, attributed to an agent, assigned to a transaction, or made the subject of further claims. Reification is the default, not a bolt-on.

## Evidence

Each experiment puts git agents and CNF agents on the same task and counts what breaks.

### Information gaps (F2, F3)

Five agents build a CRM — workflow, permissions, audit, notifications, analytics — with cross-cutting requirements: notifications suppress for archived tickets, analytics excludes them from active counts, permissions covers the archive action.

|                    | Git   | CNF   |
| ------------------ | ----- | ----- |
| Integration tests  | 9/14  | 14/14 |
| Cross-cutting bugs | 5     | 0     |

The git agents aren't dumb — they're *locally rational*, each building a correct module from what it can see. The CNF notification agent imported `TERMINAL_STATUSES` from the workflow module because the claim graph said those entities existed. The git agent guessed terminal states from intuition (`{"closed", "resolved"}`) and never knew `"archived"` was one. Not an intelligence gap, not a prompt gap — one agent had shared structure, the other had local reconstruction. Replicated across two runs (16 agents total); the four structural bugs appear in every git run and no CNF run.

**F3** repeats this with a *live* graph — each agent's code is parsed into the graph when it finishes, so the next agent inherits everything (17 → 34 entities across the pipeline). Same result (CNF 13/14, git 7/14). CNF's lone miss is instructive: the permissions agent *found* `archive_ticket` and granted it too broadly — a policy judgment made with full information, not the git failure of not knowing archive exists at all.

### Overlapping edits (F4)

Three agents edit `config.py` independently, and a new status (`on_hold`) lands *after* the first agent forks.

|                             | Git        | CNF   |
| --------------------------- | ---------- | ----- |
| Integration tests           | 18/21      | 21/21 |
| Config merge conflicts      | 3 versions | 0     |
| Mid-run requirement handled | no         | yes   |

Even with a flawless manual merge, the git agents miss `on_hold` entirely — they forked before it existed. CNF agents read the updated graph and absorb it. Merge cost scales quadratically with agent count; sequential accumulation is O(N).

### Scaling agent count (F5)

Eight agents, three tiers, deepening cross-cut.

| Tier  | Agents | Git   | CNF   |
| ----- | ------ | ----- | ----- |
| A     | 3      | 8/10  | 10/10 |
| B     | 5      | 7/8   | 8/8   |
| C     | 8      | 10/10 | 10/10 |
| Total | 8      | 25/28 | 28/28 |

Every git failure is the same shape — *temporal divergence*. The escalation agent adds `on_hold` to config but can't add it to a workflow it forked away from, so the merged system is internally inconsistent. CNF builds against the current graph and stays coherent.

### Coordination cost (E19)

Five agents on a 45-function codebase, each with a real job: map, rename, cut dead code, add a feature, audit.

|                                 | Git          | CNF    |
| ------------------------------- | ------------ | ------ |
| Wasted on rediscovery           | 50 ops (56%) | 0 (0%) |
| Dead code correctly identified  | 5/7          | 7/7    |
| Downstream edit silently broken | yes          | no     |

A regex rename hits the function *and* an unrelated parameter that happens to share its name; a later edit then fails silently while the tests stay green. CNF renames the entity — one claim — and the parameter is never touched.

### Speed (F6 → F9)

The honest part. CNF wins on correctness everywhere; speed depended on whether it could run in parallel.

- **F6** — Git won 1.8× (276s vs 500s) — but only because CNF ran sequentially against git's parallel build-plus-repair.
- **F8** — With all agents parallel, CNF flips it: 28s vs 82s (3×). The entire delta is git's 56s repair pass.
- **F9** — Real Claude Sonnet agents, wall-clock: CNF 34s vs git 68s (2×), same four structural bugs every run. The F2/F8 prediction holds under real inference.

### Is the graph even necessary? (F7, F10)

**F7** pits graph-first against grep and plain file-reading on 7 edit sites across 18 modules. Recall ties at 86% — but graph precision is 60% vs grep's 35%, at 3.2× fewer tool calls. The graph doesn't find *more* sites; it lets agents skip the non-sites.

**F10** runs a live CNF daemon serving six agents via MCP bridges (1685 objects, 1130 claims, 6 simultaneous bridges). Same info-gap bugs eliminated, now from live queries: CNF 20/22 vs git 16.5/22 first-pass. Caveat — agents can't navigate raw Datalog, so coordinator-mediated context is the practical path, and higher-level query tools are the next interface step.

→ [See the full experiment arc — E1–E19, F2–F10 — with raw results.](docs/experiments/README.md)

## Architecture

```text
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

Three bridges prove the pattern is language-agnostic. A new language is just a frontend that maps an AST into entities and claims — dependency queries, rename propagation, history, MCP tools, and materialized views are all shared infrastructure underneath.

## Quick start

```bash
# Prerequisites: Racket 8.x, Python 3.x (for the Python bridge)

# Install
git clone https://github.com/tom/cnf-racket && cd cnf-racket
raco pkg install cnf/            # meta package — installs cnf-lib + deps

# Beagle bridge (optional):
#   git clone https://github.com/tom/beagle && raco pkg install beagle/beagle-lib/

# Verify
raco test cnf-test/tests/

# Use as a library
racket -e '(require cnf) (displayln (make-cnf-ctx))'

# MCP server
racket cnf-lib/server.rkt               # stdio mode
racket cnf-lib/server.rkt --daemon 7888 # daemon mode (multi-client, MVCC)
racket cnf-lib/server.rkt --connect 7888 # bridge to a running daemon
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
| [How CNF works](docs/overview.md) | Concrete walkthrough — function as claims, rename, deps, agents |
| [API reference](docs/api.md) | Kernel, Datalog, eval, schema, graph, lang layer APIs |
| [MCP server](docs/mcp.md) | 29 tools, MCP Resources, workflows, daemon mode |
| [Language bridges](docs/bridges.md) | Racket, Python, and Beagle bridges; adding new languages |
| [Performance](docs/performance.md) | Benchmarks, honest limitations |
| [Specification](specification.md) | Full formal spec |
| [Experiments](docs/experiments/README.md) | 29 experiments (E1–E19, F2–F10) with raw results |
| [Devlog](docs/devlog/README.md) | 28 entries — discoveries, direction changes, honest numbers |
| [Roadmap](docs/todo.md) | What's done, what's next |

## Tests

```bash
raco test cnf-test/tests/     # 379 tests across 11 files
```

## Limitations

The correctness story is solid; the scale story isn't proven yet.

CNF holds at 100% across F2–F5 while git ranges 50–89% — and that advantage is *structural* (entity references vs string matching), so it shouldn't erode with size. The advantage also compounds: more agents mean more bugs and more repair rounds for git, while CNF's graph stays roughly constant (~2s). Projected ~5× at 10 agents, ~7× at 20.

But benchmarks top out at 50–200 functions. Performance at real scale is unmeasured, and the repair loop CNF beats may itself behave differently when there are more agents, more files, harder cross-cutting failures, and repair rounds that compound. Earlier experiments (E15–E18) showed the structural-query and hidden-contract-test wins that motivate all of this — CNF 30/30 vs text 26/30 on hidden contracts — but the headline numbers above are the load-bearing ones.

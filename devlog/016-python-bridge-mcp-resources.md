# 016 — Python bridge + MCP Resources + language-agnostic server

## What happened

Built a complete Python bridge — the second language target after beagle.
Python source → `python3` AST helper (subprocess, JSON) → Racket bridge
→ claim graph. Same pattern as beagle but with a fundamentally different
parser architecture: external process vs. in-process Racket structs.

Added MCP Resources to the server — the first non-tool capability.
Resources push structured data into agent context rather than requiring
tool calls to pull it.

Made the MCP server language-agnostic. All 30 tools auto-detect Python
vs beagle from source syntax.

## The Python bridge pattern

`python-ast-helper.py` (~390 lines) uses Python's `ast` module to parse
source into JSON. Handles 30+ node types: functions, classes, imports,
assignments, calls, operators, comprehensions, control flow, match
statements, decorators, async, type annotations.

`python-lang.rkt` (~550 lines) reads the JSON and creates entities
and claims. 14 predicates, 2 Datalog rules (`py-contains-call`,
`py-fn-depends-on`). Same incremental operations as lang.rkt:
`add-python-function!`, `remove-python-function!`,
`modify-python-function!`.

The subprocess adds ~50ms per parse operation. For incremental edits
this dominates — beagle's in-process parse is 0.9ms for the same
operation. But once claims are in the graph, everything is identical:
queries, renames, matviews, rules.

## MCP Resources

Four resources exposed via `resources/list` and `resources/read`:

- `cnf://summary` — object/claim counts, form overview
- `cnf://dependencies` — fn-depends-on edges
- `cnf://functions` — function names and signatures
- `cnf://rules` — user-defined Datalog rules

These are the structured summaries that an agent's context window
should contain *before* the first tool call. Instead of the agent
calling `status` + `query` + `list_rules` (3 round-trips), the
MCP client can inject all four resources as context (0 round-trips).

This is the architectural fix identified in the deep audit: the
bottleneck was never the engine (100-1000x per-op advantage), it was
the MCP request/response protocol forcing unnecessary round-trips for
information that should be ambient context.

## Language auto-detection

The MCP server checks for `def `, `class `, or `import ` in source to
decide Python vs beagle. `parse_program`, `render`, `add_function`,
`remove_function`, `modify_function` all dispatch automatically. An
optional `language` parameter overrides detection.

## Numbers

E14 Python demo (9 forms, same domain as E13):
- Parse: 55ms (50ms subprocess + 5ms claim creation)
- Objects: 542, Claims: 338
- 7 direct deps, 15 transitive pairs
- Rename: 0.03ms
- Render: 0.6ms

Direct comparison: Python parse is 24x slower than beagle (subprocess
vs in-process), but post-parse operations are within measurement noise.

## What this means

The claim graph is language-agnostic. Two bridges now prove the pattern:
parse source (however your language works) → create entities and claims
→ get structural analysis, rename propagation, incremental mutations,
Datalog queries, and materialized views for free.

Adding a third language means writing one file: a parser that produces
entities and claims. Everything else — the Datalog engine, matviews,
MCP server, persistence, multi-agent collaboration — works unchanged.

118 tests across 10 files. All passing.

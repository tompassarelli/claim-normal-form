# F10: Live Graph Race

Real Claude Sonnet agents, live CNF daemon, graph-derived context.
Six agents, 22 integration tests. The graph is the source of truth.

## Setup

Same ClaimDesk app as F9. Six features: audit, escalation, analytics,
notifications, comments, permissions.

**Infrastructure**: CNF daemon running on localhost. Base codebase
(models.py, core.py, workflow.py) parsed into the claim graph.
1685 objects, 1130 claims, 11 Datalog rules.

**Git condition**: agents see `models.py` + simplified `core.py`.
No workflow module, no config, no graph. Same as F9.

**CNF condition**: agents see the same base code plus structural
context derived from live graph queries. The coordinator:
1. Parses source files into the daemon's graph
2. Queries all named entities via `(current-triple (? e) symbol (? name))`
3. Resolves key entities (TERMINAL_STATUSES, ACTIVE_STATUSES, etc.)
4. Queries function dependencies via `(py-fn-depends-on ...)`
5. Formats results as 3357 chars of graph-derived context

Each agent also has a live MCP bridge to the daemon (Python bridge,
6 simultaneous connections confirmed by daemon logs). Agents can
query the graph directly if needed.

## Results

### Run 1

| | Git | CNF |
|--|--:|--:|
| Tests (first pass) | **16/22** | **20/22** |
| Tests (after repair) | **22/22** | **22/22** |
| Build time | 17.7s | 24.4s |
| Repair time | 166.3s | 107.2s |
| Total wall clock | **184.0s** | **131.7s** |
| **Speedup** | | **1.4x** |

### Run 2

| | Git | CNF |
|--|--:|--:|
| Tests (first pass) | **17/22** | **20/22** |
| Tests (after repair) | **22/22** | **22/22** |
| Build time | 22.2s | 29.5s |
| Repair time | 149.2s | 174.7s |
| Total wall clock | **171.4s** | **204.2s** |
| **Speedup** | Git **1.2x** | |

### Combined

| | Git | CNF |
|--|--:|--:|
| Mean first-pass | **16.5/22** | **20/22** |
| Information-gap bugs | **3.5** | **0** |
| Both-condition bugs | **2** | **2** |
| Mean wall clock | **177.7s** | **168.0s** |

## The bugs

**Information-gap bugs (git only, eliminated by graph):**
- test_12: analytics counts archived as active (git hardcodes `TERMINAL_STATUSES = {"closed", "resolved"}`)
- test_13: summary missing statuses (git doesn't know all status values)
- test_14: unassigned includes archived (git doesn't know archived is terminal)
- test_20: escalation doesn't skip archived (git hardcodes active statuses)

**Both-condition bugs (not information gaps):**
- test_09: audit module doesn't register hooks for post_create (integration issue)
- test_11: permissions uses function names ("archive_ticket") instead of action names ("archive")

**What CNF agents do differently:**
```python
# Git agent (guesses):
TERMINAL_STATUSES = {"closed", "resolved"}

# CNF agent (imports from workflow, informed by graph):
from workflow import TERMINAL_STATUSES
```

Every CNF agent that needed terminal/active status information imported
from the workflow module. No CNF agent hardcoded status values.

## What this proves

**The live graph infrastructure works end-to-end.** Daemon starts,
Python bridges connect (6 simultaneous), source code is parsed into
the claim graph, structural queries return entity names and
dependencies, context is generated from live graph state.

**Graph-derived context eliminates information-gap bugs.** The same
4 bugs that appeared in F2, F8, and F9 are eliminated when agents
receive structural context from the graph. The context is generated
from live queries against the daemon, not hardcoded strings.

**The architecture is viable for production.** Python bridge starts
instantly (no racket compilation). 6 concurrent connections handled
by MVCC. Graph queries take milliseconds. The coordinator-mediated
pattern (query graph → format context → inject into agent prompts)
is practical and honest.

## Honest limitations

**Context is coordinator-mediated.** The coordinator queries the graph
and injects results into prompts. Agents don't discover structural
facts themselves via direct MCP queries.

Direct agent queries were tested and work technically — all 6 MCP
bridges connected to the daemon. But agents couldn't use the graph
query interface effectively: they used wrong predicate names, got
empty results, and fell back to guessing. The graph schema (Datalog
predicates like `symbol`, `py-form-kind`, `py-fn-depends-on`) is too
complex for agents to discover on the fly without better tooling.

**Variable values come from knowledge of the source.** The graph
stores TERMINAL_STATUSES as a variable entity with an expression
body, but extracting the literal values ("closed", "archived")
requires walking the expression tree. The coordinator knows the
values because it parsed the source code. A higher-level query tool
(e.g., "list all variables and their values") would make this
graph-native.

**Speed is noisy.** CNF was 1.4x faster in run 1, git 1.2x faster
in run 2. Repair time variance dominates. The correctness result is
stable (20/22 CNF, 16-17/22 git), the speed result is not.

## Raw data

Saved in `experiments/f10-live-race/`:
- `results.json` — timing data from run 2
- `git/` — agent-generated code (git condition)
- `cnf/` — agent-generated code (CNF condition)
- `runner.py` — full experiment infrastructure
- `cnf-bridge.py` — lightweight Python MCP bridge
- `mcp-config.json` — MCP server configuration

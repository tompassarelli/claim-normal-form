# E24a: Facade Design Spike — Scope

**Date:** 2026-05-22

## Thesis

The graph substrate creates the possibility space. The facade makes it
usable by agents. Raw Datalog access is as bad as no graph (F11: 4/4
info-gap bugs both ways). The facade/discover layer is where failures
collapsed from 4/4 to 0/4.

ClaimDesk should not start as "Here are 30 tools. Good luck, agents."
It should start as "Here is a semantic workbench."

## Goal

E24a tests whether an agent-facing semantic facade can induce
self-directed discovery. The graph contains the facts; the facade
determines whether agents can find and use them without handcrafted
prompts.

Core question: **Does a domain-shaped facade cause agents to discover
the lifecycle without being told which constants exist?**

## What exists (F11 baseline)

F11's `graph-tools.py` (460 lines) exposes 4 facade tools over a
Python MCP server that connects to the daemon via TCP:

| Tool | Signature | What it does |
|------|-----------|--------------|
| `discover` | `(name: str)` | Symbol → kind, module, import statement, values |
| `discover_all` | `(kind?: str)` | Inventory of all symbols, optional kind filter |
| `dependencies` | `(symbol?: str)` | Call graph — who calls what |
| `declare_intent` | `(module, depends_on?, provides?)` | Register planned work in the graph |

These wrap 30 raw daemon tools down to 4. The critical one is
`discover`: a single call to `discover("TERMINAL_STATUSES")` returns
the exact import statement and literal values, replacing 4–5 chained
raw Datalog queries that agents consistently fail to compose.

**F11 results with these tools:** 20/22 tests pass, 0/4 info-gap bugs.
Without them (raw Datalog or no graph): 4/4 info-gap bugs.

### What F11's prompt did

The prompt was load-bearing. Key text:

```
CRITICAL: There is a workflow.py module that you CANNOT see. It defines
constants like TERMINAL_STATUSES and ACTIVE_STATUSES with values that
differ from what you would guess. You MUST call discover() to get the
actual values — guessing will produce wrong code.
```

This is effective but too specific — it names the exact variables and
modules. A real-world agent shouldn't need to be told *what* to
discover, only *that* discovery is available.

## What's missing for ClaimDesk

1. **No temporal awareness.** Agents can't ask "what changed since I
   started?" Multi-agent ClaimDesk needs this — when Agent A finishes,
   Agent B should know what was added without re-scanning everything.

2. **No lifecycle discovery.** F11's `discover("TERMINAL_STATUSES")`
   returns the values, but the agent needs to know to ask for that
   specific name. A lifecycle tool would let agents ask "what are the
   states in this system?" and get back the full state machine.

3. **No verification.** Agents have no way to check if their code
   references real things before declaring "done." They write
   `from workflow import TERMINAL_STATUSES` — but does `workflow`
   exist in the graph? Does it export that name?

4. **Module filter missing.** `discover_all()` returns everything
   flat. At ClaimDesk scale (6+ modules), agents need
   `discover_all(module="workflow")` to scope their queries.

5. **Prompt dependence.** F11's prompt names the exact gap. A good
   facade should make agents self-directed — they call
   `discover_lifecycle()` and get the full state machine in one shot,
   without needing to know which constants to ask for by name.

## E24a tools (5 — information discovery + verification)

### The star: `discover_lifecycle`

**`discover_lifecycle(domain?: str) → LifecycleResult`** [NEW]

The primary success path. Answers: "What's the state machine in this
system?" An agent should call this ONCE and get the full picture —
no need to know `TERMINAL_STATUSES` by name.

Without arguments, scans for lifecycle-shaped patterns:
- Variables whose values are lists of strings (enum-like)
- Variables whose values are dicts mapping strings to lists (transition maps)
- Functions that reference these variables

```json
{
  "states": {
    "active": ["open", "in_progress", "resolved", "on_hold"],
    "terminal": ["closed", "archived"]
  },
  "transitions": {
    "open": ["in_progress", "closed"],
    "in_progress": ["resolved", "open", "on_hold"],
    "on_hold": ["in_progress", "open"],
    "resolved": ["closed", "open"],
    "closed": ["archived"],
    "archived": []
  },
  "variables": {
    "VALID_TRANSITIONS": {"module": "workflow", "import": "from workflow import VALID_TRANSITIONS"},
    "ACTIVE_STATUSES": {"module": "workflow", "import": "from workflow import ACTIVE_STATUSES"},
    "TERMINAL_STATUSES": {"module": "workflow", "import": "from workflow import TERMINAL_STATUSES"},
    "ALL_STATUSES": {"module": "workflow", "import": "from workflow import ALL_STATUSES"}
  },
  "functions": {
    "is_valid_transition": {"module": "workflow", "import": "from workflow import is_valid_transition"},
    "transition_ticket": {"module": "workflow", "import": "from workflow import transition_ticket"},
    "archive_ticket": {"module": "workflow", "import": "from workflow import archive_ticket"},
    "is_active": {"module": "workflow", "import": "from workflow import is_active"},
    "is_archived": {"module": "workflow", "import": "from workflow import is_archived"},
    "get_available_transitions": {"module": "workflow", "import": "from workflow import get_available_transitions"}
  }
}
```

With `domain="ticket"`, filters to variables/functions with "ticket"
in the name or module.

Implementation:
1. `_all_symbols()` → get all variables with values
2. For each variable, check if values are list-of-strings or
   dict-of-string-to-list — these are lifecycle-shaped
3. Group related variables by module (e.g., all from `workflow`)
4. Find functions in the same module
5. Classify states as active/terminal from variable names
6. Return structured lifecycle

This is the generalized form of "discover_ticket_lifecycle" — it
works for any state machine encoded in variables, not just tickets.

### Supporting discovery tools

**`discover(name: str) → DiscoverResult`** [EXISTS — reuse from F11]

Fallback path. Returns everything about one symbol in a single call.
Useful when `discover_lifecycle` leads the agent to a specific name.

```json
{
  "name": "TERMINAL_STATUSES",
  "kind": "variable",
  "module": "workflow",
  "import": "from workflow import TERMINAL_STATUSES",
  "values": ["closed", "archived"]
}
```

**`discover_all(kind?: str, module?: str) → [DiscoverResult]`** [EXTEND]

Inventory of all symbols. Add `module` filter (missing in F11).
Useful for orientation, but `discover_lifecycle` is the agent-native
move — agents should not need to rummage through a symbol table.

**`dependencies(symbol?: str) → DependencyResult`** [EXISTS — reuse]

Call graph. No changes needed.

### Verification

**`verify_references(code: str) → VerifyResult`** [NEW]

Check whether a code snippet's imports and references resolve against
the graph. Uses Python `ast` module (not regex) for reliable parsing.

```json
{
  "resolved": [
    {"name": "TERMINAL_STATUSES", "module": "workflow", "status": "ok"},
    {"name": "get_ticket", "module": "core", "status": "ok"}
  ],
  "missing": [
    {"name": "ARCHIVE_STATUSES", "attempted_import": "from workflow import ARCHIVE_STATUSES", "suggestion": "did you mean TERMINAL_STATUSES?"}
  ],
  "unused_imports": [
    {"name": "create_ticket", "module": "core"}
  ]
}
```

Implementation:
1. `ast.parse(code)` → walk `ast.Import`, `ast.ImportFrom` nodes
2. Walk `ast.Name` nodes for reference checking
3. For each imported name, call `resolve_symbol` to check existence
4. For missing names, call `_all_symbols` and fuzzy-match
5. Check which imports are actually referenced in code body
6. Return resolved/missing/unused

### E24b tools (deferred — concurrent coordination)

These are designed but NOT scored in E24a. The 2-agent task doesn't
exercise live multi-agent graph awareness. Implement if cheap, but
E24a is judged on discovery, not coordination.

**`checkpoint() → CheckpointResult`** — mark current tx position.
**`what_changed(since_tx?) → ChangeResult`** — semantic diff since
a checkpoint, grouped by entity, tagged by agent.

## Tool summary (E24a scored)

| # | Tool | Status | Purpose | Scored? |
|---|------|--------|---------|---------|
| 1 | `discover_lifecycle` | **New** | What's the state machine? | **Primary** |
| 2 | `discover` | Reuse | What is this symbol? | Fallback |
| 3 | `discover_all` | Extend | What exists? | Fallback |
| 4 | `dependencies` | Reuse | What connects? | Secondary |
| 5 | `verify_references` | **New** | Does my code work? | Stretch |

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Agent (Claude)                        │
│  "Build notifications.py for ClaimDesk"                 │
└──────────────────┬──────────────────────────────────────┘
                   │ MCP (stdio)
┌──────────────────▼──────────────────────────────────────┐
│              Facade MCP Server                          │
│         (claimdesk-facade.py, ~600 lines)               │
│                                                         │
│  ┌─────────┐ ┌─────────────┐ ┌──────────────┐          │
│  │discover │ │discover_all │ │dependencies  │  Tier 1   │
│  └────┬────┘ └──────┬──────┘ └──────┬───────┘          │
│  ┌────▼────────────────────────────────────┐            │
│  │          discover_lifecycle             │  Tier 1    │
│  │ (orchestrates discover + discover_all)  │            │
│  └─────────────────────────────────────────┘            │
│  ┌────────────┐ ┌────────────┐                          │
│  │what_changed│ │ checkpoint │              Tier 2      │
│  └─────┬──────┘ └─────┬──────┘                          │
│  ┌─────▼──────────────────────┐                         │
│  │    verify_references       │              Tier 3     │
│  └─────┬──────────────────────┘                         │
│        │                                                │
│  ┌─────▼──────────────────────────────────────────┐     │
│  │  Daemon connection layer (TCP, JSON-RPC 2.0)   │     │
│  │  send_rpc(), daemon_query(), daemon_resolve()   │     │
│  └──────────────────┬─────────────────────────────┘     │
└─────────────────────┼───────────────────────────────────┘
                      │ TCP :7891
┌─────────────────────▼───────────────────────────────────┐
│              CNF Daemon (Racket)                         │
│  30 raw tools: query, inspect, resolve_symbol,          │
│  claim, create_entity, parse_program, evaluate,         │
│  tx_log, current_tx_seq, set_agent, batch, ...          │
│                                                         │
│  MVCC: read-only tools see committed snapshot           │
│        write tools take semaphore, copy, publish        │
└─────────────────────────────────────────────────────────┘
```

Multiple agents connect to the same daemon. Each gets its own facade
server process (separate stdio MCP), but all facade servers connect
to the same daemon TCP port. The daemon's MVCC handles concurrency.

## ClaimDesk base codebase

The codebase that gets parsed into the graph before agents start.
Three files:

### `models.py` (exists)
Ticket, User, Contact dataclasses. No changes needed.

### `core.py` (exists)
CRUD operations. No changes needed.

### `workflow.py` (must create)

This is the file agents cannot see but must discover. It contains the
state machine constants that cause info-gap bugs when guessed wrong.

```python
from core import get_ticket, update_ticket

VALID_TRANSITIONS = {
    "open": ["in_progress", "closed"],
    "in_progress": ["resolved", "open", "on_hold"],
    "on_hold": ["in_progress", "open"],
    "resolved": ["closed", "open"],
    "closed": ["archived"],
    "archived": [],
}

ACTIVE_STATUSES = ["open", "in_progress", "resolved", "on_hold"]
TERMINAL_STATUSES = ["closed", "archived"]
ALL_STATUSES = ACTIVE_STATUSES + TERMINAL_STATUSES

def is_valid_transition(from_status, to_status):
    return to_status in VALID_TRANSITIONS.get(from_status, [])

def transition_ticket(ticket_id, new_status):
    ticket = get_ticket(ticket_id)
    if not ticket:
        raise ValueError(f"Ticket {ticket_id} not found")
    if not is_valid_transition(ticket.status, new_status):
        raise ValueError(f"Cannot transition from {ticket.status} to {new_status}")
    return update_ticket(ticket_id, status=new_status)

def archive_ticket(ticket_id):
    return transition_ticket(ticket_id, "archived")

def is_active(ticket):
    return ticket.status in ACTIVE_STATUSES

def is_archived(ticket):
    return ticket.status == "archived"

def get_available_transitions(ticket):
    return VALID_TRANSITIONS.get(ticket.status, [])
```

This is the F11 workflow with `on_hold` included — the version that
maximizes the info-gap surface.

### Graph loading sequence

Before agents start:
1. Start daemon: `racket cnf-lib/server.rkt --daemon 7891`
2. Parse all base files: `parse_program(source=models_py, language="python")`
3. Parse workflow: `parse_program(source=workflow_py, language="python")`
4. Parse core: `parse_program(source=core_py, language="python")`
5. Verify: `status()` → should show all entities loaded

## The 2-agent test

### Task design

Two agents, each building one module. Both need workflow constants
that only the facade can provide.

**Agent 1 — `notifications.py`:**
Build a notification system for ticket transitions. Must suppress
notifications for terminal-status tickets.

**Agent 2 — `analytics.py`:**
Build analytics: ticket summary by status, active count, unassigned
list. Must correctly categorize all statuses including `on_hold`.

### The info-gap surface

Both agents need `TERMINAL_STATUSES` and `ACTIVE_STATUSES`. Without
the facade, agents guess:
- TERMINAL_STATUSES = `["closed"]` (missing `"archived"`)
- ACTIVE_STATUSES = `["open", "in_progress"]` (missing `"resolved"`, `"on_hold"`)

These guesses produce bugs in:
- Notifications sent for archived tickets
- Active count includes archived tickets
- Summary misses `on_hold` and `archived` categories
- Unassigned list includes archived tickets

### Prompts (minimal — no spoon-feeding)

The point of E24a is to test whether the facade is self-explanatory.
The prompt should NOT name specific variables to discover.

```
Agent 1 prompt:
  "Build notifications.py for ClaimDesk. When a ticket transitions
  between statuses, notify interested parties. Some ticket states
  should not trigger notifications. Use the available tools to
  discover the codebase structure before writing code."

Agent 2 prompt:
  "Build analytics.py for ClaimDesk. Provide: ticket_summary() that
  counts tickets by every possible status, active_ticket_count(),
  and unassigned_tickets(). Use the available tools to discover the
  codebase structure before writing code."
```

~40 words each. No mention of `TERMINAL_STATUSES`, `workflow.py`,
`discover()`, or any specific tool. The agent must figure out on its
own that:
1. There are tools available (MCP tool list)
2. `discover_all()` shows symbols it didn't know about
3. `discover_lifecycle()` reveals the state machine
4. The values differ from what it would guess

### Verification tests

Same structure as F11. Subset of the 22 tests, focused on the
info-gap bugs:

```python
# Info-gap tests (the ones that matter)
def test_no_notification_for_archived():
    """Archived tickets must NOT trigger notifications."""
    ...

def test_active_count_excludes_archived():
    """active_ticket_count() must not count archived tickets."""
    ...

def test_summary_includes_all_statuses():
    """ticket_summary() must have entries for on_hold, archived."""
    ...

def test_unassigned_excludes_archived():
    """unassigned_tickets() must not include archived tickets."""
    ...
```

### Conditions to compare

| Condition | Tools | Prompt | Expected |
|-----------|-------|--------|----------|
| **Facade full** | discover_lifecycle + discover + discover_all + dependencies + verify | Minimal | 0/4 info-gap bugs |
| **Facade basic** | discover + discover_all + dependencies + verify (NO lifecycle) | Minimal | ? — the key ablation |
| **No graph** | None (just models.py + core.py visible) | Minimal | 4/4 info-gap bugs |

The critical ablation is **Facade full** vs **Facade basic**. This
tells us whether `discover_lifecycle` is actually doing work, or
whether `discover_all → discover` is enough. If facade basic also
gets 0/4, the lifecycle tool is nice but not load-bearing. If facade
basic gets >0/4 while facade full gets 0/4, the lifecycle tool IS
the product.

Optional additional conditions if budget allows:
- **Raw tools** — 4 raw daemon tools (query, inspect, resolve, claim)
- **Facade full + hint** — adds "workflow constants may surprise you"

## Success criteria

1. **Primary:** Agents call `discover_lifecycle()` and use its output
   to correctly handle all states including `on_hold` and `archived`.
   The agent should not need to know `TERMINAL_STATUSES` by name —
   the lifecycle tool surfaces the full state machine unprompted.

2. **Secondary:** `discover_all → discover` works as a fallback path.
   Agents browse the inventory, notice unfamiliar variables, and look
   them up. This is acceptable but not the ideal facade win.

3. **Stretch:** `verify_references()` catches a mistake before the
   agent declares done, and the agent self-corrects.

4. **Anti-goal:** Do NOT tune the prompt to force tool usage. The
   prompt may say "use tools to discover structure" (that's normal
   tool-use framing). It must NOT say "workflow constants may surprise
   you", "TERMINAL_STATUSES exists", "call discover_lifecycle", or
   "closed and archived are terminal."

## Tool-use scoring rubric

Pass/fail tests are not enough. For each agent, track:

```
called discover_lifecycle?        → primary path
called discover_all?              → inventory path
called discover("TERMINAL_...")?  → specific lookup
called discover("ACTIVE_...")?    → specific lookup
called verify_references?         → self-check
used returned import statements?  → did they trust the tool?
used actual values vs guessed?    → did they use the tool output?
```

This distinguishes:
- Agent passed BECAUSE it used the facade
- Agent passed because it guessed luckily
- Agent failed despite discovering correct info
- Agent never discovered the lifecycle

Record the full tool-call sequence per agent in the results.

## Implementation plan

### Phase 1: Extend graph-tools.py → claimdesk-facade.py

Copy F11's `graph-tools.py` as the base. Add:

1. **Module filter on `discover_all`** — add optional `module` param
   to the existing `_all_symbols` query. ~10 lines.

2. **`discover_lifecycle`** — the star tool, ~60 lines.
   - Call `_all_symbols()` to get all variables with values
   - For each variable, check if values are list-of-strings or
     dict-of-string-to-list — these are lifecycle-shaped
   - Group by module, classify by variable name heuristics
   - Find functions in same module
   - Return structured LifecycleResult

3. **`verify_references`** — uses Python `ast` module, ~50 lines.
   - `ast.parse(code)` → walk Import/ImportFrom/Name nodes
   - For each imported name, call `resolve_symbol`
   - For missing names, call `_all_symbols` and fuzzy-match
   - Check which imports are actually referenced
   - Return resolved/missing/unused

4. **Update tool list** — tool descriptions that make their purpose
   obvious without naming hidden facts. `discover_lifecycle` should
   say something like: "Scan the codebase for state machines,
   workflows, and lifecycle patterns. Returns states, transitions,
   and the functions that enforce them."

### Phase 2: Build ClaimDesk base codebase

1. Create `workflow.py` (shown above)
2. Verify models.py and core.py parse correctly into the graph
3. Write a loader script that starts the daemon and parses all files

### Phase 3: Build runner

1. Minimal runner — 2 agents, facade condition only for the spike
2. Each agent gets: model selection, timeout, MCP config pointing
   to facade server, minimal prompt
3. Extract code from agent output
4. Assemble workspace: models.py + core.py + workflow.py +
   agent outputs (notifications.py, analytics.py)
5. Run verification tests
6. Record: which tools each agent called, in what order, whether
   they got correct values, test pass/fail

### Phase 4: Run and analyze

1. Run facade condition with minimal prompt
2. Check: did agents call discover_all? discover_lifecycle?
3. Check: 0/4 info-gap bugs?
4. If yes → facade design is sufficient
5. If no → analyze transcript, identify what the facade is missing
6. Optionally run with hint ("workflow constants may surprise you")
   to separate tool design from prompt design

## Estimated effort

| Phase | Work | Lines |
|-------|------|-------|
| Extend facade server | discover_lifecycle + verify_references + module filter | ~130 new |
| workflow.py | One file | ~35 |
| Loader script | Start daemon, parse files | ~30 |
| Runner | 2-agent harness + tests + tool-use scoring | ~250 |
| Analysis | Transcript review, tool-use rubric, devlog | — |
| **Total new code** | | **~445 lines** |

Reused from F11's graph-tools.py: ~460 lines (daemon connection,
MCP protocol, discover, discover_all, dependencies, declare_intent).

## Risk: lifecycle heuristics

`discover_lifecycle` uses two detection strategies:

1. **Name heuristics** — variable names containing "status", "state",
   "transition", "active", "terminal" etc.
2. **Value-shape inference** — any variable whose value is a
   list-of-strings or a dict mapping strings to lists of strings
   is lifecycle-shaped, regardless of its name.

Strategy 2 is the robust one. A variable named `FLOW_MAP` with value
`{"open": ["closed"]}` would be detected by shape even though its
name has no lifecycle keywords. Strategy 1 helps classify (active
vs terminal) once the variable is detected.

Known crack: if lifecycle values are not embedded as literals (e.g.,
built dynamically at runtime), the graph won't have them. This
requires parser tagging or runtime instrumentation. Not needed for
E24a — the ClaimDesk workflow uses literal constants.

## Risk: agent behavior without prompting

F11's 0/4 result depended on the prompt saying "values differ from
what you would guess." Without that nudge, agents may:
- See `discover_all()` in the tool list but not call it
- Call `discover_all()` but ignore variables they don't recognize
- Write code using guessed values without checking

This is the central question E24a tests. If agents don't self-direct,
we need either:
- Better tool descriptions (MCP tool schemas have a description field)
- A single "orientation" line in the prompt ("explore before you build")
- A `start_task()` meta-tool that runs discover_all + discover_lifecycle
  automatically and returns the results as the first interaction

The point is to find the minimum viable prompt, not zero prompt.

## Relationship to ClaimDesk (E24b)

E24a is a 2-agent test on a small slice. E24b is the full 3–5 agent
ClaimDesk run with:
- permissions.py, audit.py, notifications.py, analytics.py,
  escalation.py, comments.py (all 6 F11 modules)
- Concurrent agents on shared daemon (E23b architecture)
- Facade tools proven in E24a
- Overlapping concerns forcing coordination

E24a proves the facade works for information discovery. E24b proves
it works for concurrent composition at realistic scale.

# 010: The shared substrate — persistence changes the game

**Date:** 2026-05-20

## The realization

E5–E9 kept asking "which agent makes fewer tool calls?" and the
answer was always text — because a Python script is Turing-complete
in one Bash call. No amount of interface optimization changes that.

The breakthrough: stop comparing within the same frame. The claim
graph's real properties are all **cross-boundary** — they matter
across tasks, across sessions, across agents. Every experiment so far
was single-agent, single-session, all-questions-upfront. The claim
graph's advantages were invisible by design.

## What we built

### Checkpoint/restore

Added `export-store` and `import-store!` to cnf.rkt. The full claim
graph (objects, values, claims, supersession, next-id) serializes to
JSON and round-trips perfectly.

The hard part was restore. You can't re-run the setup functions
(they'd create duplicate predicate entities). Instead:

1. Create a blank context (no bootstrap)
2. Inject raw state directly into the hash tables
3. Find predicate entities by symbol name (`resolve-symbol "op"` etc.)
4. Rebuild the ext table mapping (e.g., `'op-pred → entity-id`)
5. Re-register built-in rules (11 Datalog rules from eval/graph/lang)
6. Restore user-defined rules from their claim-stored source
7. Materialize

Step 6 is where homoiconic rules pay off. Because rules store their
source as claims (`rule-source` predicate), we can parse them back
into `dl-rule` structs without any external state. The rules ARE
claims, so checkpointing claims checkpoints rules.

### Daemon mode

`racket mcp-server.rkt --daemon PORT` — TCP server with a semaphore
serializing access to the claim graph. Multiple clients connect, all
see the same state. Auto-restores from checkpoint on startup.

`racket mcp-server.rkt --connect PORT` — thin stdio↔TCP bridge so
Claude Code (which only speaks stdio MCP) can connect to the daemon.

Refactored `handle-request` into `make-response` (returns JSON) so
the same dispatch logic serves both stdio and TCP transports.

### E10 results

Two sessions, 50 functions. Session 1: parse + define rules +
checkpoint. Session 2: fresh server, 5 composition tasks.

**CNF Session 2 (6 calls):**
- `restore` → 1283 objects, 882 claims, 3 user-defined rules
- `list_rules` → saw rules it never defined
- `query trans-dep` → hit Session 1's matview
- `batch(rename + query)` → matview auto-updated
- `query shared-dep` → auto-updated through rename
- `define_rule` → composed existing derived relations

**Text Session 2 (~5 calls):**
- Read file, wrote Python scripts, reimplemented everything
- Got structural analysis wrong (22 roots instead of 10, wrong hub)

Call ratio: 1.2x. The gap is noise. The difference is qualitative.

## Why this matters

The claim graph is no longer a tool the agent uses. It's an
**environment the agent lives in**.

When Agent 2 arrives and the matview is already there, it doesn't
"use the CNF tool to analyze code." It queries shared understanding
that Agent 1 built. It adds to it. The understanding grows. The next
agent finds an even richer environment.

Text files don't accumulate understanding. They're static. Each agent
starts from scratch. A Python script is a one-shot computation —
powerful but disposable. A Datalog rule is a persistent, composable,
inspectable piece of structural understanding that survives across
sessions, auto-updates through mutations, and composes with other
rules by reference.

E10 is the first experiment that tested what the claim graph CAN DO,
not just how fast it does it. And it's the first one where CNF has an
advantage text fundamentally cannot match.

## What's next

Transactions. Checkpoint is a coarse whole-graph snapshot. With tx
entities, every claim records which transaction created it. Agents
can ask "what changed since I was last here?" instead of loading the
full graph. This enables diff-based reasoning — the foundation for
real multi-agent collaboration.

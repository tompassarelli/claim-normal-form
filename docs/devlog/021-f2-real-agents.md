# F2: Real agents confirm the coordination thesis

## Context for external readers

This is a status report on **Claim Normal Form (CNF)** — a structural
reasoning scaffold for coding agents. Instead of treating source code
as text (strings, files, grep), CNF treats it as claims about stable
identities. A function is an entity with a current name claim, not a
string. A call site points at the entity, not at matching characters.

The project is implemented in Racket. It includes a claim graph kernel,
a Datalog rule engine with materialized views, an MCP server (30 tools),
and language bridges for Python, Racket, and Beagle (a typed Lisp).
19 experiments (E1–E19) tracked the evolution from speed benchmarks
to structural correctness to multi-agent coordination.

The core thesis: **agents that share a structural model of the program
produce fewer cross-cutting bugs than agents that share text files.**

## The reframe: reasoning scaffold, not shared memory

Early experiments (E1–E9) measured speed — how many MCP calls, how
many milliseconds. This was the wrong frame. The real value of CNF
is not "faster" but "correct in ways text can't be."

The analogy that crystallized the direction: **CNF is to agents what
a type system is to programmers.** Not "catch trivial errors" but
"give the agent a stable model to reason against while the program
is changing." A type checker prevents invalid compositions during
construction. CNF prevents invalid coordination during collaboration.

This reframe happened during E15–E18, where the experiments shifted
from speed comparisons to structural correctness:

- **E15**: 5 structural queries (transitive deps, shadowed names,
  dead code). CNF correct on all 5. Grep wrong on all 5.
- **E16**: 10 tasks on a 45-function codebase. CNF correct on 7/7
  structural tasks. Text search wrong on 5, unprovable on 2.
- **E17**: Both agents make real code changes and run tests. Both
  pass all 26 tests. Hidden contract tests: CNF 30/30, text 26/30.
- **E18**: Python's `rope` library (real semantic tool) ties CNF at
  30/30 on rename tasks. But rope provides no persistent state, no
  rule engine, no cross-session memory. CNF's advantage is the
  substrate, not any single operation.

## E19: Coordination cost

Five agents, 45-function codebase, six modules. Each agent has a
real task: map structure, rename a function, remove dead code, add
a feature, audit the result.

Key findings:
- **56% rediscovery in git.** Every agent re-reads every file.
  50 of 89 discovery operations are redundant. CNF: 0% rediscovery
  (each agent restores one checkpoint and inherits prior knowledge).
- **Regex rename breaks downstream work.** Agent B renames function
  `subtotal` → `compute_subtotal` via regex. This also renames the
  `subtotal` *parameter* in an unrelated function. Agent D's later
  edit fails silently. Tests pass. Nobody notices.
- **Dead code false positives.** Grep finds function names in dict
  keys and comments. Agent C keeps 2 dead functions alive. CNF checks
  entity references: 7/7 correct.

## F2: Parallel feature construction (ClaimDesk)

The biggest step: moving from maintenance tasks (rename, refactor,
audit) to **construction** — multiple agents building a coherent
application in parallel.

### Setup

**ClaimDesk** — a small CRM/helpdesk app. Base: 13 functions across
2 modules (core.py, models.py). Five agents each build a cross-cutting
feature:

1. **Workflow** — state machine (open → in_progress → resolved →
   closed → archived), transition rules, archive function
2. **Permissions** — role-based access (admin/agent/viewer)
3. **Audit** — action logging, audit trail
4. **Notifications** — transition alerts, subscriber management
5. **Analytics** — ticket summary, active counts, reports

The implicit requirement: *archived tickets cannot trigger
notifications and are excluded from active reports, but remain
visible in audit history.*

Two conditions:
- **Git**: Each agent sees only the base code. They build their
  feature independently. All features merge into one codebase.
- **CNF**: Agents see the base code + workflow module + structural
  context from the claim graph (entity IDs for `archive_ticket`,
  `is_archived`, `is_active`, dependency edges, status lists).

### Scripted results

Deterministic scripts write predetermined code for each condition.
Git: 9/14 integration tests pass. CNF: 14/14. Five cross-cutting
bugs in git, zero in CNF:

| Bug | Root cause |
|-----|-----------|
| Notifications fire for archived tickets | Agent doesn't know archived state exists |
| Analytics count archived as active | Agent only treats "closed" as terminal |
| Summary missing archived/in_progress/resolved | Agent only knows open/closed |
| No archive permission in matrix | Agent doesn't know archive action exists |
| Archived tickets in unassigned list | Agent doesn't exclude archived |

### Real Claude Code agent results

8 Sonnet agents launched in parallel (4 git, 4 CNF). Each receives
the same task spec with required function signatures. The only
difference: git agents see base code only; CNF agents also see
workflow.py and structural context from the claim graph.

**Result: Git 9/14 (5 bugs), CNF 14/14 (0 bugs). Same five failures
as the scripted version.**

What the git agents actually wrote:
- Permissions: 9 actions from core.py. No "archive" — never saw
  workflow.py. Reasonable matrix, but incomplete.
- Notifications: `_TERMINAL_STATUSES = {"closed", "resolved"}`.
  Good domain guess (inferred "resolved" from CRM conventions) but
  no concept of "archived." Transitions to archived fire notifications.
- Analytics: `TERMINAL_STATUSES = {"closed"}`. Counts archived as
  active. Dynamic status counting (no pre-populated keys). Includes
  archived in unassigned list.

What the CNF agents actually wrote:
- Permissions: 9 actions including "archive" and "transition" from
  workflow.py. Admin-only archive with explicit reasoning about
  terminal/destructive state changes.
- Notifications: Imported `TERMINAL_STATUSES` from workflow. Defined
  `_SILENT_TARGET_STATUSES = {"archived"}`. Returns None for archive
  transitions.
- Analytics: Imported `ACTIVE_STATUSES`, `TERMINAL_STATUSES`, and
  `is_active` from workflow. Pre-populated all 5 status keys.
  Filters unassigned to active tickets only.

The bugs are structural, not stochastic. They follow from the
information gap: if you can't see workflow.py, you can't know
archived exists. No amount of LLM intelligence overcomes missing
information.

## What the experiments prove (and don't)

**What they prove:**
- Agents sharing a structural model produce fewer cross-cutting bugs
  than agents sharing only text files.
- The failures are in the *gaps between features* — each module is
  correct in isolation but inconsistent with others. This is not a
  testing problem (you can't test for states you don't know exist).
- The root cause is *private cognition* — each agent's understanding
  dies with its session. CNF externalizes that understanding into a
  shared graph.

**What they don't prove:**
- This is not yet a "10x faster" demo. F2 proves correctness, not
  speed. The construction was constrained (separate files, no shared
  modifications, graph context provided as text not live queries).
- The codebase is small (13 base functions + 5 feature modules).
  The hypothesis is that the advantage grows with scale, but that's
  unproven.
- Single model, single run. LLM outputs are non-deterministic. The
  structural prediction is robust (git agents miss archived state
  because the information isn't available) but exact failure counts
  could vary across runs.

## Architecture summary

```
                    ┌─────────────────────┐
                    │    MCP Server        │
                    │  30 tools, JSON-RPC  │
                    └──────────┬──────────┘
                               │
              ┌────────────────┼────────────────┐
              │                │                │
        ┌─────┴─────┐   ┌─────┴─────┐   ┌─────┴─────┐
        │  Python    │   │  Beagle   │   │  Racket   │
        │  bridge    │   │  bridge   │   │  bridge   │
        └─────┬─────┘   └─────┬─────┘   └─────┬─────┘
              │                │                │
              └────────────────┼────────────────┘
                               │
                    ┌──────────┴──────────┐
                    │   Claim Graph       │
                    │   (kernel.rkt)      │
                    │                     │
                    │  Entity / Value /   │
                    │  Claim primitives   │
                    └──────────┬──────────┘
                               │
                    ┌──────────┴──────────┐
                    │   Datalog Engine    │
                    │   (datalog.rkt)     │
                    │                     │
                    │  Materialized views │
                    │  Delta propagation  │
                    │  Composable rules   │
                    └─────────────────────┘
```

Three clean layers:
1. **CNF** — the data model. Entities, values, claims.
2. **Datalog** — the reasoning layer. Rules, materialized views,
   incremental delta propagation.
3. **MCP** — the agent interface. 30 tools over JSON-RPC 2.0.

The ontology: `Object = addressable identity`. `Entity = object only`.
`Value = object + literal` (interned). `Claim = object + (l p r)` —
the claim itself is an object, reifiable by default.

## What's next

**F3**: Agents that modify shared files, resolve conflicts, and build
against a live-updating graph. True parallel construction where the
CNF graph is the coordination layer, not just a read-only context
provider.

**BEAM runtime** (later): Entity = process. Claim = message. Each
entity serializes its own claim updates locally while the system
remains massively parallel. Not needed to prove the thesis, needed
when the question shifts from "does the model work?" to "can N agents
use it at production scale?"

The standard for "done": not a benchmark, not a paper — a real app
built 10x faster because of this architecture. F2 is the first step.
The five bugs are the proof that the information gap is real. The
next step is closing it at scale.

# F2: Real agents confirm the coordination thesis

## Context for external readers

**Claim Normal Form (CNF)** is a structural reasoning scaffold for
coding agents. Instead of treating source code as text, CNF treats it
as claims about stable identities. A function is an entity with a
current name claim, not a string. A call site points at the entity,
not at matching characters.

Implemented in Racket: claim graph kernel, Datalog rule engine with
materialized views, MCP server (30 tools), language bridges for
Python, Racket, and Beagle. 20 experiments tracked the evolution from
speed benchmarks to structural correctness to multi-agent coordination.

## The central insight

**The failures are in the gaps between features.** Each module is
correct in isolation but inconsistent with others. The agents are not
wrong — they are locally rational. The bugs emerge from fragmented
world models.

The enemy is not text, not grep, not git. The enemy is **cognition
trapped inside isolated agent sessions**. CNF externalizes cognition
into durable shared structure.

The analogy: **CNF is to agents what a type system is to programmers.**
Types are not valuable mainly because "int vs string." They are
valuable because they stabilize reasoning during change. CNF
stabilizes coordination during collaboration.

## The reframe

Early experiments (E1–E9) measured speed — MCP calls, milliseconds.
Wrong frame. The real value is not "faster" but "correct in ways
text can't be."

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

## What this means

F2 is an existence proof, not a statistical benchmark. The important
result is structural: agents missing shared state produced the exact
classes of integration bugs predicted by the information gap.
Replicated across two runs (16 agents total) — the four structural
bugs appear in every git run and never in any CNF run.

The cleanest evidence: the CNF notification agent imported
`TERMINAL_STATUSES` from the workflow module because the claim graph
told it those entities exist. The git notification agent guessed
terminal states from domain intuition (`{"closed", "resolved"}`) and
missed `"archived"` entirely. Not an intelligence difference. Not a
prompt difference. One system shared semantic structure; the other
relied on local reconstruction.

F2 does not yet prove speed. The construction was constrained
(separate files, no shared modifications, graph context provided as
text not live queries). The hypothesis that shared structure enables
faster construction is the target for F3.

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

F2 proved: fewer integration failures during parallel construction.
The hypothesis for F3: shared structure also enables faster
construction. That is the target, not a proven result.

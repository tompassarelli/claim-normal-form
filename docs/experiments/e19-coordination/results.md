# E19: Coordination Cost — Shared Working Memory

## The thesis

CNF is not "better grep." CNF is shared working memory for code agents.

The killer claim is not "an agent can rename functions more safely." It
is: **multiple agents can build the same program faster because they
are not separately rediscovering the program.**

A normal coding agent loop is mostly private cognition:

1. Inspect files
2. Infer structure
3. Make change
4. Next agent repeats most of that work

CNF changes that into:

1. Inspect code, emit claims about stable entities
2. Other agents inherit that knowledge immediately
3. Future work starts from accumulated semantic state, not fresh text

E19 measures this directly: **coordination cost** — how much does
Agent B waste rediscovering what Agent A already knew?

## Setup

Five agents, same codebase. Each has a distinct task. Agents run
sequentially; each inherits the accumulated state of all prior agents.

**Codebase**: 45 Python functions across 6 modules (models.py,
pricing.py, validation.py, processing.py, reporting.py, test_orders.py).
This is the E16 codebase — production-scale for a small service.

**Agent tasks**:
1. **Architect** — Parse all modules, map dependency structure, define
   transitive dependency rule, identify dead code.
2. **Renamer** — Rename function `subtotal` → `compute_subtotal`.
3. **Janitor** — Remove all dead code (functions with zero callers).
4. **Feature dev** — Add tax exemption parameter to `tax_amount`.
5. **Auditor** — Verify all changes are structurally consistent.

Two conditions:
- **Git**: Agents work on files. Coordination through text changes only.
- **CNF**: Agents work on a shared claim graph. Coordination through
  checkpoint/restore.

## Results

### Git Condition

**Agent A (Architect)**: 30 discoveries, 1 action
- Read all 6 files (function inventory, test count, import tracing)
- Grep each dead-code candidate (7 greps)
- Document findings for subsequent agents
- **Result**: Can't definitively identify 2/7 dead functions (`total`,
  `summary`) because the names appear as dict keys and in other
  contexts. Regex false positives.

**Agent B (Renamer)**: 7 discoveries (all rediscovery), 1 action
- Re-read all 6 files ← REDISCOVERY
- Grep `subtotal` ← REDISCOVERY
- Rename via `\bsubtotal\b` regex across all files
- **Problem**: Naive regex also renames the `subtotal` *parameter* in
  `tax_amount(subtotal: float, region: str)`. This silently changes
  code semantics and breaks Agent D's downstream edit.

**Agent C (Janitor)**: 13 discoveries (all rediscovery), 1 action
- Re-read all 6 files ← REDISCOVERY
- Re-grep each dead-code candidate ← REDISCOVERY
- Remove 5/7 dead functions (kept `total`, `summary` — false refs)
- Same false-positive problem as Agent A.

**Agent D (Feature dev)**: 8 discoveries (all rediscovery), 1 action
- Re-read all 6 files ← REDISCOVERY
- Grep `tax_amount`, `tax_rate` ← REDISCOVERY
- Attempt to add `exempt_below` parameter — **SILENTLY FAILS**.
  Agent B renamed the `subtotal` parameter, so the replacement string
  doesn't match. Agent D's edit is a no-op.

**Agent E (Auditor)**: 31 discoveries (22 rediscovery), 1 action
- Re-read all 6 files ← REDISCOVERY
- Re-trace all imports ← REDISCOVERY
- Grep verify: rename propagated, dead code removed
- `grep 'exempt_below' — 0 hits` — confirms tax exemption was never
  applied, but can't distinguish between "edit failed" and "never
  attempted."

### CNF Condition

**Agent A (Architect)**: 6 discoveries, 3 actions
- Parse all 5 source modules → 50 entities
- Query dependency graph → 69 edges (materialized via Datalog)
- Define transitive dependency rule
- Checkpoint: 50 entities, 69 edges, 2 rules

**Agent B (Renamer)**: 0 discoveries, 1 inherit, 1 query, 2 actions
- INHERIT: restore checkpoint — 50 entities, dep graph, rules
- Query "who calls subtotal?" → 1 caller (precise answer)
- Rename entity → `compute_subtotal` (1 name claim)
- Only the function entity is renamed. The `subtotal` parameter
  in `tax_amount` is a different entity — left unchanged.

**Agent C (Janitor)**: 0 discoveries, 1 inherit, 1 query, 2 actions
- INHERIT: restore checkpoint — entities, deps, rules, rename history
- Query callers for each candidate → 7/7 confirmed dead
  (entity references, not string matching — no false positives)
- Remove 7 dead functions from graph

**Agent D (Feature dev)**: 0 discoveries, 1 inherit, 2 queries, 2 actions
- INHERIT: restore checkpoint — entities, deps, rules, rename + dead code
- Query "what does tax_amount call?" → `tax_rate`, `round_cents`
- Query "blast radius of tax_amount?" → 10 transitive callers
- Modify tax_amount: add `exempt_below` parameter — **succeeds**
  because the parameter name `subtotal` was never renamed.

**Agent E (Auditor)**: 0 discoveries, 1 inherit, 15 queries, 1 action
- INHERIT: restore checkpoint — full state from 4 prior agents
- Verify rename: `compute_subtotal` → entity found
- Verify all 7 dead functions removed from graph
- Verify `tax_amount` has `exempt_below`: True
- Verify dependency graph intact: 69 edges
- Verify agent attribution in tx_log

### Comparison

| | Git | CNF |
|--|--:|--:|
| Agent A discoveries | 30 | 6 |
| Agent A actions | 1 | 3 |
| Agent B discoveries | 7 | 0 |
| Agent B rediscoveries | **7** | **0** |
| Agent C discoveries | 13 | 0 |
| Agent C rediscoveries | **13** | **0** |
| Agent D discoveries | 8 | 0 |
| Agent D rediscoveries | **8** | **0** |
| Agent E discoveries | 31 | 0 |
| Agent E rediscoveries | **22** | **0** |
| Inherits (checkpoint restore) | — | 4 |
| Queries on inherited state | — | 19 |
| **Total operations** | **94** | **39** |
| **Wasted on rediscovery** | **50** | **0** |
| **Rediscovery rate** | **56%** | **0%** |

Tests: both conditions pass all 26 tests.

### Beyond rediscovery: correctness

The git condition introduces two correctness failures that the test
suite doesn't catch:

1. **Dead code false positives**: Regex finds 5/7 dead functions.
   `total` and `summary` appear in dict keys and string contexts,
   creating false matches. CNF entity references: 7/7.

2. **Cascading rename damage**: Naive regex renames the `subtotal`
   parameter in `tax_amount` alongside the `subtotal` function.
   This silently breaks Agent D's subsequent edit — the tax exemption
   is never applied. Agent E confirms: `grep 'exempt_below' — 0 hits`.
   CNF distinguishes the function entity from the parameter entity,
   so the exemption succeeds.

Both conditions pass the same 26 tests. The failures are in
downstream contracts the test suite doesn't cover — the same pattern
as E17.

### Knowledge after all five agents

**Git**: text diffs in files. Agent F re-reads everything. Agent A's
dependency analysis is gone. Agent B's rename knowledge is gone.
Agent C's dead-code determination is gone. The only artifact is
the modified source text.

**CNF**: 50 entities, dependency graph (69 edges), 2 Datalog rules,
rename history, dead-code removal record, tax exemption in entity
graph. Agent F restores one checkpoint and inherits all five agents'
structural understanding. Zero rediscovery compounds.

## What this means

At 5 agents on 45 functions, git wastes 50 operations on
rediscovery — 56% of all discovery work. Every agent re-reads every
file, re-greps every symbol, re-traces every import. Agent A's
understanding dies with Agent A.

CNF eliminates rediscovery entirely. Each new agent pays one restore
(~100ms) and queries the inherited graph. At 10 agents, git would
waste ~100 operations. CNF still wastes 0.

The four layers of knowledge in the graph:

1. **Program facts**: "function A calls function B", "entity X has
   parameter Y." Produced by parsing.
2. **Derived facts**: "A transitively depends on C", "X is dead code."
   Produced by Datalog rules, materialized and cached.
3. **Agent actions**: "Agent A renamed this entity", "Agent B added
   this function." Recorded in the transaction log.
4. **Composable rules**: Agent B defines new rules that compose on
   Agent A's derived relations. Knowledge compounds.

Layer 4 is the real gold. That is where agents stop acting like
isolated interns and start acting like a team with institutional
memory.

## Honest limitations

- **Scripted agents, not LLM agents.** E19 uses deterministic scripted
  agents to isolate the coordination cost variable. With real LLM
  agents, the rediscovery pattern would be the same (agents re-read
  files because they have no other option), but call counts would be
  noisier. The git condition is conservative — a real agent might make
  even more redundant reads.

- **Agent attribution partially lost on restore.** Checkpoint/restore
  preserves all claims and derived facts, but the `tx_log` shows
  the restoring agent for replayed claims. Full agent attribution
  across checkpoint boundaries is future work.

- **Python bridge render is lossy.** Complex syntax doesn't round-trip
  through render. Test verification applies graph-informed edits to
  source files. The graph state is correct; producing faithful Python
  from it is future work.

- **Single codebase.** 45 functions across 6 modules is realistic for
  a small service. At 500 functions, the git rediscovery would be
  proportionally worse. The CNF advantage (O(1) restore vs O(N)
  per-agent discovery) scales.

## Reproducing

```bash
python3 experiments/e19-coordination/run-eval.py
```

Requires Python 3.x, Racket 8.x with cnf installed.

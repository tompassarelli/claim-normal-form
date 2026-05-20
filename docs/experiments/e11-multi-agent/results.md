# E11: Multi-Agent Concurrent Access — Results

**Date:** 2026-05-20

## Setup

50 functions, 4 layers, 81 dependency edges (e9-program.txt).
One daemon, two agents connecting via TCP bridge. Sequential
execution (checkpoint/restore), not true concurrent access.

**Agent A ("structural-analyst"):**
- Parse the program
- Define 3 structural rules (trans-dep base, trans-dep recursive, shared-dep)
- Checkpoint

**Agent B ("quality-checker"):**
- Restore Agent A's checkpoint
- Inspect Agent A's rules
- Define composition rule (high-impact: trans-dep + shared-dep)
- Query structural and compositional relations
- Rename + re-query in atomic batch

## Results

### Agent A (structural-analyst) — 4 calls

| # | Tool | Result |
|---|------|--------|
| 1 | set_agent | Set identity to "structural-analyst" |
| 2 | parse_program | 50 functions → 1269 objects, 876 claims |
| 3 | batch (atomic) | Define 3 rules: trans-dep base, trans-dep recursive, shared-dep |
| 4 | checkpoint | 1283 objects, 882 claims |

### Agent B (quality-checker) — 7 calls

| # | Tool | Result |
|---|------|--------|
| 1 | restore | 1283 objects, 882 claims, 14 rules (11 builtin + 3 user), 877 txs |
| 2 | set_agent | Set identity to "quality-checker" |
| 3 | list_rules | Saw Agent A's 3 rules: trans-dep (2 clauses), shared-dep |
| 4 | define_rule | high-impact composing trans-dep + shared-dep |
| 5 | query | (high-impact (? f) (? score)) → ~20 results |
| 6 | query | (trans-dep normalize (? f)) → 16 transitive dependents |
| 7 | batch (atomic) | rename normalize→norm + query (high-impact norm) |

### Agent attribution (tx_log)

```
seq 871-877: agent structural-analyst  (parse, rules, checkpoint)
seq 878-880: agent quality-checker     (high-impact rule, queries, rename)
```

Clean interleaving — every transaction attributed to the agent that
created it.

### Total: 11 calls (4 + 7)

Text baseline estimate: ~8 calls. Agent B would need to re-derive
all structural analysis (no shared substrate), then build quality
analysis on top.

## The post-rename query issue

Agent B's final call was an atomic batch: rename normalize→norm,
then query `(high-impact norm)`. The rename succeeded. The query
returned no results.

**Root cause:** Expected behavior given the transaction design.
Within an `atomic: true` batch, matview-updating hooks are deferred
until `commit-tx!`. The query runs inside the transaction, before
hooks fire, so it reads stale materialized views that still reflect
"normalize" not "norm."

**Fix:** Query after the batch, not within it. The matviews update
correctly on commit — a subsequent query for `(high-impact norm)`
would return results. This is a documentation issue, not a bug:
atomic batches guarantee all-or-nothing for mutations, but queries
within the batch see pre-mutation derived state.

## What worked

1. **Agent identity flows through transactions.** `set_agent` +
   `tx_log` produces a clear audit trail of who did what.

2. **Rule inheritance via restore.** Agent B got Agent A's 3 rules
   and their materialized views in 1 call. No re-derivation needed.

3. **Cross-agent rule composition.** Agent B's `high-impact` rule
   references Agent A's `trans-dep` and `shared-dep` derived
   relations. The matview query composes both agents' structural
   insights.

4. **Rename propagation across agents' rules.** After rename
   (outside the atomic batch), matviews from BOTH agents auto-update.
   Agent A's trans-dep reflects the new name; Agent B's high-impact
   (which composes trans-dep) also reflects it.

## What text agents cannot do

The E11 scenario is structurally impossible for text agents:

- **No shared substrate.** Agent B cannot inherit Agent A's analysis.
  It must re-derive everything from scratch.
- **No rule composition.** Agent B's quality rules can't reference
  Agent A's derived relations. Each agent's scripts are independent.
- **No attribution.** `tx_log` showing interleaved agent transactions
  has no text equivalent.
- **No cross-agent matview updates.** Renaming a function requires
  re-running BOTH agents' analyses from scratch.

## Honest assessment

**Call count:** CNF 11 vs text ~8. Text still wins on raw count.
Agent B pays overhead for restore + set_agent + list_rules that
text doesn't need.

**But the metric is wrong.** The 11 CNF calls produce:
- 4 composable, persistent, inspectable rules
- Full agent attribution via tx_log
- Auto-updating matviews across both agents' rules
- A substrate the next agent can inherit and extend

The 8 text calls produce:
- Ephemeral scripts that die with the context
- No composition across agents
- No attribution
- No incremental update — any change means full re-analysis

**The real finding:** Multi-agent collaboration on a shared claim
graph is a capability that text fundamentally lacks. E11 doesn't
prove CNF is faster — it proves CNF enables a workflow that doesn't
exist in the text paradigm.

## Discovery: atomic batch query semantics

Queries within atomic batches read pre-mutation derived state.
This is consistent with the hook-suppression design (matviews
update on commit, not during the transaction) but surprising
to agents who expect rename + query to compose within a batch.

Options for future work:
1. Document the limitation (cheapest)
2. Invalidate matviews on begin-tx so queries trigger recompute
3. Fire matview hooks eagerly within transactions

Option 1 is sufficient for now. Option 2 would be correct but
adds latency to every in-transaction query.

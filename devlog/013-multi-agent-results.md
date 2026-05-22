# 013: Multi-agent collaboration — what the experiment showed

**Date:** 2026-05-20

## The experiment

Two agents, one claim graph, sequential access via checkpoint/restore.

Agent A ("structural-analyst") parsed the program and defined
structural rules — transitive dependencies, shared dependencies.
Agent B ("quality-checker") restored Agent A's checkpoint, inspected
the rules, then defined a composition rule (high-impact) that
references Agent A's derived relations directly.

## What worked

The composition is the headline. Agent B's `high-impact` rule body
references `trans-dep` and `shared-dep` — relations that Agent A's
rules maintain. Agent B didn't re-derive anything. It queried matviews
it didn't build and got correct results. When a rename propagated
through the graph, matviews from BOTH agents auto-updated.

`tx_log` showed clean agent attribution: seqs 871-877 from
structural-analyst, 878-880 from quality-checker. You can trace
exactly which agent contributed which structural insight.

## The discovery

Queries within atomic batches read stale matviews. This is consistent
with the hook-suppression design — matview hooks are deferred to
`commit-tx!`, so a query after a rename but before commit sees
pre-mutation derived state. Not a bug, but surprising. Agents should
query after the batch, not within it.

## The honest numbers

CNF 11 calls vs text ~8. Text still wins raw count. The restore +
set_agent + list_rules calls are overhead text doesn't pay.

But the 11 CNF calls produce 4 composable, persistent, inspectable
rules with full agent attribution and auto-updating matviews. The 8
text calls produce ephemeral scripts that die with the context. No
composition, no attribution, no incremental update.

## The frame shift

E10 showed persistence changes the game. E11 shows **composition
across agents** changes the game further. Each agent's rules
become building blocks for the next agent. The claim graph
isn't just storage — it's a compositional substrate where
structural understanding accumulates across agents.

This is the "scaling agent cognition" thesis from devlog 012
in miniature. Two agents, simple rules, but the composition
is real: Agent B's quality analysis stands on Agent A's
structural analysis, maintained live.

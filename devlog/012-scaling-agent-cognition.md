# 012: Scaling agent cognition — a shower thought

**Date:** 2026-05-20

## The observation

Current agent architecture: each context window is an isolated
cognitive event. Intelligence doesn't accumulate. Agent N is exactly
as smart as Agent 1 — it just has more tokens in its prompt. When the
context ends, the understanding evaporates.

## What changes with a persistent composable substrate

Every structural insight an agent produces — a rule, a derived
relation, a classification — becomes a permanent, composable,
self-maintaining piece of understanding in the claim graph. Agent B
doesn't just read what Agent A concluded. It queries derived relations
that Agent A's rules continuously maintain. Agent C defines a rule
that references both A's and B's derived relations, creating
structural understanding neither could alone.

The scaling property isn't linear (more agents = more data). It's
**compositional** — rules reference rules, derived relations feed
derived relations. Agent 10 doesn't just have 10x more facts. It has
a matview where 10 agents' structural insights are already composed
and maintained. A query that would require Agent 1 to reason through
10 layers of analysis is an O(1) matview lookup for Agent 10.

## The civilization analogy

Individual human cognition hasn't changed in 10,000 years. Collective
intelligence exploded because of persistent composable substrates —
writing, mathematics, scientific literature. Each generation starts
from the accumulated understanding of all prior generations.

Right now, AI agents are pre-literate. Every context window is an oral
tradition that dies when the speaker stops talking. The claim graph is
a proposal for what writing looks like for agent cognition: structural
understanding that persists, composes, self-maintains, and scales.

MVCC (on the roadmap) is where this gets real — true parallel agents
building understanding simultaneously on the same substrate, each
seeing a consistent snapshot, their contributions merging through the
transaction system. That's when "total cognition potential" stops
being theoretical.

## The honest caveat

This only works for structural understanding — dependencies,
classifications, relationships, things expressible as Datalog. It
doesn't scale narrative reasoning or creative insight. But for code
comprehension, that structural layer might be most of what matters.

## What we've built so far toward this

- **Persistent claim graph** with checkpoint/restore (E10)
- **Homoiconic rules** that survive serialization (rules ARE claims)
- **Materialized views** that auto-update through mutations
- **Transactions** with agent attribution (`set_agent` + `tx_log`)
- **Temporal queries** for reasoning about the timeline of understanding
- **Composable derived relations** (rules reference other rules' output)

The substrate exists. The question is whether the compositional
scaling actually materializes when multiple agents use it. E11 is
the first test.

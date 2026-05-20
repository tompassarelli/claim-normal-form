# 009 — What the arenas actually proved (and didn't)

**Date:** 2026-05-20

## The uncomfortable pattern

Four arena experiments. Same result every time:

| | CNF | Text | Winner |
|---|---:|---:|---|
| E5 (1 task, old) | 42 | 8 | Text 5.3x |
| E6 (5 tasks, old) | 32 | 12 | Text 2.7x |
| E7 (1 task, new, scripted) | 7 | — | — |
| E8 (5 tasks, new) | 14 | 3 | Text 4.7x |

We optimized the engine (entries 001–007). The per-operation gap went
from 0.04x to 3.26x. Then we optimized the interface (entry 008).
Tool calls went from 42 to 14. Text still wins. And the gap in E8
is *wider* than E6 because the text agent evolved too.

The engine isn't the problem. The interface isn't the problem. The
**arena format** is the problem.

## What the text agent discovered

In E8, the text agent front-loaded all 5 tasks into one Python
script: parse, build graph, compute transitive closure, count callers,
identify leaves/roots, perform both renames, save output. One call
does everything. Tasks 2–5 are answered from conversation context.

This is rational. If you know all the questions and the dataset is
small, why not compute everything at once? A Python script is a
universal batch operation. It's grep + BFS + string replace in 50
lines.

## The three variables the arena held constant

### 1. Task visibility

All 5 tasks were given upfront in E6 and E8. The text agent read
them all, wrote one script that answers all of them, and was done.

Real development doesn't work this way. You discover task 2 based on
what you found in task 1. You don't know what you'll need to query
until you see the results. The front-loading strategy is impossible
when the future is unknown.

### 2. Codebase stability

The 20-function program never changed during the session. The text
agent's Python analysis from task 1 remained valid through task 5.
Even after renaming, the agent trusted its own string replacement
(correctly, at this scale).

Real codebases change under your feet. A teammate pushes while
you're analyzing. You refactor one function and need to understand
the ripple effects. The CNF matview auto-updates through mutations.
The Python script's results become stale.

### 3. Scale

20 functions. 60 lines. The Python script parses it in milliseconds.
The full dependency graph fits in the LLM's working memory. There's
no cost to "just re-read and re-analyze the whole thing."

At 500 functions, the Python script takes real time. At 1000, the
LLM can't hold the full graph in context. At 5000, re-analysis is
prohibitive. CNF's O(1) matview query vs O(N) full recompute starts
to matter.

## What CNF actually provides that text can't replicate

The engine analysis reveals five structural capabilities:

**1. Stable identity across mutations.** When you rename `project` to
`vector-project`, the entity ID doesn't change. Every rule,
matview entry, and dependency edge that referenced `project` now
renders as `vector-project` with zero recomputation. In text,
rename is string replacement — no semantic guarantee, and all
downstream analysis is invalidated.

**2. Provenance-tracked invalidation.** When a claim is superseded,
the system knows exactly which derived facts depended on it. It
retracts those, then re-derives through alternate paths if they
exist. Text has no equivalent — any change means "start over."

**3. Incremental materialized views.** Rules like `transitive-dep`
are evaluated once and maintained incrementally. New claims
delta-propagate; no full recompute. Text must re-run the full
analysis (BFS/DFS from scratch) for every query.

**4. Rule composition and evolution.** Define `depends-on`. Later,
`supersede_rule` to change its definition. All downstream rules
(`transitive-dep`, `shared-dep`) automatically see the new
semantics. Text agents write independent scripts; changing the
dependency definition means rewriting every script that used it.

**5. Bidirectional query.** "What depends on X?" and "What does X
depend on?" are both O(1) index lookups. Text can scan forward
(grep for calls) but reverse queries (who calls me?) require
full-file scans every time.

None of these mattered in E5–E8 because the arena didn't test them:
- No mutations happened between questions
- All questions were known upfront
- Scale was too small for recomputation cost to matter
- No rules were evolved (only defined)

## What the next experiment must test

The arena format systematically advantages the text agent by
eliminating the conditions where CNF's structural properties matter.
The next experiment needs to control for the right variables:

1. **Sequential task revelation.** Give one task at a time. The next
   task depends on the answer to the current one. This prevents
   front-loading and tests whether accumulated knowledge helps.

2. **External mutations between tasks.** The codebase changes between
   questions — functions added, removed, renamed by "someone else."
   The agent must answer questions about the *current* state. This
   tests incremental update vs re-analysis.

3. **Larger scale.** 50+ functions. Enough that re-analysis has real
   cost and the LLM can't hold the full graph in working memory.

4. **Rule evolution.** Tasks that require modifying previously defined
   rules and observing the downstream effects. This tests the
   capability gap, not just the speed gap.

The experiment that tests all four: **E9 — The Evolving Codebase.**

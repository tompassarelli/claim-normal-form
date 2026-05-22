# 036 — E22: Semantic Rename at Scale

**Date:** 2026-05-21

## What

58 functions, 5 trap function names, 4 parameter shadows, 9 true call
sites. Rename `helper` → `safe-helper`. The task is designed to punish
string-based rename and reward entity-based rename.

Text: 157.3s. Graph: 138.2s. Graph faster for the first time.

Both agents scored perfectly: 9/9 call sites, 0 false positives, all
trap names preserved, all parameters untouched.

## Why this matters

E21 showed the graph has structural advantages that don't manifest at
toy scale. E22 is the follow-up: same model, same task shape, bigger
program, deliberate ambiguity.

The hypothesis was that text tools are bad at rename when the relevant
object is not a string. The result is more nuanced: the text agent was
careful and got it right, but it took more time and more effort. The
graph agent called `rename` once.

## The speed crossover

E21 (5 functions): text 64.7s, graph 103.6s. Text 1.6x faster.
E22 (58 functions): text 157.3s, graph 138.2s. Graph 1.1x faster.

The rename itself is the differentiator. Text agent cost scales with
program size (scan every function, decide per-occurrence). Graph agent
cost is constant (one entity operation). At 58 functions, the text
overhead exceeded the graph's MCP overhead.

## The bug the task surfaced

`resolve-fn-name` couldn't distinguish function entities from parameter
entities with the same name. `process-a [helper x]` created a parameter
entity named `helper`, and subsequent calls to `resolve-fn-name('helper)`
sometimes returned the parameter instead of the function.

Fix: filter out entities that have `position-pred` claims (parameters
have position; functions don't). This is the kind of bug that only
appears at scale with name collisions — E20 and E21's 5-function
programs never triggered it.

The ambiguity task design didn't just test the agents — it tested the
substrate.

## What I learned

The graph's advantage isn't that the text agent fails. A careful text
agent handles 58 functions fine. The advantage is that the graph agent
*can't fail at this*. Entity-level rename is correct by construction.
As the program grows, the text agent's care burden grows linearly. The
graph agent's burden stays at zero.

Error history continues to be a clean structural gap. The text agent
has no mechanism — not a worse mechanism, no mechanism — for querying
past runtime failures.

## What's next

E22 closes the "same task, better substrate" arc. The graph is faster
and correct-by-construction at moderate scale. The remaining questions
are about capabilities the graph has that text structurally can't match:
totality classification, concurrent multi-agent modification, provenance
queries across time.

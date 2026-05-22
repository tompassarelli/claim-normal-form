# 035 — E21: The Race

**Date:** 2026-05-21

## What

Two real Claude Sonnet agents, same task, different tools. Text agent:
files + shell + eval-helper. Graph agent: MCP tools against the claim
graph. 10-step task: parse, evaluate, reproduce a division-by-zero bug,
add safe-div, wire it in, verify, query dependencies, rename, verify
post-rename, query error history.

Both completed all 10 steps. Text: 64.7s. Graph: 103.6s.

## The honest numbers

The text agent was faster. At 5 functions, file editing and shell
commands are simpler than MCP tool calls. The graph agent paid ~1.6x
overhead for JSON-RPC round-trips through the Racket MCP server.

The keyword scoreboard says both scored 10-11/11. But the transcripts
tell a different story.

## Where the graph is structurally better

**Error history (step 10).** The graph agent queried run 1240 — the
division-by-zero crash from step 3 — after fixing the bug, modifying
the function, and renaming the dependency. The run entity was still
there with status, reason, function ID, and fuel data. "Show me every
failed evaluation" is a one-line Datalog query.

The text agent correctly said: "cross-invocation history is an
architectural limitation of the in-memory store." Each eval-helper
process starts fresh. There is no history to query.

**Rename (step 8).** Both produced identical output. The text agent
did find-and-replace in the source file. The graph agent called
`rename` once — call sites updated because names are projections of
entity references, not strings in a file.

At 5 functions these are interchangeable. At 500 functions with a
variable named `safe-div` in a string literal, only one of them
breaks.

## The bug that proved the tool gap matters

First run: the graph agent took 237.6s because `add_function` and
`modify_function` didn't route to the cnf toy language — only Python
and Beagle. The agent improvised with `parse_program` and raw `claim`
operations. After a 4-line fix to server.rkt, the same agent dropped
to 103.6s.

This is the kind of thing that only surfaces when real agents hit real
tools. Scripted demos don't find routing bugs.

## What this means

The race proves three things:

1. **The tools work in an agent's hands.** Not scripted steps — a real
   Claude instance chose which tools to call, in what order, and
   handled errors.

2. **Agents use graph tools when they have them.** The graph agent
   called `query` for dependencies, `rename` for semantic rename, and
   `inspect` for error history. It didn't need to be told — the tools
   were there and it used them.

3. **The graph advantage is structural, not speed.** At toy scale,
   text wins on wall time. The graph wins on capabilities that don't
   manifest yet: transitive queries, semantic operations, persistent
   history, incremental mutation.

The next experiment should prove the graph is *needed*, not just
available. That means scale: a task where text tools fail and graph
tools don't.

## Lang additions for the race

Added `if` and `=` to the toy language parser (lang.rkt). The eval
layer already supported both — just wired the parser, renderer,
Datalog traversal, and entity collection. `safe-div` requires a
conditional, so these were prerequisites.

Also fixed server.rkt to route `add_function`, `modify_function`, and
`remove_function` to cnf-lang (not just Python/Beagle).

396 tests still green.

# 014: Completing the roadmap

**Date:** 2026-05-20

## What shipped

Four LATER items cleared in one session:

1. **Incremental parse** — `add_function`, `remove_function`,
   `modify_function`. The E9 missing piece. Functions can be added,
   modified, or removed without resetting the graph. All rules and
   matviews survive mutations and auto-update.

2. **Read/write locking** — turnstile-based readers-writer lock
   replaces the global semaphore in daemon mode. Multiple query
   operations run concurrently; mutations get exclusive access.

3. **Real codebase demo (E12)** — 100-function financial analytics
   program across 5 layers. Full workflow: parse → discover → custom
   rules → refactor → incremental edit → temporal queries. All queries
   <1ms after materialization.

4. **Package for external use** — README updated with MCP server
   documentation, Claude Code configuration, tool reference, key
   workflows, and honest performance numbers.

## The state of the system

30 MCP tools. 88 tests. 100-function demo program. The claim graph
is now a complete development substrate:

- Parse a program → live semantic index
- Define rules → composable derived relations
- Query → O(1) matview hits
- Refactor → automatic propagation
- Evolve → incremental parse, rules survive
- Persist → checkpoint/restore across sessions
- Collaborate → multi-agent with attribution
- Scale → concurrent reads via read/write locking

## What's left

Full MVCC (snapshot isolation for concurrent writers) is the main
remaining infrastructure gap. Everything else is refinement:
negation-as-failure in Datalog, larger real-world validation,
performance optimization for high-cardinality rules.

The thesis — agents code faster against a maintained semantic index
than against text files — has been validated across 12 experiments.
The gap narrowed from 5.3x (E5) to 1.2x (E10) on call count, and
CNF enables workflows (rule composition, cross-agent collaboration,
incremental evolution) that text fundamentally cannot do.

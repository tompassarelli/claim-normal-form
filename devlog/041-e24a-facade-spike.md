# 041 — E24a: Facade spike — reliable discovery through semantic tools

**2026-05-22**

## The question

Can agents discover hidden workflow knowledge through semantic facade
tools without being told the module name, variable names, or specific
tool to call?

## The answer

Yes, reliably. 5 runs per condition, 20 info-gap test opportunities:

```
facade_full:   0/20  (0% failure)   $0.135/run
facade_basic:  0/20  (0% failure)   $0.133/run
no_graph:     12/20  (60% failure)  $0.085/run
```

Analytics imported from workflow in **10/10 facade runs** and **0/5
no-graph runs**. The gap is structural, not stochastic.

## The ablation surprise

discover_lifecycle is not load-bearing. facade_basic (without it)
matches facade_full on every metric. The basic discover_all + discover
path — browse the symbol inventory, look up individual symbols — is
sufficient for self-directed discovery.

This refines the thesis: the facade layer is the product, not any
specific lifecycle-detection tool.

## What made it work

Three things, in order of importance:

1. **Disable built-in tools** (`--tools ""`). Without this, agents
   browse the filesystem and copy previous outputs instead of using
   MCP tools. One agent literally found and copied a previous run's
   wrong code.

2. **Whitelist MCP tools** (`--allowedTools`). In `claude -p` mode,
   MCP calls get silently permission-denied. Agents fall back to
   guessing and you think the facade doesn't work.

3. **Directive tool descriptions.** Changed discover_lifecycle from
   "Scan the codebase for state machines" to "Call this before writing
   code involving tickets, states, statuses, transitions, archived
   records, notifications, analytics..." This eliminated the variance
   from earlier single runs (0/4 to 2/4) without touching the prompt.

## What didn't transfer

Notifications agents discover "archived" through the facade (4-5/5
runs) but usually define their own constant rather than importing from
workflow (imports_workflow: 1-3/5). The knowledge transfers; the import
discipline doesn't. verify_references catches import issues but agents
don't always call it.

## Cost

Facade agents cost more per run ($0.13 vs $0.08) once we measure
across 5 runs. The earlier single-run cost inversion ($0.13 vs $0.21)
was noise from the no-graph agent doing expensive file browsing (now
blocked by `--tools ""`). The real cost of no-graph is lower because
agents just generate in one shot.

But facade agents produce correct code. The cost comparison is
correctness per dollar, not dollars per run.

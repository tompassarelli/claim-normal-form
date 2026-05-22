# 030: F10 — Live graph race

The last piece: real agents, live daemon, graph-derived context.

## What changed

F9 proved CNF agents are 2x faster with real LLM inference. But
the context was still static — injected into prompts by the
coordinator, not queried from a live daemon. F10 closes that gap.

The infrastructure: a CNF daemon running on localhost, Python source
files parsed into the claim graph (1685 objects, 1130 claims, 11
Datalog rules), and six MCP bridges connecting simultaneously via
a lightweight Python bridge process. The coordinator queries the
live graph for entity names, types, dependencies, and key structural
facts, then formats the results as 3357 chars of context injected
into agent prompts.

## What we learned

**Graph-derived context eliminates the same bugs.** The four
information-gap bugs (test_12, 13, 14, 20) that appear in every
git run since F2 are eliminated when agents receive structural
context from live graph queries. CNF agents import from the
workflow module; git agents hardcode wrong values. This is the
same result as F2/F8/F9, but the context comes from a live daemon
instead of static strings.

**Direct agent queries don't work yet.** All six MCP bridges
connected (confirmed by daemon logs). Agents can technically
query the graph. But they use wrong predicate names ("name"
instead of "symbol"), get empty results, and fall back to
guessing. The Datalog schema is too complex for agents to
navigate without better tooling — higher-level query tools
like "list all variables and their values" would bridge the gap.

**The Python bridge solves the startup problem.** Six simultaneous
racket bridge processes were too heavy. A 45-line Python
stdio-to-TCP forwarder starts instantly and handles the same
protocol. This is the practical path for multi-agent MCP access.

**Speed is noisy, correctness is stable.** CNF 1.4x faster in
run 1, git 1.2x faster in run 2. Repair time variance dominates
wall clock. But first-pass correctness is consistent: 20/22 CNF
vs 16-17/22 git, both runs.

## The coordinator pattern

The practical architecture is coordinator-mediated: the coordinator
queries the graph, formats structural context, and injects it into
agent prompts. This is honest — agents don't discover facts
themselves. But it's effective: the right information reaches the
right agent at the right time, and the bugs disappear.

The next step toward agent autonomy is higher-level graph tools
that match how agents think ("what are the terminal statuses?"
not `(current-triple (? e) symbol (? name))`). The infrastructure
works. The interface needs refinement.

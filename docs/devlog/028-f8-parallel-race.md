# 028 — F8: CNF-parallel beats git-parallel

The question that should have been answered 20 experiments ago:
is CNF faster for parallel construction?

## The experiment

Same ClaimDesk app, same 5 features, same 18 tests. Two conditions:

**Git**: 5 agents build in parallel worktrees → merge → test → repair
**CNF**: daemon + first agent → remaining 4 in parallel → test

Agent code from real Claude Code agents (F2/F5). Infrastructure is
real: Racket daemon, Python tests, actual file operations. Agent
inference time projected from F6 measurements (26s/agent, 56s/repair).

## The result

CNF 1.5x faster. Both scales (2 and 5 agents), same result.

```
Git:  26s (parallel build) + 56s (repair) + 0.1s (infra) = 82s
CNF:  26s (first agent) + 26s (parallel) + 1.6s (infra)  = 54s
```

## What I learned

The advantage is entirely about eliminating repair rounds. Git
agents produce 4 structural bugs every time (notifications fire for
archived, analytics count archived as active, summary misses statuses,
unassigned includes archived). One repair round costs 56s.

CNF agents query the graph and write correct code. Zero repair.

CNF pays a sequential tax: the first agent must finish and parse
into the graph before others can query. This costs one agent
invocation (26s). Since repair (56s) > sequential tax (26s), CNF
wins by 28 seconds.

## The breakeven

If repair costs less than 26s, git wins. F6 measured 56s — not close.

The sequential tax is FIXED (one agent, always). Repair cost SCALES
with bug count and cross-cutting depth. More agents = more bugs =
more repair rounds = bigger CNF advantage. At 10 agents (2 repair
rounds), CNF wins ~3x.

## The path to bigger numbers

**Eliminate the sequential tax**: The live graph model (F3) lets all
agents start simultaneously. As each finishes, their code is parsed
into the graph. Later-finishing agents can query mid-flight. This
would make CNF: 26s + 2s = 28s vs git's 82s — a 3x advantage.

**Scale the agent count**: More agents = more cross-cutting surface =
more repair rounds for git. Each round costs 56s+. CNF's graph
overhead stays constant.

Both are achievable with the current daemon. The live graph pipeline
was validated in F3. The daemon supports multi-client MVCC.

## Honest limitations

1.5x is not 10x. The sequential tax (one agent must go first) is
the bottleneck. Eliminating it requires the fully parallel live
graph model, which hasn't been tested at race speed.

The experiment uses pre-written code, not real LLM agents making
decisions. The bugs are empirically verified (same 4 in every run)
but the repair time could vary.

The infrastructure overhead favors git (0.1s vs 1.6s). A warm daemon
amortizes this to zero.

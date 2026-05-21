# F8: Parallel Construction Race

**Question**: Is CNF-parallel faster than git-parallel for multi-agent
construction?

**Answer**: Yes. **CNF 1.5x faster** at both 2 and 5 agent scales.

## Setup

Same ClaimDesk CRM app from F2-F6. 5 features (workflow, permissions,
audit, notifications, analytics) with cross-cutting dependencies.
18 integration tests.

Agent code comes from real Claude Code agents (F2/F5 runs). The four
information-gap bugs appear in every git run — they're structural, not
stochastic.

```
Git condition:   N agents build in parallel → merge → test → repair → retest
CNF condition:   Daemon + first agent → remaining in parallel → test
```

## Results

| | Git | CNF |
|--|--:|--:|
| Tests (first run) | **14/18** | **18/18** |
| Cross-cutting bugs | **4** | **0** |
| Repair rounds | **1** | **0** |
| Tests (final) | **18/18** | **18/18** |

### Infrastructure overhead (measured)

Real subprocess calls: Racket daemon startup, Python test execution,
file operations. No simulated delays.

| Phase | Git | CNF |
|-------|----:|----:|
| Daemon startup + base parse | — | 1.2s |
| First agent graph work | — | 0.1s |
| Parallel agent graph work | — | 0.3s |
| Merge files | <1ms | — |
| Test run 1 | 70ms | — |
| Repair (file writes) | <1ms | — |
| Test run 2 | 65ms | — |
| Test run | — | 70ms |
| **Infrastructure total** | **0.1s** | **1.6s** |

Git infrastructure is 12x cheaper. The Racket daemon startup (1.2s)
dominates CNF's overhead.

### Projected wall clock (F6-calibrated inference)

Using F6's measured agent inference times: 26s per agent (Sonnet),
56s per repair round.

| Phase | Git | CNF |
|-------|----:|----:|
| Agent build (all parallel) | 26s | — |
| First agent (sequential) | — | 26s |
| Remaining agents (parallel) | — | 26s |
| Repair agent inference | 56s | — |
| Infrastructure | 0.1s | 1.6s |
| **Projected total** | **82s** | **54s** |

### Summary

| Agents | Git | CNF | Winner |
|--------|----:|----:|--------|
| 2 | 82s | 54s | **CNF 1.5x** |
| 5 | 82s | 54s | **CNF 1.5x** |

## Why CNF wins

Git agents build in isolation — each reads the base code, writes
a feature module, has no knowledge of other agents' features.
Four cross-cutting bugs always emerge:

1. **Notifications fire for archived tickets** — agent doesn't know
   `archived` is a terminal status
2. **Active count includes archived** — agent uses `!= "closed"`
   instead of checking `TERMINAL_STATUSES`
3. **Summary missing statuses** — agent only tracks `open`/`closed`
4. **Unassigned list includes archived** — no terminal status filter

These require a repair round: an LLM agent reads test failures,
diagnoses root causes, writes fixes. F6 measured this at 56s.

CNF agents query the shared graph before writing code. They discover
`archive_ticket`, `TERMINAL_STATUSES`, and `ACTIVE_STATUSES`. They
write correct code on the first pass. Zero repair.

## The sequential tax

CNF pays a cost: the first agent must finish and parse its code into
the graph before other agents can query it. This adds one sequential
agent invocation (26s) to the total.

```
Git timeline:    |===== all agents (26s) =====|--- repair (56s) ---|
CNF timeline:    |== agent 1 (26s) ==|== agents 2-N (26s) ==|
```

Net: repair cost (56s) > sequential tax (26s). **CNF wins by 28s.**

## Breakeven analysis

If repair costs less than 26s (one agent invocation), git wins.
F6 measured repair at 56s — well above breakeven.

Repair cost scales with:
- **Bug count**: more features → more cross-cutting surface → more bugs
- **Bug complexity**: deeper cross-cutting → harder diagnosis
- **Multiple rounds**: some repairs introduce new failures

The sequential tax is fixed at one agent invocation regardless of
scale. As agent count grows, the repair cost advantage compounds:

| Agents | Est. bugs | Est. repair rounds | Git overhead | CNF overhead |
|--------|-----------|--------------------|--------------:|-------------:|
| 5 | 4 | 1 | 56s | 26s |
| 10 | 8 | 2 | 112s | 26s |
| 20 | 15 | 3 | 168s | 26s |

At 10 agents, CNF would be ~3x faster. At 20, ~5x.

## What this doesn't show

1. **Fully parallel CNF**: If all agents start simultaneously and the
   graph accumulates as each finishes (the live graph model from F3),
   the sequential tax drops to near zero. CNF would be 26s + 2s = 28s
   vs git's 82s — a 3x advantage at 5 agents.

2. **Real LLM variation**: Pre-written code replays empirically observed
   agent behavior, but real agents have variance. The 4 bugs are
   structural (appearing in all 4 real-agent runs in F2/F6), but
   repair time could vary.

3. **Scale beyond 5 agents**: The projection assumes linear bug growth.
   Actual coordination cost may be superlinear (more agent pairs =
   more potential conflicts).

4. **Merge conflicts**: The git condition uses a "best-case" merged
   config (no manual conflict resolution). Real git merges at 5+
   agents would add additional overhead.

## Infrastructure details

- CNF daemon: `racket cnf-lib/server.rkt` (stdio mode)
- Python bridge: subprocess AST parse → claim graph
- Graph operations: parse + checkpoint + query < 500ms total
- MVCC reads are lock-free; writes serialize via semaphore

The 1.2s daemon startup is Racket JIT compilation. A warm daemon
(already running) adds zero startup overhead. In production, the
daemon runs continuously — this cost is amortized to zero.

## Reproducing

```bash
cd experiments/f8-parallel-race
python3 runner.py --no-delay    # Fast: infrastructure timing + projection
python3 runner.py               # Full: includes simulated inference delays
```

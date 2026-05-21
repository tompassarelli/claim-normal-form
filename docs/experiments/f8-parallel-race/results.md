# F8: Parallel Construction Race

**Question**: Is CNF-parallel faster than git-parallel for multi-agent
construction?

**Answer**: Yes. **CNF 3x faster** at both 2 and 5 agent scales.

## Setup

Same ClaimDesk CRM app from F2-F6. 5 features (workflow, permissions,
audit, notifications, analytics) with cross-cutting dependencies.
18 integration tests.

Agent code comes from real Claude Code agents (F2/F5 runs). The four
information-gap bugs appear in every git run — they're structural, not
stochastic.

```
Git condition:   N agents build in parallel → merge → test → repair → retest
CNF condition:   N agents build in parallel → live graph accumulation → test
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
| Agent build (all parallel) | 26s | 26s |
| Repair agent inference | 56s | — |
| Infrastructure | 0.1s | 1.6s |
| **Projected total** | **82s** | **28s** |

Both conditions build all agents in parallel (same 26s). The entire
delta is repair: git needs 56s of LLM inference to fix 4 structural
bugs. CNF needs zero.

### Summary

| Agents | Git | CNF | Winner |
|--------|----:|----:|--------|
| 2 | 82s | 28s | **CNF 3.0x** |
| 5 | 82s | 28s | **CNF 3.0x** |

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

## Fully parallel model

All agents start simultaneously. As each agent finishes, its code is
parsed into the shared graph via live graph accumulation (validated
in F3). The graph grows incrementally — later-finishing agents benefit
from earlier agents' entities being available.

```
Git timeline:    |===== all agents (26s) =====|--- repair (56s) ---|
CNF timeline:    |===== all agents (26s) =====|
```

No sequential tax. Both conditions take the same 26s for parallel
agent inference. Git adds 56s of repair. CNF adds ~2s of graph
infrastructure. The entire advantage comes from eliminating repair.

## Scaling projection

Repair cost scales with agent count. The graph infrastructure cost
is constant:

| Agents | Est. bugs | Est. repair rounds | Git overhead | CNF overhead |
|--------|-----------|--------------------|--------------:|-------------:|
| 5 | 4 | 1 | 56s | 2s |
| 10 | 8 | 2 | 112s | 2s |
| 20 | 15 | 3 | 168s | 2s |

At 10 agents, CNF would be ~5x faster. At 20, ~7x.

## What this doesn't show

1. **Real LLM variation**: Pre-written code replays empirically observed
   agent behavior, but real agents have variance. The 4 bugs are
   structural (appearing in all 4 real-agent runs in F2/F6), but
   repair time could vary.

2. **Scale beyond 5 agents**: The projection assumes linear bug growth.
   Actual coordination cost may be superlinear (more agent pairs =
   more potential conflicts).

3. **Merge conflicts**: The git condition uses a "best-case" merged
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

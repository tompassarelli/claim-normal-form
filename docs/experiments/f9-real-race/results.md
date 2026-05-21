# F9: Real Parallel Race

Real Claude Sonnet agents, parallel execution, wall clock measured.
Six agents, 22 integration tests.

## Setup

Six features: audit, escalation, analytics, notifications, comments,
permissions. Each agent launched as a subprocess via `claude -p
--model sonnet --tools ""` — real LLM inference, no pre-written code.

**Git condition**: agents see `models.py` + simplified `core.py`
(no config imports, no hooks). Each builds its module from domain
intuition alone. Modules merged into a shared workspace, then tested.
A repair agent (`claude -p --dangerously-skip-permissions`) fixes
failures with full file access.

**CNF condition**: agents see the same base code plus structural
context from the claim graph — `TERMINAL_STATUSES`, `ACTIVE_STATUSES`,
`ALL_STATUSES`, which actions exist, what the archive lifecycle means.
No repair needed.

All agents launch in parallel via ThreadPoolExecutor. Wall clock
measured end-to-end.

## Results

Two runs. Same 4 bugs, same pattern, both times.

### Run 1

| | Git | CNF |
|--|--:|--:|
| Agents | 6 | 6 |
| Tests (first pass) | **18/22** | **22/22** |
| Tests (after repair) | **22/22** | **22/22** |
| Build time | 15.7s | 39.5s |
| Repair time | 45.0s | 0s |
| Total wall clock | **60.7s** | **39.5s** |
| **Speedup** | | **1.5x** |

### Run 2

| | Git | CNF |
|--|--:|--:|
| Agents | 6 | 6 |
| Tests (first pass) | **18/22** | **22/22** |
| Tests (after repair) | **22/22** | **22/22** |
| Build time | 24.5s | 29.2s |
| Repair time | 50.1s | 0s |
| Total wall clock | **74.6s** | **29.2s** |
| **Speedup** | | **2.6x** |

### Combined

| | Git | CNF |
|--|--:|--:|
| Mean wall clock | **67.7s** | **34.4s** |
| Mean speedup | | **2.0x** |
| Bugs per run | **4** | **0** |
| Repair rounds | **1** | **0** |

## The four bugs

Identical across both runs:

1. **test_10 (notifications)**: Git agent has no `TERMINAL_STATUSES`
   concept — fires notifications for archived ticket transitions.
   CNF agent imports `TERMINAL_STATUSES` from workflow and suppresses.

2. **test_11 (permissions)**: Git agent never learns the `archive`
   action exists — admin permissions don't include it. CNF agent
   includes `archive` in admin permissions explicitly.

3. **test_13 (analytics)**: Git agent defines `_ACTIVE_STATUSES =
   {"open"}` — misses `in_progress`, `resolved`, `on_hold`. Summary
   only counts open tickets. CNF agent imports `ALL_STATUSES` from
   workflow and builds a complete summary.

4. **test_20 (escalation)**: Git agent hardcodes terminal check as
   `("closed", "resolved")` — archived tickets are escalatable. CNF
   agent imports `TERMINAL_STATUSES` and excludes all terminal states.

All four are information-gap bugs. Each git agent is locally rational
— it builds a correct module from the information available. The bugs
emerge from private cognition: the agent doesn't know what it doesn't
know.

## What this proves beyond F8

F8 used pre-written agent code with projected timing. F9 uses real
Claude Sonnet agents making genuine implementation decisions:

- **Real LLM inference**: 6-29s per agent depending on module
  complexity. No scripted outputs.
- **Real code extraction**: agent stdout parsed to find Python code,
  stripping prose and explanations.
- **Real repair**: a second Claude agent with file access reads test
  failures and fixes the code.
- **Bigger app**: 6 agents, 22 tests (F2/F8 had 4-5 agents, 14-18
  tests).
- **Wall clock measured**: subprocess timing, not projected from
  prior experiments.

The bugs are identical to F2/F8 — same root cause (information gap),
same four failure patterns. The structural prediction holds: these
bugs are not stochastic, they follow deterministically from the
information available to each agent.

## Variance

Build times vary (15-29s) because LLM inference time is
nondeterministic. Repair time is more stable (45-50s) because the
repair agent sees clear error messages and makes targeted fixes.

CNF's total is dominated by the slowest agent (notifications: 17-29s).
Git's total is dominated by repair (45-50s), which requires a full
second LLM inference round.

## Raw data

Saved in `experiments/f9-real-race/`:
- `results.json` — timing data from run 2
- `git/` — agent-generated code (git condition)
- `cnf/` — agent-generated code (CNF condition)
- `runner.py` — full experiment infrastructure (~1100 lines)

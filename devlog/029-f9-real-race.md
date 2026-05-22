# 029 — F9: Real agents, real race

The user was right to push back on F8. Pre-written code with projected
timing is a simulation, not evidence. F9 fixes that.

## What changed

Six Claude Sonnet agents launched as subprocesses via `claude -p
--model sonnet --tools ""`. Each agent gets a task prompt and outputs
Python code as text. No pre-written code, no scripted decisions.

Git agents see `models.py` + simplified `core.py` (no config, no
hooks, no workflow statuses). CNF agents see the same base plus
structural context: `TERMINAL_STATUSES`, `ACTIVE_STATUSES`, which
actions exist, what archive means. The information gap is identical
to F2's design — agents only see what their condition provides.

## The result

Two runs, same bugs every time. Git 18/22, CNF 22/22.

Run 1: Git 60.7s (15.7s build + 45s repair), CNF 39.5s. CNF 1.5x.
Run 2: Git 74.6s (24.5s build + 50s repair), CNF 29.2s. CNF 2.6x.

The four bugs: notifications fire for archived, admin lacks archive
permission, analytics only counts open tickets, escalation doesn't
exclude archived. Same four bugs as F2 and F8. Same root cause:
private cognition.

## What I learned

The bugs are boringly predictable. That's the point — they're
structural, not stochastic. An agent that doesn't know `archived`
exists will hardcode `("closed", "resolved")` or `{"open"}` or omit
the archive action. Every time, every run.

The git analytics agent defined `_ACTIVE_STATUSES = {"open"}`. Not
wrong — open IS an active status. But it missed three others because
it had to guess from domain intuition. The CNF agent imported
`ACTIVE_STATUSES` from the workflow module because the structural
context told it those entities exist.

Repair is expensive. Not because the fixes are hard (they're local,
targeted), but because each round costs a full LLM inference cycle
(45-50s). At 6 agents and 4 bugs, one round suffices. At 20 agents,
the repair loop becomes the bottleneck.

## Honest limitations

Two runs is not a large sample. The variance is real (1.5x to 2.6x)
because LLM inference time fluctuates. More runs would tighten the
confidence interval.

The information gap is designed, not discovered — we chose what agents
see. The claim is that the CNF graph would provide this context
naturally (as demonstrated in F3's live graph pipeline). F9 simulates
that with explicit structural context in the prompt.

The app is still moderate scale (6 features, 22 tests, ~200 LOC per
module). The thesis predicts the advantage compounds with scale. That
remains unproven at larger sizes.

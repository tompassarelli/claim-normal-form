# E25: Graph-Native Repair Loop — Results

**Date:** 2026-05-22

## Summary

Same E24b setup (3 agents, 15 tests, 8 info-gap). New condition:
`cnf_repair` — facade discovery + finish_check + obligation repair.

```
cnf_repair:   1/24 info-gap bugs (4%)    $0.142/run   1 repair round
cnf_facade:   9/24             (38%)    $0.156/run   0 rounds (E24b)
file_repair:  1/24              (4%)    $0.293/run   1 repair round (E24b)
file_first:  11/24             (46%)    —            0 rounds (E24b)
```

**finish_check structurally repaired the permissions problem.** The
permissions agent that never engaged with facade tools (0/6
imports_workflow in E24b) now imports from workflow in 3/3 runs after
obligation repair. The remaining failure (run 2) is behavioral: the
agent knew the lifecycle facts but implemented the gate incorrectly.

## cnf_repair — 3 runs

| Run | First pass | After repair | Repair rounds |
|-----|-----------|-------------|---------------|
| 1 | 2/8 | 0/8 | 1 |
| 2 | 1/8 | 1/8 | 1 |
| 3 | 2/8 | 0/8 | 1 |

### What finish_check found

**Permissions** (the E24b failure case): In 2/3 runs, finish_check
flagged 3 critical obligations:
1. No workflow import
2. Terminal statuses not handled
3. Permissions don't gate on lifecycle state

After repair, the agent added `from workflow import TERMINAL_STATUSES`
and gated `can_manage` on ticket lifecycle. In the third run,
permissions already passed (the agent happened to explore on its own).

**Analytics**: In all 3 runs, finish_check flagged 1 critical
obligation (terminal status handling). This was a false positive in
some cases — the code was already handling it but using names
finish_check didn't recognize. Repair still improved the code
(cleaner imports, more explicit handling).

**Notifications**: Passed finish_check in all 3 runs (already
importing TERMINAL_STATUSES and suppressing terminal transitions).

### The run 2 residual

Run 2 had 1/8 info-gap bugs after repair (test_06: no_manage_archived).
The permissions agent passed finish_check (it imported from workflow
and knew about archived) but implemented the lifecycle gate wrong at
runtime. finish_check is a structural check, not a behavioral test.
This is expected — behavioral correctness is the test suite's job.

### Per-agent quality (post-repair)

| Signal | notifications | analytics | permissions |
|--------|:---:|:---:|:---:|
| imports_workflow | 3/3 | 3/3 | 3/3 |
| uses_terminal_statuses | 3/3 | 3/3 | 2/3 |
| uses_is_active | 0/3 | 3/3 | 0/3 |
| mean turns | 5.3 | 4.7 | 4.3 |
| mean cost | $0.058 | $0.039 | $0.045 |

Every agent imports from workflow. This was 0/6 for permissions in
E24b.

## Cost comparison

| Condition | Final info-gap | Cost/run | Repair rounds |
|-----------|---------------|----------|---------------|
| cnf_repair | 4% (1/24) | $0.142 | 1 |
| file_repair | 4% (1/24) | $0.293 | 1 |
| cnf_facade | 38% (9/24) | $0.156 | 0 |
| file_first | 46% (11/24) | ~$0.200 | 0 |

cnf_repair matches file_repair correctness at roughly half the
observed cost.

Why cheaper: CNF agents generate code in fewer turns (facade tools vs
file browsing). finish_check is programmatic (zero LLM cost). Obligation
repair is targeted — specific imports and checks, not "debug these test
failures."

## What this means

### The obligation layer works

The thesis shift from E24b is confirmed:

> CNF is not enough as a passive knowledge surface. It becomes useful
> when the graph actively turns hidden dependencies into task obligations.

finish_check doesn't ask the agent to discover. It tells the agent
what it missed. The agent doesn't need to believe lifecycle is relevant
to permissions — the graph proves it is.

### Structural check, not behavioral test

finish_check catches missing imports, missing constant references,
missing lifecycle gates. It does NOT catch logic bugs (wrong
implementation despite correct imports). Run 2's residual failure
confirms this boundary.

This is the right boundary. finish_check is a structural linter backed
by the graph. The test suite is the behavioral verifier. Together they
cover different failure modes.

### The stack crystallizes

```
graph substrate (claims, Datalog)
  → semantic facade (discover_all, discover)
  → obligation discovery (finish_check)
  → repair loop (agent + obligations → fixed code)
```

Each layer catches what the previous one misses:
- Facade catches agents who explore
- Obligations catch agents who don't explore
- Repair turns obligations into correct code
- Tests verify behavior

## Raw data

`results-cnf_repair.json` in the experiment directory.

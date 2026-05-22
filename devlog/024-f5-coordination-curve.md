# 024 — F5: The coordination curve

Eight agents. Twenty-eight tests. Three tiers (3, 5, 8 agents).
The coordination curve experiment.

## What we measured

The question: does pass rate drop as agent count increases? If
CNF stays flat while git degrades, the thesis is confirmed —
shared semantic state makes parallel construction composable.

Same ClaimDesk CRM as F2-F4, but scaled to 8 feature modules:
permissions, audit, notifications, analytics, SLA, tags, teams,
escalation. Tests organized by tier — Tier A needs 3 agents
working together, Tier B needs 5, Tier C needs all 8.

Mid-run requirement: `on_hold` status injected after the base
code is distributed. This is the temporal divergence test from
F4, now at scale.

## The result

| | Git | CNF |
|--|--:|--:|
| Tier A (3 agents) | 8/10 | 10/10 |
| Tier B (5 agents) | 7/8 | 8/8 |
| Tier C (8 agents) | 10/10 | 10/10 |
| **Total** | **25/28** | **28/28** |

CNF: 100%. Git: 89%.

## What failed and why

All three git failures are temporal divergence:

1. `on_hold` not in `workflow.VALID_TRANSITIONS` — no agent saw
   the mid-run requirement
2. Can't transition to on_hold — consequence of (1)
3. SLA doesn't pause for on_hold — SLA agent has no concept of
   paused states

The escalation agent (Tier C) hardcoded `on_hold` in its
`_SKIP_STATUSES` and added it to `config.ACTIVE_STATUSES`. But
the workflow's state machine has no path to it. The merged system
is internally inconsistent — config says on_hold is active, but
the workflow can't reach it.

## What it means

The curve exists but it's not smooth. Git failures concentrate
where the mid-run requirement lands (Tier A), not uniformly across
tiers. The important observation: **all failures share one root
cause** — agents can't see changes that happened after they forked.

This is the same failure mode as F4 (temporal divergence), now
confirmed at 8-agent scale. The earlier experiments (F2/F3)
surfaced information-gap bugs (not knowing entities exist). F4/F5
surface temporal bugs (not seeing mid-run changes). Both are forms
of private cognition — the same enemy, different faces.

## The F2-F5 arc

Four experiments, increasing complexity:

| | Agents | Git pass | CNF pass |
|--|--:|--:|--:|
| F2 | 5 | 64% | 100% |
| F3 | 5 | 50% | 93% |
| F4 | 3 | 86% | 100% |
| F5 | 8 | 89% | 100% |

CNF holds at 100% (or 93% with one policy decision in F3) across
every experiment. Git failures are always structural — they follow
from the information architecture, not from prompt quality or agent
capability. The specific failure modes shift as experiment design
evolves, but they're always the same thing: cognition trapped in
isolated sessions.

## Honest limitations

The curve is not the clean monotonic drop we might want. Git
actually scores higher at Tier C (10/10) than Tier A (8/10)
because the on_hold tests happen to land in Tier A. A truly
smooth curve would require more tests per tier and more
independent mid-run requirements.

The SLA timing edge case (both conditions initially failed test_b06)
shows that agents make similar implementation choices regardless of
condition — the coordination substrate doesn't change individual
code quality, it changes system coherence.

The CNF pipeline is sequential, not parallel. True concurrent
construction with live graph synchronization is the BEAM target.
These experiments validate the information-sharing mechanism, not
the concurrency mechanism.

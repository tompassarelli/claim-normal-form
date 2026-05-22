# E33: Coordination curve on the graph-canonical substrate

## The question

> At what program size and agent count does graph-canonical multi-agent
> construction beat file+git multi-agent construction on wall-clock to
> a runnable, correct application?

This is the only question the user has said matters. E33 exists to
answer it.

## Why now

E27–E32 stood up and validated the graph-canonical substrate as a
correctness story (representation collapse, cross-entity obligations,
property-derived classification). All six experiments were single-agent
on a synthetic 4-module ClaimDesk. None measured wall-clock for
coordinating agents.

The coordination curve was last measured in F8/F9/F10 — but in the
**old** frame where Python files were the source of truth and CNF was a
sidecar parser. F8 showed CNF 2x faster at 5 agents; F10 confirmed with
real Sonnet agents at 6.

Nothing since E23 (2 concurrent agents) has tested coordination on the
graph-canonical substrate at 3+ agents. E33 fills that gap.

## What this is NOT

- Not "real app projection" (the prior NOW item). That asks "is the
  projected Python a real running service?" — orthogonal question.
- Not "strong textual baseline" (proposed last turn). That's still
  single-agent.
- Not another representation-collapse test. E32 already nailed that.

## Conditions

Two conditions, run in parallel where possible:

### file+git (control)
- N agents, each in its own git worktree from a shared base
- Coordinator merges in agent-completion order (or with a documented
  merge policy)
- Repair agent fixes integration failures after merge
- Wall-clock includes all of: agent inference, merging, repair rounds

### cnf-graph (treatment)
- N agents connected to a shared CNF daemon
- Agents edit claims via MCP tools (`claimdesk-mcp.rkt` shape, but
  for whatever the target app's domain is)
- Projection runs after each agent completes; final projection is
  the artifact under test
- No repair agent — graph-canonical is bet to one-pass correctness
  (per F8/F9/E32 pattern). If a repair round is needed, count it.

Both conditions: real Claude Sonnet agents (`claude -p --model sonnet
--tools ...`), same task spec, same acceptance test suite.

## Axes

### Agent count
- 3 (minimum interesting parallelism)
- 5 (matches F5/F8)
- 8 (matches F5, stress test)

### Program size
This is the open design question. Three rough scales:
- **small** (~25 entities, ~600 LOC, ClaimDesk-as-today)
- **medium** (~80 entities, ~2000 LOC, expanded helpdesk with
  accounts, billing, SLAs, integrations)
- **large** (~200 entities, ~5000 LOC, full app)

The user's `user_goal.md` says "real app." A synthetic benchmark at
scale-medium probably does not qualify. **This is what I need to
resolve with you before designing further.** See "Decisions needed."

## Metrics

Primary:
- **Wall-clock end-to-end** to passing acceptance tests, including
  any repair rounds in either condition

Secondary:
- Cost per run (token spend)
- First-pass test pass rate (without repair)
- Info-gap bugs (the F2/F8/F9 metric — cross-cutting issues that come
  from agents not seeing each other's work)
- Number of repair rounds required

## Decisions needed before running

1. **What is the target app?**
   - (a) Expand ClaimDesk into a 80-entity / 2000 LOC version
     (path of least resistance; risks "still a benchmark, not real")
   - (b) Pick a real reference app (e.g., a Rails-style blog clone,
     a real internal tool you'd use, an open-source helpdesk port)
   - (c) Define a real app you actually want and build it as the
     experiment

2. **How are claims for a "real app" structured?**
   The ClaimDesk graph models 6 status/role/permission/effect entity
   types. A real app needs models for: HTTP routes, request/response
   shapes, persistence, auth sessions, background jobs, configuration.
   Some of these have natural claim shapes (routes, schemas). Others
   may not (template rendering, side-effecting handlers).
   - Decide: which subset of "real app" lives in the graph?
   - Decide: what's projection vs what's hand-written scaffolding
     the agents don't touch?

3. **What does "correct" mean for the acceptance tests?**
   E32-style structural tests (does PRIORITIES exist as dict?) are
   weak. Real-app correctness means HTTP integration tests against
   a running server. That's a much heavier harness.

4. **What's the repair policy in the file condition?**
   F8/F9 used a coordinator + one repair agent. F11 used graph-aware
   tools with no repair. The fairest comparison is "both get equal
   repair budget" — but graph rarely needs it. Choose: equal time
   budget? Equal token budget? Unbounded until passing?

## Pre-experiment infrastructure

Likely needed before E33 can run:
- Multi-agent stress test of the daemon (8 simultaneous MCP
  connections, all writing claims, MVCC stays consistent). The
  cross-connection fix from E23b/c was for 2 connections; 8 is new.
- Projection target beyond synthetic Python modules. If the app is
  a Flask/FastAPI service, projection needs to emit routes, schemas,
  handlers, not just data dicts.
- Domain claim schema for the target app (depends on decision 2).

## Success looks like

A graph: wall-clock vs agent count, plotted for both conditions
across small/medium/large program sizes. The thesis is the lines
diverge as N grows — file+git plateaus or degrades, cnf-graph
stays near-linear.

If the curves don't diverge, the thesis is wrong (or this experiment
isn't sensitive enough to find it). Either outcome is the data we
needed.

## What I'm waiting on

Decisions 1–4 above, with #1 being the load-bearing one.

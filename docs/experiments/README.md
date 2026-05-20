# CNF Experiments

Empirical benchmarks for the CNF thesis: agents code faster against
a maintained semantic index than against text files.

## Experiments

| # | Type | Result | Key finding |
|---|------|--------|-------------|
| E1 | Scripted workflow | [results](e1-scripted/results.md) | CNF 1.4x faster post-load. Crossover ~35 ops. |
| E2 | Multi-operation | [results](e2-multi-op/results.md) | CNF wins at all scales (20 renames). 115-268x per-op. |
| E3 | Agent comparison | [results](e3-agent-comparison/results.md) | CNF wins N=100 (1.95x). Phase 4: 122-746x per-op. |
| E4 | Live session | [results](e4-live-session/results.md) | CNF wins total 3.26x. 307x sustained per-op. |
| E5 | Real agent arena | [results](e5-arena/results.md) | Text wins single task (8 vs 42 calls). CNF builds persistent rules. |
| E6 | Multi-round arena | [results](e6-multi-round/results.md) | Text wins total (12 vs 32). CNF wins tasks 2-5 (5 vs 7). |
| E7 | Interface proof | [results](e7-interface-proof/results.md) | **42 calls → 7.** Schema + batch + symbols = 6x reduction. |
| E8 | New interface arena | [results](e8-new-interface/results.md) | CNF 32→14 calls. Text also evolved: 12→3. Text wins 4.7x. |
| E9 | Evolving codebase | [results](e9-evolving-codebase/results.md) | 50 fn, 7 tasks. CNF 10 vs text ~6. Gap narrows to 1.7x. |
| E10 | Shared substrate | [results](e10-shared-substrate/results.md) | Cross-session persistence. CNF 6 vs text ~5. **Paradigm shift.** |
| E11 | Multi-agent | [results](e11-multi-agent/results.md) | Two agents, shared graph. Cross-agent rule composition. **Text can't do this.** |
| E12 | Real demo | [results](e12-real-demo/results.md) | 100 fns, full workflow: parse→rules→refactor→evolve. Incremental parse works. |
| E13 | Beagle bridge | [results](e13-beagle-bridge/results.md) | Real language (30+ form types). Parse→deps→rename→edit works end-to-end. |
| E14 | Python bridge | [results](e14-python-bridge/results.md) | Second language. Subprocess parse, same engine. Language-agnostic MCP. |
| E15 | Correctness eval | [results](e15-correctness/results.md) | **CNF correct on 5/5 tasks. Text search wrong on 5/5.** The payoff experiment. |
| E16 | Agent grounding | [results](e16-agent-grounding/results.md) | **CNF correct on 7/7 structural tasks. Text search wrong on 5, unprovable on 2.** |
| E17 | Agent-in-the-loop | [results](e17-agent-in-the-loop/results.md) | **CNF 30/30, text 26/30. Both pass all tests — difference is in API contracts.** |
| E18 | Real baseline | [results](e18-real-baseline/results.md) | **Rope ties CNF 30/30. Regex 26/30. Substrate properties: 5/5 (rope: N/A).** |
| E19 | Coordination cost | [results](e19-coordination/results.md) | **5 agents, 45 fns. Git rediscovery 56% (50 ops). CNF 0%. Git rename breaks downstream edit.** |
| F2 | Parallel construction | [results](f2-claimdesk/results.md) | **5 agents build CRM app. Git 9/14 integration tests (5 cross-cutting bugs). CNF 14/14. Confirmed with real Claude Code agents.** |
| F3 | Live graph | [results](f3-live-graph/results.md) | **Sequential agents, accumulated graph. Git 7/14 (5 cross-cutting bugs). CNF 13/14 (0 cross-cutting bugs, 1 policy decision). Live graph pipeline validated.** |

## The arc

E1-E4 optimized the engine: 0.04x to 3.26x. Per-operation, CNF is
100-1000x faster.

E5-E6 tested real agents: the engine speed doesn't matter because
**tool call count dominates wall time**. Each MCP round-trip costs
seconds of LLM inference.

E6 validated the compounding thesis — tasks 2-5 cost 5 calls (CNF)
vs 7 (text). But task 1's schema discovery (13 of 27 calls) kept
total high.

E7 proved the interface fix works: same task, 7 calls instead of 42.

E8 ran the real rematch: CNF dropped from 32 to 14 calls, but the
text agent also got smarter — from 12 to 3 calls by front-loading
all analysis into one Python script. Text wins when all questions are
known upfront.

E9 scaled to 50 functions and 7 tasks with an agent-initiated rename.
CNF 10 calls vs text ~6. The 1.7x gap (down from 5.3x in E5) is
the closest yet. Marginal cost converges to ~1 call/task for both
approaches — the remaining gap is setup cost.

E10 changed the frame entirely. Two sessions, same codebase. The CNF
agent in Session 2 restored Session 1's claim graph (1 call) and
inherited 3 rules, queried matviews it didn't build, got auto-updated
results through a rename, and composed new rules on existing derived
relations. The text agent reimplemented everything from scratch — and
got answers wrong. At 1.2x, call count is noise. The differentiation
is qualitative: what the agent CAN DO, not how many calls it takes.

E11 pushed further: two agents on the same claim graph. Agent A
defines structural rules, Agent B inherits them and defines quality
rules that COMPOSE Agent A's derived relations. tx_log shows clean
agent attribution. This is structurally impossible for text agents —
there's no shared mutable substrate to inherit, compose on, or
attribute through.

E12-E13 proved real-world applicability: 100-function codebases with
incremental parse, real beagle syntax with 30+ form types.

E14 added the second language (Python) and proved the pattern is
language-agnostic. The claim graph engine is the same — only the
parser changes. MCP Resources shift the bottleneck from tool-call
round-trips to context injection.

E15 shifted the frame from speed to correctness: 5 structural tasks
where CNF gets right answers and text search gets wrong answers.
Entity resolution, transitive closure, and shadowed-name disambiguation
are qualitatively different from string matching — not faster, correct.

E16 scaled this to 10 tasks on a 45-function codebase with hidden
ground truth. CNF correct on 7/7 structural tasks, text search wrong
on 5, unprovable on 2. Cross-session memory (task 10) scores 10/10
for CNF and 0/10 for text — structurally impossible without a
persistent semantic substrate.

E17 closed the loop: both agents make actual code changes and run
the test suite. Both pass all 26 tests on every task. The difference
only appears in hidden tests checking API contracts: CNF 30/30 (100%),
text 26/30 (87%). The text agent renames dict keys alongside function
calls and misses dead code whose names appear as dict keys. CI can't
catch this — the failure is in downstream contracts the tests don't
cover.

E18 answered the obvious rebuttal: regex is a strawman. Python's
`rope` library does scope-aware rename and reference-counting — a
real semantic tool. Result: rope ties CNF at 30/30 on all four tasks.
The E17 advantage over regex was real but not unique. However, Part B
tested substrate properties: cross-session rename propagation, Datalog
rule persistence, cross-agent composition. 5/5 pass for CNF. Rope
gets N/A by construction — no persistent state, no rule engine, no
cross-session memory. The honest positioning: CNF doesn't beat rope
at Python refactoring. It provides a persistent semantic substrate
that survives sessions, spans languages, and lets agents compose
derived knowledge.

E19 shifted the frame entirely. The question is no longer "which tool
renames better?" but "how much do agents waste rediscovering what
prior agents already knew?" Five agents, 45-function codebase, six
modules. Architect maps structure, Renamer renames, Janitor removes
dead code, Feature dev adds a parameter, Auditor verifies. In git,
every agent re-reads every file — 56% of all discovery is redundant
(50 operations wasted). In CNF, each agent restores one checkpoint
and inherits all prior agents' accumulated knowledge — 0% rediscovery.
Bonus finding: git's naive rename breaks Agent D's downstream edit
(tax exemption silently not applied). CNF distinguishes the function
entity from the parameter entity, so the edit succeeds. The graph is
shared working memory: program facts, derived relations, agent actions,
and composable rules all persist and compound across sessions.

F2 moved from maintenance tasks to construction. Five agents build a
CRM app: workflow state machine, permissions, audit, notifications,
analytics. The features cross-cut — notifications must suppress for
archived tickets, analytics must exclude them from active counts,
permissions must include the archive action. In the git condition,
each agent only sees the base code and builds its feature blind to
what others built. Result: 5 cross-cutting bugs, all from the same
root cause — agents don't know about each other's entities. In the
CNF condition, agents query the claim graph and discover archive_ticket,
is_archived, ACTIVE_STATUSES before writing code. Result: 0 bugs.
First confirmed with scripted agents, then replicated with real Claude
Code agents making genuine implementation decisions. The five failures
are identical in both runs — they're structural, not stochastic.

F3 validated the live graph pipeline. Instead of static context injected
into prompts, each agent's code is parsed into the CNF graph after it
finishes. The next agent queries the accumulated graph — 17 entities
growing to 34 as modules are added. Same cross-cutting result: 5
information-gap bugs in git, 0 in CNF. The CNF condition's single
failure is a policy decision (permissions agent found archive but gave
agents access — test expects admin-only), not an information gap. The
live graph mechanism works: parse → checkpoint → restore → query → parse
new code → re-checkpoint. This is the infrastructure for true concurrent
multi-agent construction.

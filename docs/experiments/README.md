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

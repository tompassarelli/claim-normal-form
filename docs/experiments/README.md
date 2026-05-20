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
Projected E6 with new interface: ~11 calls (CNF) vs 12 (text).
**CNF wins total for the first time.**

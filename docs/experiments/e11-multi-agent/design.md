# E11: Multi-Agent Concurrent Access

## Thesis under test

Multiple agents building complementary understanding on a shared claim
graph produce richer results than any single agent — and text agents
have no equivalent, because there's no shared mutable substrate.

E10 proved cross-session persistence. E11 tests the next dimension:
**cross-agent collaboration within a session**.

## Setup

Same 50-function, 4-layer codebase (e9-program.txt). One daemon, two
agents connecting via TCP bridge.

**Agent A ("structural-analyst"):**
- `set_agent structural-analyst`
- Parse program
- Define trans-dep rule (transitive dependencies)
- Define shared-dep rule (pairs sharing 2+ direct deps)
- Checkpoint

**Agent B ("quality-checker"):**
- `set_agent quality-checker`
- `restore` (inherits Agent A's graph + rules)
- `list_rules` — inspect what Agent A built
- Define leaf-complexity rule: leaves with >2 params
- Define coupling rule: functions appearing in >3 shared-dep pairs
- Query: which functions are both high-complexity and high-coupling?

**Verification phase (either agent):**
- `tx_log` — shows interleaved Agent A and Agent B transactions
- `list_rules` — 5 rules total (2 structural + 1 shared-dep + 2 quality)
- Query composing Agent A's structural rules with Agent B's quality rules
- Rename a hub function → matviews from BOTH agents auto-update

## The asymmetry

**CNF agents:**
- Agent B inherits Agent A's rules and matviews (1 call: restore)
- Agent B defines quality rules that REFERENCE Agent A's derived
  relations (e.g., `coupling` body uses `shared-dep` from Agent A)
- After rename, both agents' matviews auto-update
- `tx_log` shows exactly who did what

**Text agents:**
- Agent B has no access to Agent A's analysis
- Agent B must re-derive all structural analysis before building on it
- No composition — each agent's scripts are independent
- No attribution — can't tell which agent produced which analysis
- Rename requires re-running BOTH agents' analyses from scratch

## What E11 does NOT test

- **True concurrency.** Agents run sequentially via checkpoint/restore,
  not simultaneously on the daemon. The semaphore serializes access.
  Real parallelism requires MVCC (LATER on roadmap).
- **Conflicting mutations.** Both agents add to the graph; neither
  contradicts the other. Conflict resolution is out of scope.
- **Scale.** Still 50 functions.

## Honest prediction

**Call count:** CNF ~12, text ~8. Agent B's restore + rule definitions
cost calls that text doesn't pay. But Agent B's rules COMPOSE Agent A's
derived relations — text agent B would need to reimplemented A's analysis
first, which could push text to ~10+ calls.

**The real finding:** The tx_log showing "Agent A defined trans-dep at
seq 5, Agent B defined coupling at seq 8, composing Agent A's shared-dep"
is something text cannot produce. The claim graph is an audit trail of
collaborative structural reasoning.

## Expected answers

- Trans-dep of normalize: 16 functions (from E9/E10)
- Shared-dep pairs: 6 pairs with 2+ shared deps
- Leaf complexity: functions with 0 callees and >2 params
- Coupling: functions appearing in >3 shared-dep triples
- Composition query: intersection of high-complexity and high-coupling
- After rename: all matviews auto-update (structural + quality)

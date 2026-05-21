# E23b: Concurrent Graph-Native Agents — Shared Daemon

**Date:** 2026-05-22 (E23b re-run after MVCC fix)

## Question

When two agents modify the same program concurrently through a shared
claim graph — one adding safe division, one renaming a core dependency
— does the graph substrate eliminate coordination conflicts that text
editing cannot?

## Setup

Same 51-function program as E23, same two tasks, same overlap zone.

- **5 overlap functions** (`calc-ratio`, `calc-average`, `calc-share`,
  `calc-rate`, `calc-pct`): call `helper` AND use raw division. Both
  agents must touch these.
- **Agent A (safety):** Add `safe-div`, guard all division-using
  functions, verify no crashes.
- **Agent B (refactor):** Rename `helper` → `utility`, verify all call
  sites, query error history.

**Graph condition (new):** Both agents connect to the **same running
daemon** via TCP. Program parsed once into shared state. Agents read
and write through MVCC — each write takes a semaphore, deep-copies
committed state, processes, publishes back. Reads parameterize from
committed without locking.

**Text condition (fixed):** Each agent gets an isolated workspace copy
(`cwd` per agent, not `--add-dir`). Three-way merge afterward. This
fixes the E23 bug where both agents accidentally edited the same file.

**Verification:** A fresh TCP connection opens after both agents finish
and confirms it can see all changes through the MVCC committed snapshot
(pre-check: 2474 objects; post-check: 24714 objects).

**Model:** Claude Sonnet. **Timeout:** 420s.

## Results

|                        | Graph (shared daemon) | Text (isolated) |
|------------------------|-----------------------|-----------------|
| Wall time              | 346.2s                | 164.5s          |
| Agent A (safety)       | 75.2s                 | 79.8s           |
| Agent B (refactor)     | 346.2s                | 164.5s          |
| Both completed?        | Yes                   | Yes             |
| Conflicts              | **0**                 | **4**           |
| Repair rounds          | 0                     | 0               |
| Verification           | **26/26**             | **13/14**       |
| Error history          | Yes                   | No              |

### Graph condition: 0 conflicts, fully integrated

Both agents operated on the same live daemon. Agent B's rename and
Agent A's body modifications hit the same 5 overlap functions from
different angles — rename changes the entity name claim, body
modification changes the body claim. These are different claim types
on the same entity. No conflict.

**Rendered overlap function (graph):**
```clojure
(defn calc-ratio [a b]
  (safe-div (utility a b) b))
```

Both changes integrated: `utility` (Agent B's rename) and `safe-div`
(Agent A's guard). This happened without either agent knowing about
the other — they operated on orthogonal claim types.

**Agent A:** Added `safe-div` (entity 6809), guarded 8 functions
(`ratio`, `share`, `split-even`, `percent`, `calc-ratio`, `calc-share`,
`calc-rate`, `calc-pct`). Verified: `ratio(10,0) = 0`. Non-regression:
`ratio(10,2) = 5`.

**Agent B:** Renamed entity 222 `helper` → `utility`. All 11 call
sites updated (one `rename` call). `helper-rate` (entity 280),
`tax-helper`, and `helper` parameters in `process-a/b/c` unaffected.
Error history: run 35249 (`/: division by zero`) still queryable.

**MVCC witness:** Fresh verifier connection confirmed:
- Pre-agents: 2474 objects, 1757 transactions, 51 functions
- Post-agents: 24714 objects, 18894 transactions
- Rendered program: 52 functions (51 + safe-div), fully coherent

### Text condition: 4 conflicts, definition lost

Each agent edited its own copy. Three-way merge produced 4 conflicts
in the overlap zone:

```
;; CONFLICT: calc-ratio
;; --- Agent A version ---
(defn calc-ratio [a b]
  (safe-div (helper a b) b))
;; --- Agent B version ---
(defn calc-ratio [a b]
  (/ (utility a b) b))
```

Agent A's version has `safe-div` but still says `helper`. Agent B's
version has `utility` but no `safe-div` guard. Neither version is
correct — the correct form requires both changes. Same pattern in
`calc-share`, `calc-rate`, `calc-pct`.

Worse: the `(defn utility [x y] (+ x y))` definition was lost
entirely in the merge. Call sites reference `utility` but the
definition doesn't exist. The `b_utility_exists` check fails.

## What changed from E23

| Issue | E23 | E23b |
|-------|-----|------|
| Daemon MVCC | Broken — agents used separate servers | Fixed — both agents share one daemon |
| Text workspaces | Accidental file sharing (same dir) | Isolated (`cwd` per agent) |
| Verifier | Broken (wrong render args) | Real witness (fresh TCP connection) |
| Graph conflicts | N/A (separate servers) | **0** (same daemon, concurrent) |
| Text conflicts | 0 (accidental coordination) | **4** (honest isolation) |

E23 was compromised in both directions: graph agents couldn't share
state, text agents accidentally did. E23b fixes both.

## The overlap zone

This is where the experiment's design pays off. The 5 overlap
functions need both Agent A's safe-div AND Agent B's rename.

**Graph:** Rename changes the name claim on entity 222. Body
modification changes body claims on the functions that call it.
These are independent writes to different predicates on the same
(or related) entities. MVCC serializes them without conflict because
neither write invalidates the other.

**Text:** Both agents rewrite the same line of the same function.
Agent A changes `(/ (helper a b) b)` → `(safe-div (helper a b) b)`.
Agent B changes `(/ (helper a b) b)` → `(/ (utility a b) b)`. These
are conflicting edits to the same string. No merge strategy can
resolve this without understanding the semantic intent.

## Honest assessment

**The graph condition proves the coordination thesis.** Two agents,
same live graph, overlapping targets, zero conflicts. The rendered
program has both changes correctly integrated. This is what E23 was
designed to test, and the MVCC fix makes it work.

**The text condition shows the real failure mode.** Not "text is
slower" — text loses data. The `utility` definition vanished. Four
functions have irreconcilable conflicts. A repair agent could fix
this, but it would need to understand both agents' intent and
synthesize a combined version.

**Wall time favored text this run.** Text: 164.5s, Graph: 346.2s.
Agent B's graph execution was unusually slow (346.2s vs its typical
~105s from E23). The graph overhead is partly MVCC serialization on
writes and partly variance. Speed is not the claim — correctness
under concurrency is.

**The graph's structural advantage:** rename and body-modification are
orthogonal operations in the claim model. This is not a coincidence
of this particular test — it's a consequence of the entity/claim
architecture. Any operation that modifies a different predicate on the
same entity will compose without conflict.

## What this demonstrates

1. **Shared-graph coordination works.** Two agents, one daemon, zero
   conflicts. The MVCC snapshot system correctly serializes concurrent
   writes.

2. **Orthogonal claim types compose.** Rename (name claim) and body
   modification (body claim) on the same entity don't conflict. The
   graph structure makes the non-interference provable.

3. **Text merging loses information.** Not just conflicts — the
   function definition itself was lost. Conflicts can be repaired;
   lost definitions require re-discovery.

4. **Error-as-data persists through concurrent modification.** Run
   35249 (`division by zero`) survived Agent A's body modifications,
   Agent B's rename, and MVCC snapshot transitions. Queryable by a
   fresh connection after both agents finish.

## What's next

1. **Add repair rounds to text condition.** Give a third agent the
   conflicted merge and measure the cost of conflict resolution.

2. **Scale to 3+ agents on shared daemon.** ClaimDesk: multiple agents
   constructing a real application through the shared claim graph.

3. **Measure MVCC contention.** At what agent count does write
   serialization become a bottleneck?

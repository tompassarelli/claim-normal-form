# 040 — E20–E23c Synthesis: From Graph Runtime to Concurrent Composition

**Date:** 2026-05-22

## The arc completes

037 ended with a question: when two agents modify the same
claim-graph program concurrently, does the shared substrate reduce
coordination failures?

E23b/c answered it. Yes. And the mechanism is specific.

## The progression

**E20** proved the agent loop works. Parse, evaluate, query, rename,
break, diagnose, fix — all against one claim graph. Scripted, not
agent-driven.

**E21** put it in agents' hands. Text was faster (64.7s vs 103.6s) at
5 functions. The graph's structural advantages didn't manifest at toy
scale.

**E22** found the crossover. At 58 functions with name-ambiguity
traps, graph was faster for the first time (138.2s vs 157.3s). Both
scored perfectly, but graph rename was one operation while text
required careful multi-step analysis. O(1) vs O(N).

**E23** attempted concurrent agents but was compromised both ways:
graph agents couldn't share state (MVCC bug), text agents
accidentally shared a file.

**E23b** fixed both. Two agents on the same daemon, zero conflicts.
Text agents in isolated workspaces, four conflicts.

**E23c** fixed `resolve_symbol` (function/parameter disambiguation)
and confirmed Agent B's slowness was model variance, not a code bug.

## The result that matters

Graph rendered overlap function:
```clojure
(defn calc-ratio [a b]
  (safe-div (utility a b) b))
```

Text merged overlap function:
```
;; CONFLICT: calc-ratio
;; --- Agent A version ---
(defn calc-ratio [a b]
  (safe-div (helper a b) b))
;; --- Agent B version ---
(defn calc-ratio [a b]
  (/ (utility a b) b))
```

Agent A added safety. Agent B renamed the dependency. In the graph,
these are different predicates on the same entity — they compose. In
text, both edits target the same line — they conflict.

## Why this is architectural, not accidental

In the claim model:
- **Rename** changes the name claim on entity 222
- **Body modification** changes body claims on functions that call it
- These are independent writes to different predicates

No amount of clever merging can fix the text problem. The merge
algorithm has one line and two different versions. It cannot know
that both changes are needed because the semantic intent was
collapsed into string edits.

The graph never had this problem because the operations were never
entangled. Rename and body-modification are structurally independent.

## The speed story, honestly

```
                    Graph      Text        Text+repair
E21 (5 fn):        103.6s     64.7s       —
E22 (58 fn):       138.2s     157.3s      —
E23b (51 fn):      346.2s     164.5s      213.4s
E23c (51 fn):      327.9s     195.1s      285.7s
```

Speed bounces with model variance. Agent B's graph time ranges from
105s to 346s across runs. The structural result does not bounce:
graph always produces 0 conflicts, text always produces 4.

## Three capability gaps, now proven

1. **Correct-by-construction operations.** Rename cannot produce
   false positives (E22). Body modification cannot hit the wrong
   function. These are properties of the substrate, not of the
   agent's reasoning.

2. **Error-as-data.** Runtime failures persist as queryable entities.
   Run 35249 (division by zero) survives Agent A's body modifications,
   Agent B's rename, MVCC snapshot transitions, and is queryable by a
   fresh TCP connection after both agents finish. Text has no
   mechanism for this.

3. **Concurrent composition.** Orthogonal claim types compose under
   shared graph state. Two agents, one daemon, overlapping targets,
   zero conflicts. Text agents produce locally correct work that
   fails to merge. Repair works (48.9–90.6s) but scales with conflict
   complexity.

## The bugs that shaped the design

**MVCC cross-connection snapshot (E23 → E23b):** Non-tool messages
clobbered the committed snapshot. Fix: 3-branch cond separating
read-only tools, write tools, and non-tool messages. Proved the
daemon architecture was right but the implementation missed an edge.

**resolve_symbol ambiguity (E22 → E23c):** Parameter entities
shadowed function entities at scale. Fix: `prefer-non-param` filters
by position claims. This disambiguation is itself a structural
operation — it requires entity-level identity.

Both bugs surfaced only under conditions previous experiments
couldn't create: MVCC needed multiple connections, resolve_symbol
needed name collisions at scale. The experiments drove the
implementation forward.

## What this means for ClaimDesk

The mechanism is proven: semantic operations compose under shared
graph state. The question now is whether it survives realistic work
— multiple agents constructing a real application, not a toy
51-function program.

The infrastructure is ready: shared daemon with MVCC, agent identity
on transactions, MVCC-witnessed verification. What's needed is a
task that exercises it: 3+ agents building complementary modules on
a shared claim graph, with overlapping concerns that force the
composition mechanism to work.

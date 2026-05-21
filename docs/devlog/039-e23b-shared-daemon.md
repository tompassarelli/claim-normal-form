# 039 — E23b: Shared daemon proves the coordination thesis

**Date:** 2026-05-22

## What

Fixed the MVCC cross-connection snapshot bug, re-ran E23 with both
agents on the same daemon. Graph: 0 conflicts, 26/26 verification.
Text: 4 conflicts, definition lost in merge.

## The MVCC fix

The daemon's message handler had two branches: tool calls (write path)
and everything else. Non-tool messages (initialize, ping,
notifications/initialized) fell into the else branch which clobbered
the committed snapshot with a stale thread-local copy. New connections
started from pre-parse state.

Fixed with a 3-branch cond: read-only tools parameterize from
committed. Write tools take semaphore, deep-copy, process, publish
back. Non-tool messages parameterize from committed without updating.

## The result that matters

Graph rendered overlap function:
```clojure
(defn calc-ratio [a b]
  (safe-div (utility a b) b))
```

Both changes integrated: `utility` from Agent B's rename, `safe-div`
from Agent A's guard. Neither agent knew about the other. They
operated on orthogonal claim types (name vs body) on the same entity.

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

Neither version is correct. Agent A has `safe-div` but missed the
rename. Agent B has `utility` but missed the guard. And the `utility`
definition itself was lost in the merge.

## What went wrong with E23

E23 was compromised both ways. Graph agents used separate servers
(MVCC bug). Text agents accidentally edited the same file (`--add-dir`
bug gave them the experiment directory, not their workspace). E23
showed 0 conflicts for both — but neither measurement was honest.

## What I learned

The graph's advantage isn't speed — text was faster this run (164s vs
346s). It's that rename and body-modification are different operations
in the claim model. They can't conflict because they modify different
predicates. This isn't a property of this test — it's a structural
consequence of the entity/claim architecture.

Text editing collapses these distinct operations into "edit this line."
When two agents edit the same line for different semantic reasons, the
merge can't know that both changes are needed. The graph never has
this problem because the operations were never entangled.

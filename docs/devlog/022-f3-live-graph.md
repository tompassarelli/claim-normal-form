# F3: Live graph — accumulated context works

## What changed

F2 gave CNF agents static structural context — entity IDs and
dependency edges pre-computed and injected into prompts. It worked
(14/14 vs 9/14), but the context was hand-assembled. The agent
didn't query the graph; it received the answers.

F3 closes that gap. Each CNF agent's code is parsed into the live
graph via MCP server after it finishes. The next agent inherits
the accumulated graph — 17 entities growing to 34 as four modules
are added. The structural context isn't pre-computed; it emerges
from the pipeline.

## The pipeline

```
base + workflow.py → parse → graph (17 entities)
  → permissions agent → parse permissions.py → graph (20 entities)
    → audit agent → parse audit.py → graph (27 entities)
      → notifications agent → parse notifications.py → graph (34 entities)
        → analytics agent (richest context)
```

The graph tracks dependency edges too: `require_permission →
has_permission`, `notify_transition → should_notify`, `audit_* →
log_action`. Each agent sees the full dependency web of all prior
work.

## Results

**Git: 7/14. CNF: 13/14.**

Same five cross-cutting bugs in git as F2 — all from the archived
state information gap. Two additional git failures: permissions agent
chose namespaced actions (`ticket:create` vs `create`), notification
agent added an audience check that suppressed test notifications.
These are convention/spec issues, not cross-cutting bugs.

CNF's one failure: the permissions agent found `archive_ticket` in
the graph (cross-cutting discovery succeeded) but gave agents the
archive permission. Test expects admin-only. This is a policy
judgment made with full information — categorically different from
the git failure where the agent doesn't know archive exists at all.

## The distinction that matters

Git failure on archive permissions: "I didn't include archive
because I don't know it exists. I only saw core.py."

CNF failure on archive permissions: "I included archive because
I found entity 1566 (archive_ticket) in the graph. I classified it
as agent-accessible because it's a ticket operation."

Both fail the test. Only one is an information gap. The graph solved
the discovery problem; the agent made a different policy choice.

## What I learned

The live graph pipeline works as infrastructure. Parse → checkpoint →
restore → query → parse new code → re-checkpoint. Each step takes
under 30 seconds. The MCP server handles the full round-trip.

The cross-cutting result is invariant to the delivery mechanism.
Whether structural context arrives as static text (F2) or live query
results (F3), the pattern is the same: agents with shared state avoid
information-gap bugs, agents without produce them.

The value of the live pipeline isn't better correctness (F2 already
achieved that). It's automation: the graph accumulates as agents
work without a human pre-computing the context. This is the
infrastructure for concurrent multi-agent construction — the next
step is agents writing to the same files while the graph tracks
entity-level changes.

## What's next

The sequential pipeline proves the mechanism. Concurrent operation
needs conflict resolution: what happens when two agents modify the
same entity? The graph knows which entity changed (not just which
file). That's the substrate for merge-at-the-entity-level rather
than merge-at-the-line-level.

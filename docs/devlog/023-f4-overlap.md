# F4: Overlapping edits — the merge problem is structural

## What changed

F2 and F3 tested agents writing separate files. Every real project
has shared files — configuration, shared modules, constants. F4 makes
agents modify the same `config.py` and wire their hooks into the same
hook registration system.

## The three failures

Git: 18/21. CNF: 21/21. Three failures, three distinct failure modes:

**1. Temporal divergence.** All three failures are on_hold tests. The
mid-run requirement (on_hold status) was added after git agents
forked. They can't incorporate information that didn't exist when they
started. This is not a merge problem — no amount of conflict
resolution adds on_hold to agents that never saw it.

**2. Merge conflicts (averted by hand).** Three agents produced three
different config.py files. Same lines modified, different orderings,
different hook registrations. The test used a perfect manual merge.
In a real workflow, this would be a three-way merge conflict requiring
human intervention.

**3. Hidden dependency.** The audit agent registered post_transition
hooks. The base workflow.py doesn't fire post_transition. Only the
notification agent independently fixed this. Without that fix, audit
transition hooks are dead code. Neither agent knows about the other.

## CNF avoided all three

The sequential pipeline makes merge conflicts impossible — each agent
reads the current config.py and appends. The mid-run requirement is
just a workspace update between agents — the next agent sees on_hold
naturally. And the workflow hook calls are in place before the audit
agent runs.

## What I notice

The git agents did surprisingly well on the shared-state parts:
- All three independently discovered "archived" in TERMINAL_STATUSES
- All three added "archive" and "transition" to SYSTEM_ACTIONS
- All three wrote correct hook registrations

The git-only failures are ALL temporal — on_hold. The agents had the
right instincts but lacked the information. Same story as F2 and F3:
the failures are in the gaps between features, and the gaps come from
information asymmetry, not from agent incompetence.

## What this means for the thesis

The coordination curve argument: as you add more agents modifying the
same files, the merge conflict surface grows quadratically. Two agents
touching config.py is a two-way merge. Three is a three-way merge.
Five is... not fun.

CNF's sequential accumulation is O(N) — each agent reads current
state and extends it. No merge conflicts regardless of agent count.
The graph ensures every agent sees the complete current state
including mid-run changes.

The temporal divergence result is new. F2/F3 showed agents missing
*existing* information (workflow.py was always there, git agents just
didn't see it). F4 shows agents missing *new* information that arrived
after they forked. This is the real-world case: requirements change
during construction. Agents that started from a snapshot are frozen in
time. The live graph updates between agents.

# 027 — F7: The graph filters, it doesn't find

The bridge spike showed the graph CAN answer structural questions.
The agent experiment tests whether it HELPS.

## Setup

49 integration tests written from the feature spec alone (blind to
codebase structure). Reference implementation: 7 edit sites across
4 files. 14 of 18 modules auto-adapt via ACTIVE_STATUSES and
TERMINAL_STATUSES — no changes needed.

Three Claude Sonnet agents, each given the feature spec:
- Grep-only: 35 tool calls
- File-reader: 19 tool calls
- Graph-first: 11 tool calls

## The surprise

All three agents found the same 6 core edit sites. Same recall: 86%.
The 7th site (a pre-existing crash exposed by the new feature) was
invisible to all static analysis approaches.

I expected the graph agent to find sites the others missed. It didn't.
For this feature, the edit sites are shallow — named constants and
hardcoded comparisons, all directly visible to grep.

## The real advantage: precision

Where the graph differentiated: false positives.

- Grep: 11 false positives (35% precision)
- File-reader: 6 false positives (50% precision)
- Graph: 4 false positives (60% precision)

The grep agent saw 25 hits for ACTIVE_STATUSES across 8 files and
flagged most of them as needing changes. The graph agent started from
a structured categorization — "these 15 functions reference the
constant" — and correctly reasoned that all 15 auto-adapt.

The graph agent also produced a unique analytical category: "hardcoded
but correct." It correctly identified `tickets.delete_ticket`'s
`status = "closed"` as intentional soft-delete behavior, not a
terminal-status bug. Neither other agent made this distinction.

## What I learned

The graph's value isn't DISCOVERY — grep is a perfectly adequate
discovery tool. The graph's value is FILTERING: knowing which of
the many hits actually need attention.

At 18 modules, the difference is modest (11 false positives vs 4).
At 180 modules, the linear-scan approaches would scale proportionally
while the graph query stays constant. The precision advantage would
compound.

The universal false positive is illuminating: all three agents flagged
`validation.validate_comment` line 260 (hardcoded `== "closed"`) as
needing changes. It's technically wrong but functionally harmless —
the calling code already checks TERMINAL_STATUSES. The graph HAS the
call-graph data to surface this redundancy, but the analysis I
presented to the agent wasn't granular enough. Better queries would
expose it.

## Honest positioning

The graph doesn't help agents find more edit sites for shallow
features. It helps them SKIP more non-sites, work 3x faster, and
reason about the codebase structure rather than pattern-matching
on text.

The bigger value proposition — the one F2-F6 already proved — is
that the graph persists across sessions and agents. The efficiency
gain compounds: the impact zone query runs in one call, every time,
for every agent. Grep rediscovers the same information from scratch
each time.

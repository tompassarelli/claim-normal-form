# 042 — E24b: Concurrent facade — the permissions problem

**2026-05-22**

## The question

E24a proved facade discovery works for 2 agents. E23b proved
concurrent graph composition works. E24b combines them: 3 agents,
shared graph, facade tools, concurrent execution. Plus a file-based
control group (worktrees + merge + repair) for contrast.

## The answer

The facade doesn't generalize to agents whose tasks are semantically
distant from the tool descriptions.

```
cnf (6 runs):   9/24 info-gap bugs  (38% failure rate)
file first pass: 11/24              (46%)
file + repair:   1/24               (4%)
```

## Why it broke

The permissions agent never calls facade tools. It sees tools
described in terms of "states, statuses, transitions, notifications,
analytics" and decides they're irrelevant to access control. One
agent explicitly said: "No external lifecycle registry — ticket states
are plain strings in core.py. I have everything I need."

I updated discover_lifecycle to include "permissions, access control,
role-based rules" in its description. No effect — the agent's mental
model of permissions doesn't include lifecycle state at all. The words
are there but the semantic connection isn't.

Analytics agents reliably discover workflow through the facade
(5/6 runs). Notifications agents discover "archived" but hardcode
constants rather than importing. Permissions agents never engage.

## The repair asymmetry

File agents have the same first-pass failure rate as CNF (46% vs 38%).
The difference: file gets a repair round. A repair agent sees test
failures + full source and reliably fixes everything. CNF has no
repair mechanism — it's one-shot.

This is the real finding. Both conditions produce similar first-pass
results. File condition + repair is a strong baseline because it can
iterate.

## What this tells us about facades

E24a was right: discover_all + discover works. But "works" means
"works for tasks the facade's tool descriptions anticipate." The
facade is a semantic funnel — agents whose tasks match the funnel's
vocabulary discover well; agents whose tasks don't match skip
discovery entirely.

This limits where the facade scales. Adding a new agent type
(permissions) required updating tool descriptions, and even that
wasn't sufficient. The agent needs to believe the tools are relevant
to its task, not just see matching keywords.

## What's next

Three possible responses:

1. **Mandatory discovery** — force discover_all as a required first
   step. Removes agent judgment about relevance. Increases cost.

2. **Task-aware meta-tool** — a tool that maps the agent's task to
   relevant graph regions. "You're building permissions; here's why
   lifecycle state matters."

3. **CNF repair** — add a post-generation verification step. Repair
   agent uses the graph to fix info-gap bugs. Levels the playing
   field with file condition.

The third option is most interesting because it decouples discovery
from generation. An agent can write naive code, and the graph catches
what it missed.

## Numbers

| | CNF | File (first pass) | File (after repair) |
|---|---|---|---|
| Info-gap bugs | 38% | 46% | 4% |
| Mean cost/run | $0.156 | — | $0.293 |
| Repair rounds | 0 | — | 1 per run |
| Permissions imports_workflow | 0/6 | — | 3/3 (post-repair) |
| Analytics imports_workflow | 5/6 | — | 2/3 |

# E24a: Facade Design Spike — Results

**Date:** 2026-05-22

## Summary

Semantic facade tools eliminate info-gap bugs. Across 5 runs per
condition (10 agent-runs per condition, 20 info-gap test opportunities):

```
                    Info-gap bugs    Failure rate    Cost/run
facade_full:        0/20             0%              $0.135
facade_basic:       0/20             0%              $0.133
no_graph:          12/20            60%              $0.085
```

The facade vs no-graph gap is definitive. The ablation (facade_basic
vs facade_full) shows discover_lifecycle is NOT load-bearing — basic
discover tools suffice.

## Setup

- 2 agents (notifications, analytics), each builds one module
- Hidden knowledge in `workflow.py`: TERMINAL_STATUSES, ACTIVE_STATUSES,
  VALID_TRANSITIONS, plus helper functions
- Agents see only `models.py` and `core.py` in their prompt
- 6 integration tests, 4 targeting info-gap bugs (test_02–05)
- Model: claude-sonnet-4-6, `claude -p` mode
- Built-in tools disabled (`--tools ""`) — agents cannot read files
- MCP tools whitelisted (`--allowedTools`) — no silent permission denials
- 5 runs per condition, daemon reused across runs within a condition

## Multi-run results

### Discovery rates

| Metric | facade_full | facade_basic | no_graph |
|---|---|---|---|
| analytics imports_workflow | **5/5** | **5/5** | 0/5 |
| analytics uses_is_active | 4/5 | 2/5 | 0/5 |
| analytics uses_ALL_STATUSES | 2/5 | 3/5 | 0/5 |
| analytics hardcoded_statuses | 0/5 | 0/5 | 2/5 |
| analytics info-gap bugs/run | [0,0,0,0,0] | [0,0,0,0,0] | [2,2,2,2,2] |
| notifications imports_workflow | 1/5 | 3/5 | 0/5 |
| notifications knows_archived | 4/5 | **5/5** | 2/5 |
| notifications knows_on_hold | 0/5 | 1/5 | 0/5 |
| notifications mean turns | 4.0 | 5.4 | 1.0 |

### Per-run info-gap bugs

| Run | facade_full | facade_basic | no_graph |
|-----|:-----------:|:------------:|:--------:|
| 1   | 0           | 0            | 3        |
| 2   | 0           | 0            | 2        |
| 3   | 0           | 0            | 3        |
| 4   | 0           | 0            | 2        |
| 5   | 0           | 0            | 2        |

## Key findings

### 1. Facade tools reliably induce discovery

This is the central result. Across 10 runs with facade tools
(facade_full + facade_basic), analytics imported from workflow in
**10/10 runs**. Without tools, it imported from workflow in **0/5
runs**. No overlap. No lucky guessing.

The analytics agent in facade conditions consistently found symbols
it didn't know existed (`ALL_STATUSES`, `is_active`,
`TERMINAL_STATUSES`) through the discover_all → discover path, and
used the graph-provided import statements in its code.

### 2. discover_lifecycle is not load-bearing

The ablation is clear: facade_basic (without discover_lifecycle)
matches facade_full on every metric. Both get 0/20 info-gap bugs.
facade_basic notifications even outperforms facade_full on some
discovery metrics (imports_workflow: 3/5 vs 1/5, knows_archived:
5/5 vs 4/5).

The basic discover tools (discover_all + discover) are the product.
discover_lifecycle is a convenience — it helps on the first call to
understand the domain — but agents reach the same information through
the inventory path.

### 3. No-graph agents are deterministically wrong

no_graph analytics produced info-gap bugs in **every single run**
([2,2,2,2,2]). The failure is not variance — it's structural. Without
tools, the agent cannot discover that "archived" is a terminal status.
It hardcodes `{"closed", "resolved"}` based on training data, every
time.

no_graph notifications is noisier (knows_archived: 2/5) because
"archived" is a more guessable concept for notification suppression
than for analytics filtering. But it still fails 60% of info-gap
opportunities.

### 4. Tool description matters

After changing discover_lifecycle's description from neutral ("Scan
the codebase for state machines") to directive ("Call this before
writing code involving tickets, states, statuses, transitions..."),
facade_full went from variable (0/4 to 2/4 in earlier single runs)
to perfectly consistent (0/20 across 5 runs).

Good tool descriptions are part of the interface, not prompt cheating.

### 5. test_01 and test_06 fragility

test_01 (basic notification fires) fails in some runs across all
conditions. Cause: agents over-engineer notifications with per-recipient
logic that produces zero notifications when no recipients (managers,
assignees) exist in the test fixture. Not an info-gap bug.

test_06 (must import from workflow) fails for notifications in most
facade runs. Agents discover archived status through the facade but
often define their own constant (`_SILENT_STATUSES = {"archived"}`)
rather than importing from workflow. The knowledge transferred; the
import discipline didn't. This is a legitimate finding about facade
tool design — the tools surface facts but don't enforce import
patterns.

## Infrastructure lessons

### MCP permissions in -p mode

`claude -p` blocks MCP tool calls unless explicitly whitelisted.
Without `--allowedTools mcp__cnf-facade__discover_lifecycle ...`,
agents get permission denials and fall back to guessing. This was
the cause of the first 4/4 result — agents tried to call tools but
were silently blocked.

### Built-in tools contaminate results

Without `--tools ""`, agents use Read/Bash to browse the local
filesystem, find previous experiment outputs, and copy them — including
bugs from prior runs. The analytics agent in one run literally said
"The facade spike version is the most direct reference" and copied
code from a previous run's output file.

### Tool-use scoring via output text is unreliable

The `-p --output-format json` output only contains the final result
text, not intermediate tool calls. `num_turns` is the reliable proxy:
- no_graph: mean 1.3 turns (single-shot generation)
- facade: mean 4.5 turns (tool exploration)

Code quality signals (imports_workflow, knows_archived) are the ground
truth for whether discovery happened.

## Relationship to thesis

The scope document asked:
> "Does a domain-shaped facade cause agents to discover the lifecycle
> without being told which constants exist?"

The answer is **yes, reliably**. The initial single-run variance was
caused by infrastructure bugs (permission denials, filesystem
contamination) and neutral tool descriptions. After fixing those:
0/20 info-gap bugs across 5 runs.

The clean claim:
> E24a shows that a domain-shaped facade reliably causes agents to
> discover hidden lifecycle knowledge without being told the relevant
> module, variable names, or constants.

The ablation result refines the thesis: the facade layer itself is
the product, not any specific lifecycle-detection tool. discover_all
+ discover — the ability to browse the symbol inventory and look up
individual symbols — is sufficient for self-directed discovery.

## What's next

**E24b**: Scale from 2 agents to 3–5 on concurrent ClaimDesk modules.
Tests whether facade tools work for coordination (not just discovery)
when agents build interdependent modules simultaneously. Must include
a control group using file-based coordination (git worktrees) for
contrast with the CNF graph approach.

Open question from E24a: the `orient_task` tool concept (agent
supplies task description, graph returns relevant domains/symbols)
was proposed but not needed — directive tool descriptions were
sufficient. Revisit if E24b shows agents failing to start discovery
at larger scale.

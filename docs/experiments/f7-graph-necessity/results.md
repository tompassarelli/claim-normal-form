# F7: Graph Necessity

## Question

F2–F6 proved shared accumulated state eliminates coordination bugs.
But the "shared state" in those experiments was filesystem accumulation
— sequential file writes, not graph queries. **Does the semantic graph
itself provide value beyond reading files?**

## Design

Three phases:

1. **Bridge validation spike** — parse realistic codebase through CNF
   Python bridge, verify graph answers structural questions. GREEN.

2. **Test oracle + reference implementation** — 49 integration tests
   from feature spec (blind to codebase structure). Reference
   implementation: 7 edit sites across 4 files. Oracle verified:
   49/49 pass against reference, 31/49 fail against original.

3. **Three-condition agent experiment** — grep-only, file-reading,
   graph-first agents identify edit sites for the same feature.
   Scored against hidden ground truth.

## Codebase

18 Python modules, 4947 LOC, 238 functions, 11 classes.
Helpdesk/CRM app with status lifecycle, transitions, SLA, search,
reports, notifications, assignment, validation, comments, import/export.

Feature requirement: add `archived` (terminal) and `on_hold` (active)
statuses with specified transitions and behavioral semantics.

## Ground truth

7 edit sites across 4 files:

| # | File | Location | Change |
|---|------|----------|--------|
| 1 | config.py | STATUSES | Add "archived", "on_hold" |
| 2 | config.py | ACTIVE_STATUSES | Add "on_hold" |
| 3 | config.py | TERMINAL_STATUSES | Add "archived" |
| 4 | config.py | STATUS_TRANSITIONS | Add on_hold/archived entries |
| 5 | workflow.py | VALID_TRANSITIONS | Add on_hold/archived entries |
| 6 | models.py | Ticket.is_terminal | Property + include "archived" |
| 7 | validation.py | validate_assignment | Early return (pre-existing crash) |

14 of 18 modules need NO changes — they reference `ACTIVE_STATUSES`
and `TERMINAL_STATUSES` dynamically and auto-adapt when the constants
change.

## Bridge spike results

After parsing all 18 files:
- **356 entities**, 23,545 claims
- **310 fn→fn edges**, 143 fn→var edges

| Constant | Graph refs | Grep hits | Match |
|----------|-----------|-----------|-------|
| TERMINAL_STATUSES | 8 | 16 | 8/8 exact |
| ACTIVE_STATUSES | 15 | 25 | 15/15 exact |
| STATUS_TRANSITIONS | 1 | 2 | 1/1 exact |
| VALID_TRANSITIONS | 2 | 3 | 2/2 exact |

Impact zone: **36 functions across 12 modules** in one query.

## Three-condition results

Three Claude Sonnet agents, each given the feature spec and codebase.
Different information access per condition.

### Condition details

**Grep agent**: Only grep/ripgrep, no file reads. 35 tool calls.
**File-reader**: Full file reads, no search tools. 19 tool calls.
**Graph-first**: Pre-computed graph analysis + targeted reads. 11 tool calls.

### Scoring

| Metric | Grep | File-reader | Graph-first |
|--------|------|-------------|-------------|
| **Recall** | 6/7 (86%) | 6/7 (86%) | 6/7 (86%) |
| **Precision** | 6/17 (35%) | 6/12 (50%) | 6/10 (60%) |
| **Tool calls** | 35 | 19 | 11 |
| **False positives** | 11 | 6 | 4 |
| **Files correctly skipped** | 7 | 10 | 12 |

### What each agent found

All three correctly identified sites 1–6 (config constants, workflow
transitions, models.is_terminal). All three missed site 7 (validation
crash bug — only discoverable by running the code).

### False positive analysis

All three agents flagged `validation.validate_comment` line 260
(`ticket.status == "closed"`) as needing changes. This is a false
positive: `comments.add_comment` already checks `TERMINAL_STATUSES`,
so the hardcoded check in `validate_comment` is redundant but harmless.

| False positive | Grep | File | Graph |
|----------------|------|------|-------|
| validation.validate_comment line 260 | ✓ | ✓ | ✓ |
| config.HOOKS (add archive slot) | ✓ | | |
| models.is_open (add on_hold) | ✓ | ✓ | |
| workflow.transition_ticket (event) | ✓ | ✓ | ✓ |
| workflow.reopen_ticket | ✓ | ✓ | ✓ |
| workflow.docstring | ✓ | | |
| tickets.update_ticket (event) | ✓ | ✓ | ✓ |
| events.KNOWN_EVENTS | ✓ | | |
| audit.py (new handler) | ✓ | | |
| assignment.get_workload (key) | ✓ | ✓ | |

Grep generated 2.8x as many false positives as the graph (11 vs 4).
The graph agent produced a unique "hardcoded but correct" category,
correctly identifying `tickets.delete_ticket` (`status = "closed"`)
as intentional soft-delete behavior.

## Analysis

### Same recall — the sites are shallow

All three conditions found the same 6 core edit sites. The constants
(STATUSES, ACTIVE_STATUSES, TERMINAL_STATUSES, STATUS_TRANSITIONS)
are obvious targets for any approach. The duplicate transition table
in workflow.py is found by following imports or grepping. The hardcoded
`is_terminal` method in models.py is found by grepping `"closed"` or
reading the class definition.

The 7th site (validation.validate_assignment crash) is a latent bug
exposed by the new feature. No static analysis approach — grep, file
reading, or graph — can find it. It requires running the code and
hitting the crash path. All agents would discover it in the
test-driven repair loop.

### Precision differentiates — the graph filters noise

The graph's key advantage is **not finding more** but **filtering better**.
ACTIVE_STATUSES appears in 25 grep hits across 8 files; the graph
immediately shows which 15 functions reference it in executable code,
and the agent can reason that all of them auto-adapt.

The grep agent, seeing 25 hits, flagged 11 false positives — files
that look like they need changes but don't. The graph agent, starting
from a structured categorization of "references constant" vs. "hardcodes
value," flagged only 4 false positives.

### Efficiency scales with codebase size

| Condition | Tool calls | Ratio to grep |
|-----------|-----------|---------------|
| Grep | 35 | 1.0x |
| File-reader | 19 | 1.8x faster |
| Graph-first | 11 | 3.2x faster |

At 18 modules, the absolute difference is small (24 tool calls).
At 180 modules, the linear-scan approaches (grep, file-reading)
would scale proportionally, while the graph query count stays constant
— the impact zone query produces the same structured result regardless
of codebase size.

### The universal false positive

All three agents flagged `validation.validate_comment` line 260 as
needing changes. This hardcode (`ticket.status == "closed"`) is
technically wrong but functionally harmless — `comments.add_comment`
catches archived tickets via `TERMINAL_STATUSES` before `validate_comment`
is ever called.

Distinguishing "redundant but harmless hardcode" from "critical
hardcode that must change" requires understanding the call graph
between the two functions. The graph has this data (fn→fn edges),
but the analysis presented to the agent didn't surface it at the
right granularity. A better graph query: "show all code paths that
block external comments on terminal tickets" would reveal the
redundancy.

## Conclusions

1. **Recall is a ceiling, not a differentiator.** For this feature,
   all approaches find the same obvious edit sites. The graph doesn't
   help you find things that grep can't — the constants are all named
   and directly referenced.

2. **Precision is the real advantage.** The graph agent produces 2.8x
   fewer false positives than grep. In a real workflow, each false
   positive costs the agent a file read + reasoning cycle. At scale,
   this compounds.

3. **Efficiency is 3.2x.** The graph agent used 11 tool calls vs 35
   for grep. The savings come from skipping auto-adapting modules
   entirely instead of reading each one to confirm it doesn't need
   changes.

4. **Latent bugs are invisible to all static approaches.** The one
   site all agents missed (validation crash) requires code execution
   to discover. The graph can't help here — this is why test oracles
   matter.

5. **The graph's structural categorization is its unique contribution.**
   Only the graph-first agent produced the "hardcoded but correct"
   category, correctly reasoning about which hardcoded values are
   intentional. This structured reasoning framework reduces cognitive
   load even when it doesn't change the final answer.

## What the graph provides that grep cannot

Confirmed from the spike:

1. **Exact function references** — ignores imports, definitions,
   docstrings. 15 functions vs 25 grep hits for ACTIVE_STATUSES.

2. **Call chain analysis** — "what calls is_active?" → 7 direct,
   15 at 2 hops. Grep can't represent the question.

3. **Impact zone computation** — 36 functions across 12 modules in
   one Datalog query. Grep requires manual cross-referencing.

4. **Entity resolution** — bare name refs and attribute access
   resolve to the same entity.

5. **Structural categorization** — "references constant" vs
   "hardcodes value" is a graph property, not a text property.

Confirmed from the agent experiment:

6. **Precision filtering** — 60% precision vs 35% for grep.
   The graph helps agents SKIP non-sites, not FIND more sites.

7. **Efficiency** — 3.2x fewer tool calls. The graph provides
   a pre-computed map; grep requires iterative exploration.

# E27/E28: Graph-Native ClaimDesk — Results

## Experiment

**Task**: Add "duplicate" as a terminal status to ClaimDesk.

Same prompt for both conditions: "A ticket marked as duplicate means
it's a copy of another ticket. Like closed and archived, duplicate
tickets are no longer active. Tickets can be marked as duplicate from
the open or in_progress states."

**Graph condition**: Agent uses ClaimDesk MCP tools (add_status,
add_transition, check_obligations, project_all_to_disk). Python files
are projected from the claim graph automatically.

**File condition**: Agent edits Python files directly in a workspace
(workflow.py, notifications.py, analytics.py, permissions.py).

**12 integration tests**: duplicate in TERMINAL_STATUSES, in ALL_STATUSES,
not in ACTIVE_STATUSES, transitions from open and in_progress,
is_terminal check, not is_active, notifications suppress, analytics
tag is_terminal, active_ticket_count excludes, permissions archive rule,
existing statuses preserved.

## Results

| Condition | Runs | Bugs | Mean time | Mean cost | Tests |
|-----------|------|------|-----------|-----------|-------|
| graph     | 3    | 0/36 | 30.5s     | $0.067    | 12/12 |
| file      | 3    | 0/36 | 71.8s     | $0.199    | 12/12 |

### Per-run detail

**Graph**
| Run | Time  | Cost   | Tests | Bugs |
|-----|-------|--------|-------|------|
| 1   | 36.0s | $0.086 | 12/12 | 0/12 |
| 2   | 22.5s | $0.059 | 12/12 | 0/12 |
| 3   | 33.2s | $0.057 | 12/12 | 0/12 |

**File**
| Run | Time  | Cost   | Tests | Bugs |
|-----|-------|--------|-------|------|
| 1   | 92.3s | $0.255 | 12/12 | 0/12 |
| 2   | 75.2s | $0.194 | 12/12 | 0/12 |
| 3   | 48.0s | $0.148 | 12/12 | 0/12 |

## Analysis

### Both conditions achieve 100% correctness

At this scale (4 files, <100 LOC each), the file agent reads all code,
spots the patterns (TERMINAL_STATUSES used in notifications/analytics),
and updates consistently. No info-gap bugs because the codebase is
small enough for the agent to fully comprehend.

### Graph is 2.4x faster, 3x cheaper

Graph mean: 30.5s, $0.067. File mean: 71.8s, $0.199.

The graph agent's work is:
1. list_statuses (understand current state)
2. add_status("duplicate", "terminal")
3. add_transition("open", "duplicate")
4. add_transition("in_progress", "duplicate")
5. check_obligations (verify constraints)
6. project_all_to_disk (emit Python)

~6 tool calls. The file agent reads 4 files, reasons about each one,
edits each one. More tokens, more time.

### Structural guarantee vs empirical correctness

The graph agent's correctness is structural — not because the agent
is smarter, but because the graph derives consequences automatically.
Adding "duplicate" as terminal means:
- TERMINAL_STATUSES includes it (derived from status-group)
- Notifications suppress for it (derived from effect condition)
- Analytics tags it (derived from effect condition)
- Permissions unchanged (not status-dependent)

The file agent achieves the same result by reading and understanding
code. At this scale that works. The question is whether it scales.

### Where info-gap bugs would appear

E24b showed 38-46% first-pass failure on cross-domain tasks where agents
build NEW modules without seeing each other's code. This experiment
tests MODIFICATIONS to existing code where the patterns are visible.

The graph-native advantage would be stronger when:
- The codebase is large enough that agents can't read everything
- The change has non-obvious downstream effects
- Multiple agents modify the graph concurrently

### What this proves

The E27 vertical slice works: domain claims → evaluators → obligation
checker → projection → tests. The pipeline is real, not theoretical.

At small scale: graph matches file correctness, wins on speed and cost.
The thesis prediction is that the gap widens with scale.

## Files

- `experiments/e27-runtime-claimdesk/claimdesk.rkt` — domain model
- `experiments/e27-runtime-claimdesk/claimdesk-mcp.rkt` — MCP server (14 tools)
- `experiments/e27-runtime-claimdesk/runner.py` — experiment runner
- `experiments/e27-runtime-claimdesk/demo.rkt` — full pipeline demo
- `experiments/e27-runtime-claimdesk/test-claimdesk.rkt` — 13 unit tests

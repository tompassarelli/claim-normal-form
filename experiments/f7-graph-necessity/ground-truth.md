# F7 Ground Truth: Required Edit Sites

Feature: Add `archived` (terminal) and `on_hold` (active) statuses.

## Edit sites

| # | File | Location | Change | Tests covered |
|---|------|----------|--------|---------------|
| 1 | config.py | STATUSES (line 15) | Add "archived", "on_hold" | a01, a02, k01, k02, l03, l04 |
| 2 | config.py | ACTIVE_STATUSES (line 18) | Add "on_hold" | a04, g02, h01, i02, l02 |
| 3 | config.py | TERMINAL_STATUSES (line 22) | Add "archived" | a03, c01, e01, j01, k04, k05 |
| 4 | config.py | STATUS_TRANSITIONS (lines 25-30) | Add on_hold/archived entries | b08, b09 |
| 5 | workflow.py | VALID_TRANSITIONS (lines 25-29) | Add on_hold/archived entries | b01-b05, c04, c05, d01-d03 |
| 6 | models.py | Ticket.is_terminal (line 36) | Property + include "archived" | m01, m02 |
| 7 | validation.py | validate_assignment (line 204) | Early return after terminal check | k05 |

**7 edit sites across 4 files out of 18 total modules.**

## Key insight: auto-adapting modules

14 of 18 modules need NO changes because they reference `ACTIVE_STATUSES`
and `TERMINAL_STATUSES` dynamically. These include: search.py, reports.py,
notifications.py, sla.py, assignment.py, comments.py, imports_exports.py,
events.py, store.py, tickets.py, audit.py, permissions.py, tags.py, teams.py.

The challenge for agents: distinguishing files that reference status constants
(auto-adapt, no edit needed) from files that hardcode status values (need editing).

## Scoring

- **First-pass recall** = edit sites correctly identified / 7
- **Precision** = correct identifications / total identifications
- An identification counts if the agent names both the file AND the specific
  constant/function to change. Naming only the file is a half-credit.

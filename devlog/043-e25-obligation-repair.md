# 043 — E25: Obligation repair — the graph checks what you missed

**2026-05-22**

## The question

E24b showed the facade fails for semantically distant tasks. The
permissions agent doesn't know lifecycle state matters for access
control. Can the graph fix this by telling the agent what it missed?

## The answer

Yes. finish_check + one repair round: **1/24 info-gap bugs (4%)**.
Down from 9/24 (38%) without it.

```
cnf_repair:   1/24  (4%)   $0.142/run
cnf_facade:   9/24  (38%)  $0.156/run  (E24b)
file_repair:  1/24  (4%)   $0.293/run  (E24b)
```

Same correctness as file + repair. Half the cost.

## How finish_check works

The tool is a structural linter backed by the graph. It:

1. Parses the agent's code with `ast`
2. Queries the graph for lifecycle constants, modules, functions
3. Cross-references: does this code touch tickets? Does it import
   workflow? Does it handle terminal statuses? Does it gate permissions
   on lifecycle?
4. Returns specific obligations with import statements and evidence

For the permissions agent, finish_check finds three critical
obligations:
- No workflow import (the module defines lifecycle constants)
- Terminal statuses not handled (archived, closed exist)
- Permission checks don't gate on lifecycle state

The agent gets these obligations + its own code and produces a fix.
One round. The fix adds `from workflow import TERMINAL_STATUSES` and
gates `can_manage` on ticket lifecycle state.

## What it can't do

finish_check is structural, not behavioral. Run 2 had 1/8 bugs after
repair — the permissions agent imported from workflow and knew about
archived, but implemented the lifecycle gate wrong. finish_check
passed. The test caught it.

This is the right boundary. Structural checks catch missing knowledge.
Tests catch wrong logic.

## The cost story

CNF repair is cheaper because:
- Facade agents generate code in fewer turns (no file browsing)
- finish_check is programmatic (zero LLM cost)
- Obligation repair is targeted (specific fixes, not "debug failures")
- File repair requires the repair agent to read all source + failures

This is the first time CNF matches file+repair correctness at roughly
half the observed cost, while outperforming both no-repair first-pass
baselines.

## The thesis shift

E24a: "facade tools cause agents to discover what they need"

E24b: "only when the task aligns with tool descriptions"

E25: "the graph checks whether you missed hidden obligations"

The new stack:
```
graph substrate → facade → obligation discovery → repair
```

Facade is opt-in discovery. Obligations are mandatory verification.
The graph's value isn't helping agents explore — it's catching what
they miss when they don't.

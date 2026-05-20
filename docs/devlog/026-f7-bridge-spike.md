# 026 — F7: Bridge validation spike

F2–F6 proved accumulation matters. But the accumulation in those
experiments was filesystem-level — agents wrote files sequentially.
The graph was there, but the experiments didn't prove the graph was
necessary. An agent reading all prior files would get the same
information.

F7 must prove the graph provides something the filesystem can't.

## The spike

Before designing the full experiment, I need to know: can the Python
bridge actually parse a realistic codebase and produce useful
structural queries? Built an 18-module helpdesk app (4947 LOC, 238
functions) and parsed it through the CNF Python bridge.

First run: 235 entities, 167 dependency edges, but ACTIVE_STATUSES
showed 0 references. That's the key constant — every module that
filters by ticket status checks it. A graph that can't find those
references is useless.

## The fix

The bridge had four gaps:

1. **Bare name references** — `ACTIVE_STATUSES` in `status in
   ACTIVE_STATUSES` is an `ast.Name` node. The bridge was returning
   a raw value, not creating any claims. Fixed: create a `name-ref`
   entity with `py-calls-pred` so `py-contains-call` can find it.

2. **Comprehension filters** — `[t for t in tickets if t.status in
   ACTIVE_STATUSES]`. The `if` condition was silently dropped. Fixed.

3. **Top-level variables** — `VALID_TRANSITIONS = {...}` at module
   level was skipped entirely (bridge only parsed function/class
   defs). Fixed: parse `assign`, `ann_assign`, and `import` nodes.

4. **Call target trees** — `VALID_TRANSITIONS.get(from_status, [])`
   was captured as a flat string `"VALID_TRANSITIONS.get"` but the
   object reference was lost. Fixed: parse the `func_node` subtree.

Added a new Datalog rule `py-fn-references` for function→variable
dependencies (complementing the existing `py-fn-depends-on` for
function→function).

## Result

After fixes:

- **356 entities**, 23,545 claims
- **310 fn→fn edges**, 143 fn→var edges
- **TERMINAL_STATUSES**: 8 functions found, 8 ground truth → **8/8**
- **ACTIVE_STATUSES**: 15 functions found, 15 ground truth → **15/15**
- **VALID_TRANSITIONS**: 2/2, **STATUS_TRANSITIONS**: 1/1

The graph matches grep's ground truth exactly for actual code
references, while correctly ignoring imports, definitions, and
docstrings. Grep returns 25 hits for ACTIVE_STATUSES; the graph
returns exactly the 15 functions that reference it in executable code.

## What the graph does that grep can't

The impact zone query: "what functions need inspection when status
sets change?" Combines constant references with call chain analysis
in one operation. Result: **36 functions across 12 modules**, grouped
by file. With grep, this requires cross-referencing multiple searches
and manually identifying function boundaries.

The transitive caller query: `is_active` has 7 direct callers, which
have 15 total callers at 2 hops. The graph computes this via Datalog.
Grep can't even represent the question.

## What this means for F7

The spike is GREEN. The graph is rich enough to orient an agent before
it reads any source files. The full experiment can proceed: three
conditions (grep, file-reader, graph-first), scoring first-pass
edit-site recall against the hidden ground truth.

The honest question: does graph orientation actually help the agent
find sites it would miss otherwise? The spike shows the information
is there. F7 tests whether the agent uses it.

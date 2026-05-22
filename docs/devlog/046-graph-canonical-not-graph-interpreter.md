# 046 — Graph-canonical, not graph-interpreter

**2026-05-22**

## The confusion

"Graph runtime" has been doing double duty. Sometimes it means "the
graph evaluates everything like an interpreter." Sometimes it means
"the graph is the canonical program representation." These are
different claims with different implications.

The first is an execution strategy. The second is an architecture.

The project is about the architecture.

## Four axes

There are four independent questions in this work:

1. **Source of truth**: Is the program stored as text files or as a
   claim graph?

2. **Editing interface**: Does the agent edit files or structured
   graph facts?

3. **Semantic analysis**: Are dependencies, obligations, permissions,
   transitions derived from graph structure?

4. **Execution strategy**: Do we interpret the graph directly,
   compile it, JIT it, or project it to Python/JS?

The thesis lives in axes 1 + 2 + 3. Axis 4 is an implementation
choice.

Compilation to Python does not betray the thesis. It only betrays
the thesis if the projected files become the thing agents edit and
reason from.

## What this means in practice

A graph-native program is one where:

```
agent edits claims
→ graph validates claims
→ graph derives consequences (obligations, types, deps)
→ graph projects executable artifact
→ artifact runs
→ failures map back to claims
```

The execution can be:
- **Interpreter**: graph walks claims at runtime. Good for tests,
  debugging, provenance, agent-visible reasoning.
- **Compiled projection**: graph emits Python/JS. Good for speed,
  deployment, ecosystem integration.
- **JIT / incremental**: graph recompiles on mutation. Good for
  fast feedback during development.

The common layer is the graph IR. That's the valuable artifact.

## What E27-E29 actually built

Retrospectively, E27-E29 is already graph-canonical:

- **Source of truth**: ClaimDesk domain is claims. Statuses,
  transitions, permissions, effects, obligations — all entities with
  predicate-linked claims. Not parsed from Python.
- **Editing interface**: agents use MCP tools to edit claims. They
  never touch Python files.
- **Semantic analysis**: obligation checker queries claim structure
  to find missing constraints. Projector reads claim structure to
  emit correct Python.
- **Execution strategy**: Racket-side has interpreter mode
  (`can-transition?`, `check-permission` evaluate the graph
  directly). Python is a compiled projection.

The confusion was calling this "graph runtime" and then worrying
whether the graph had to interpret everything. It doesn't. The
program lives in the graph. How it executes is secondary.

## What E29 revealed about the graph's role

E29 showed the graph acting as a **semantic commitment amplifier**.

When the agent classifies correctly (`add_status("suspended",
"blocked")`), the graph derives all downstream consequences:
BLOCKED_STATUSES, is_blocked(), analytics tagging, obligation
violations for missing permissions. One structural choice propagates
everywhere. 0-1 bugs.

When the agent misclassifies (`"active"` instead of `"blocked"`),
the graph propagates the wrong structure everywhere. 6-7 bugs.

File agents degrade locally — they patch ad-hoc and miss things.
Graph agents commit globally — right or wrong.

This is not a weakness to fix with prompting. It's an architectural
lesson: the graph needs to do more semantic work. Instead of trusting
the agent's classification and amplifying it, the graph should
validate or derive the classification from declared properties.

## The execution contract

A CNF program should consist of:

- **Entities**: the things in the domain
- **Relations**: typed predicates linking entities
- **Rules**: Datalog-derived facts over the relation graph
- **Effects**: declared side-effects (notifications, analytics, etc.)
- **Evaluators**: functions that query the graph to answer questions
  (can this transition happen? does this user have permission?)
- **Obligations**: structural constraints derived from the graph
  (every terminal status must have an archive permission, every
  blocked status must have suspend/resume permissions)
- **Projections**: compiled artifacts derived from the graph
  (Python modules, API schemas, config files)

The graph is canonical. Execution may occur through any strategy.
But all execution artifacts are traceable to claims, all edits
happen against claims, and all obligations are derived before
deployment.

## What not to prove

Do not get trapped proving:

> CNF as a graph interpreter is faster than Python.

That's probably the wrong battle and it's not the thesis.

The thesis is:

> CNF lets agents build and modify programs faster and with fewer
> missed obligations because program structure is explicit, queryable,
> and editable — and text is a materialized view, not the source of
> truth.

Execution optimization comes later.

## The right phrase

Not "graph runtime." That implies interpreter.

Better: **graph-canonical program substrate**, or **executable claim
graph**, or just **graph-native software**.

The core idea: the program lives as structured facts. Text is a
materialized view. Agents mutate the facts. The system derives
consequences.

# E27: ClaimDesk as graph-native executable claims

## Thesis

A graph-native executable substrate lets agents build and modify
software faster because the agent edits the actual structured program
state instead of repeatedly serializing/deserializing through text
files.

## What this tests

The thin vertical slice:

```
agent edits graph
→ graph derives obligations
→ graph evaluates behavior
→ graph projects runnable artifact
→ tests verify artifact
```

## What the graph contains

Not a parsed mirror of Python. The graph IS the program:

- **Entities**: statuses, transitions, roles, permissions, effects, tickets, users
- **Predicates**: status-name, status-group, transition-from/to, role-name,
  permission-action, permission-requires-role, ticket-status, effect-trigger/kind/condition
- **Evaluators**: can-transition? (transition validation), check-permission (role-based access)
- **Obligation checker**: obligations-for (structural constraint queries over claims)
- **Projection**: project-workflow-py, project-permissions-py (emit Python from graph)

## How it differs from E24/E25

E24/E25 treated CNF as a semantic index: agents wrote Python, the graph
held parsed metadata, facade tools helped discovery, finish_check verified
generated code against graph facts.

E27 inverts the relationship:
- Agents edit claims, not files
- Behavior (transitions, permissions) is evaluated on the graph
- Obligations are structural queries over claims, not string analysis
- Python is a projection, not a source

## The "add duplicate" test

File-native agent: must find and edit TERMINAL_STATUSES in workflow.py,
update transition rules, update every module that filters by status,
update tests. Misses some. Needs repair.

Graph-native: adds one status claim + transition claims. Terminal
membership is derived from status-group. Transition validation updates
automatically. Projection emits updated Python with the new status in
TERMINAL_STATUSES and VALID_TRANSITIONS.

## Success criteria

1. Domain model builds entirely from claims (no parsed files)
2. Executable behavior works: can-transition? rejects invalid paths,
   check-permission enforces role gates
3. Adding a new terminal status requires only claim edits, not code edits
4. Obligations fire as structural queries over the graph
5. Projection emits valid Python that includes all graph-derived facts
6. Tests verify the pipeline end to end

# 044 — Return to the runtime thesis

**2026-05-22**

## The drift

E24a through E25 tested CNF as a semantic index. Agents write Python
files. The graph holds parsed metadata. Facade tools help agents
discover structure. finish_check verifies generated code against graph
facts. Obligation repair fixes what agents miss.

That work produced real results:
- Facade discovery: 0% info-gap failure for aligned tasks (E24a)
- Facade limits: 38% failure for cross-domain tasks (E24b)
- Obligation repair: 4% failure, matching file+repair at half cost (E25)

But it's the wrong road. CNF-as-semantic-index puts the project in the
same arena as Sourcegraph, Cursor, LSPs, tree-sitter. Useful tooling.
Not the thesis.

## The thesis

The claim is not:

> CNF is a better code index.

The claim is:

> A graph-native executable substrate lets agents build and modify
> software faster because the agent edits the actual structured program
> state instead of repeatedly serializing/deserializing through text
> files.

That is stronger and weirder. It means:

- The canonical program is a graph of claims
- Evaluation, inference, verification, projection, and editing all
  operate on that graph
- Text files (Python, JS, whatever) are projections, not sources
- Agents edit claims, not files
- Obligations are native constraints, not string analysis

## What transfers from E24/E25

The semantic-index work isn't wasted. The core insight transfers:

> Agents miss hidden cross-domain obligations. A graph can expose those
> obligations and drive repair.

In the index version, finish_check parses Python strings and matches
patterns. In the runtime version, obligations are Datalog-derived
facts over the actual program state. The mechanism is the same. The
substrate changes from "analyzing emitted text" to "querying canonical
structure."

## What the runtime looks like for ClaimDesk

Not a general-purpose lambda calculus reducer. A domain-specific
executable graph:

```
domain claims (entities, statuses, transitions, permissions, roles)
+ Datalog-derived facts (terminal states, valid transitions, obligations)
+ transition evaluator (can this status change happen?)
+ permission evaluator (who may do what?)
+ obligation checker (what constraints are missing?)
+ projection emitter (generate Python/JS from claims)
```

The agent task becomes: add a cross-cutting feature by editing claims.
Not by writing Python. The graph verifies, derives, evaluates, and
projects.

Example: "add duplicate as a terminal status."

File-native agent: must find and edit TERMINAL_STATUSES in workflow.py,
update transition rules, update every module that filters by status,
update tests. Misses some. Needs repair.

Graph-native agent: adds one claim. Datalog derives the downstream
consequences. Obligation checker flags any module claims that don't
account for the new terminal status. Projection emits updated files.

That's the difference between editing a shadow and editing the thing
that casts the shadow.

## The expected scaling curve

```
small codebase:  text faster (graph overhead > benefit)
medium:          roughly tied (graph catches missed obligations)
large:           graph-native pulls ahead (if the thesis is true)
```

The experiment needs a scaling ramp, not just a toy demo. One module
proves "claims can represent a config table." That's not the thesis.
A thin vertical slice — entities, statuses, transitions, permissions,
effects, obligations, tests, projection — tests whether graph-native
development actually works.

## What's next

Build the smallest version of:

```
agent edits graph
→ graph derives obligations
→ graph evaluates behavior
→ graph projects runnable artifact
→ tests verify artifact
```

The semantic-index line (E24a → E24b → E25) is a completed side
branch. The mainline returns to graph-eval runtime.

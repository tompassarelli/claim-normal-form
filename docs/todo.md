# CNF Roadmap

## DONE: Agent Interface (MCP Server)

18 MCP tools over JSON-RPC 2.0 / stdio. Claude connects, parses
programs into claims, queries dependencies, renames functions,
renders results — all through tool calls. Shipped `a12dce7`.

## DONE: Materialized Views (Reactive Datalog)

`materialize!` caches derived facts and registers hooks on `claim!`.
New claims delta-propagate through rules incrementally. Views stay
current without re-running the fixpoint.

Results at N=200: dep query drops from 67ms (cold) to 0ms (cache hit).
Incremental parse maintains views live — query after parse is O(1).
Shipped `a12dce7`.

## NOW: Provenance-Tracked Deletion

Supersession currently invalidates all materialized views, forcing
a full fixpoint recompute on the next query. With provenance tracking:

- Each derived tuple records which claim IDs supported its derivation
- On supersession, retract only tuples whose support set includes
  the superseded claim
- Re-derive what can still be derived through alternate paths
- Result: supersession becomes O(delta), not O(full-fixpoint)

**Done when:** rename at N=200 → next dep query is O(delta), not 38ms.

## NEXT: Agent Coding Experiment (E1)

The thesis: an agent codes faster with CNF than text as codebase
grows. First experiment to prove it. See `docs/experiments/README.md`.

## LATER: Homoiconic Rules (Rules as Claims)

Datalog rules become claims in the graph. Rules are:
- Versionable (supersede a rule = schema migration)
- Queryable (meta-programming: "which rules derive this relation?")
- Composable (rule depends on rule)

The system describes itself. An agent can modify the query engine
as part of its coding workflow.

**Prerequisite:** provenance-tracked deletion (rule changes must
trigger incremental recomputation, not full rebuild).

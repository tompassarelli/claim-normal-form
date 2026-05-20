# CNF Roadmap

## NOW: Agent Interface (MCP Server)

Expose CNF operations as MCP tools so an AI agent can use the claim
graph as its codebase representation. This is the prerequisite for
every experiment downstream.

**Tools:**
- Core: reset, create_entity, create_named, create_value, claim
- Query: query (Datalog), define_rule, inspect, claims_where, resolve_symbol
- Schema: define_predicates, lookup, find_by, update
- Lang: parse_program, render, rename

**Done when:** Claude can connect via MCP, parse a program into claims,
query dependencies, rename a function, and render the result — all
through tool calls.

## NEXT: Materialized Views (Reactive Datalog)

Standing queries maintained incrementally when claims change.
Today every `query` call reruns the full semi-naive fixpoint.
With materialized views, `claim!` and supersession trigger delta
updates on registered views. Agent queries become O(delta).

**Key design questions:**
- Which views to materialize (all rules? explicit registration?)
- Invalidation granularity (per-rule? per-relation?)
- Integration with supersession (view update on supersede)

**Done when:** dependency query at N=200 drops from ~39ms to <1ms
for incremental updates after a single claim change.

## LATER: Homoiconic Rules (Rules as Claims)

Datalog rules become claims in the graph. Rules are:
- Versionable (supersede a rule = schema migration)
- Queryable (meta-programming: "which rules derive this relation?")
- Composable (rule depends on rule)

The system describes itself. An agent can modify the query engine
as part of its coding workflow.

**Prerequisite:** materialized views (rule changes must trigger
incremental recomputation, not full rebuild).

## HORIZON: Agent Coding Experiment

The thesis: an agent codes 5-10x faster with CNF than text as
codebase grows. To prove it:

1. Define a benchmark suite of coding tasks at scale (N=100, 500, 1000 functions)
2. Measure wall-time for rename, dependency query, structural edit, add function
3. Compare: agent + CNF/MCP vs agent + text files + grep/sed
4. Show crossover point where CNF wins

**Requires:** MCP server + materialized views + a real workload generator.

# 003 — Homoiconic rules: rules as claims

**Date:** 2026-05-20

## What happened

Datalog rules are now first-class entities in the claim graph. A rule
defined via `define-rule!/claims` or the MCP `define_rule` tool creates
an entity with two claims:

- `rule-head-rel` → the derived relation name (e.g., "fn-depends-on")
- `rule-source` → serialized S-expression of the full rule

The rule simultaneously exists in the in-memory rules list (so the
engine evaluates it) and in the claim store (so it's queryable,
inspectable, and versionable).

## What this enables

**For agents:**
- Define new derived relations mid-session via `define_rule`
- Query what rules exist via `list_rules`
- Inspect rule entities like any other object
- Replace a rule via `supersede_rule` — old rule's claims get
  superseded, new one takes effect, derived facts recompute

**For the system:**
- Rules are versionable: supersession tracks rule evolution
- Rules are queryable: "which rules derive this relation?" is an
  EDB query over rule-head-rel claims
- Rules are composable: rule A can reference rule B's derived relation
- The system describes itself — an agent can ask about its own
  inference structure

## Design decisions

**Dual existence.** Rules live in both the in-memory list (for the
engine) and the claim store (for queryability). Legacy rules from
`define-rule` macro (eval, graph, lang layers) stay in-memory only.
Homoiconic rules from `define-rule!/claims` live in both.

**Conservative invalidation.** Rule changes trigger `invalidate-views!`
(mark matview invalid) rather than incremental retraction. The next
query recomputes the full semi-naive fixpoint with the updated rule
set. This is correct but not optimal — incremental rule change
propagation is a future optimization.

**Serialization round-trip.** Rules serialize to S-expressions:
`(rel (? var) "literal") :- (body ...)`. Reconstruction from claims
parses this string back through `parse-clauses`. The round-trip is
exact for rules defined via MCP (which always use string/var args).

**Rule metadata is EDB-only.** The `rule-head-rel` and `rule-source`
predicates don't appear in any Datalog rule body. They're queryable
via base relations (current-triple, current-claim) but don't feed
into derivations. This avoids a chicken-and-egg problem where rules
about rules would need to be evaluated to determine which rules exist.

## Numbers

- 20 MCP tools (was 18: added `list_rules`, `supersede_rule`)
- 44 passing tests (was 29: added define + supersede homoiconic tests)
- `define_rule` via MCP creates rule entity, claims visible via `inspect`
- `supersede_rule` marks old claims `[superseded]`, new rule takes effect
- All benchmarks (E1, E2) pass without regression

## What's next

Real agent comparison: two Claude sessions, same refactoring task.
With homoiconic rules, the CNF agent can define new derived relations
mid-session — a capability that doesn't exist with text/grep/edit.

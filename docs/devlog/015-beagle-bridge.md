# 015: Beagle bridge — real language, real claim graph

**Date:** 2026-05-20

## The shift

Every prior experiment used a toy language: `(defn f [a b] (+ a b))`.
Three form types. No types, no records, no closures, no pattern matching.
Good enough to validate the architecture, but not a real language.

Beagle is a real language — typed Lisp, 50+ form types, 964 tests,
6 emit targets. It already has a parser in Racket. The bridge reuses
that parser and walks its AST structs into CNF claims.

## What the bridge does

```
source.bgl → [beagle parser] → AST structs → [bridge module] → claim graph
```

Beagle doesn't change. The bridge (`beagle-lang.rkt`, ~900 lines) imports
`beagle/private/parse`, calls `parse-program`, walks the transparent
Racket structs, creates entities and claims.

18 predicates. The expression walker handles 30+ beagle form types.
Scope tracking resolves function calls to entity references. Datalog
rules derive `contains-call` (transitive has-child walk) and
`fn-depends-on` (function-to-function, filtered by form-kind).

## What surprised us

**The fn-depends-on rule needed refinement.** The toy language only had
functions with bodies. Beagle has let, fn, when-let, loop — all with
body predicates. The original rule `fn-depends-on(?caller, ?callee) :-
body(?caller, ?body), contains-call(?body, ?callee)` matched everything.
Fixed by adding form-kind "defn" constraints on both sides.

**Entity IDs are strings, not numbers.** The Datalog query returns
string-typed IDs in hash tables. Converting via `string->number` produces
values that don't `equal?` the original string IDs. Subtle — took a few
rounds to track down.

**`parse-body-exprs!` needed to handle non-list bodies.** Beagle's
`if-let-form-then-body` returns a single form, not a list. The function
assumed a list. One extra `cond` branch fixed it, but it shows how real
parsers have more edge cases than toy ones.

**Upstream fix was necessary.** `resolve-symbol` in cnf.rkt only checked
kernel naming (`named!`), not graph naming (`give-name!`). The bridge
uses `give-name!` exclusively. Fixed at the root — `resolve-symbol` now
checks both naming systems with supersession filtering. Was a latent bug
affecting all graph-layer code.

## The numbers

9 forms (2 records, 7 functions): 565 objects, 384 claims.
7 direct dependencies, 15 transitive pairs.

Parse: 2.3ms. Rename: 0.04ms (propagates to 3 callers).
Matview query: 0ms. Incremental add: 0.9ms. Modify+rename: 1.2ms.

All operations from prior experiments work: dependency query, custom
rules (trans-dep), materialized views, rename propagation, incremental
parse, rendered output.

## What this means

CNF now operates on a real language. The claim graph doesn't know or
care that the source is beagle vs the toy language — it's all entities,
values, and claims. The Datalog rules are the same. The matviews work
the same. The MCP server exposes the same 30 tools.

The bridge pattern is general: any language with a Racket-accessible
parser can become a claim graph source. Walk the AST, create claims,
define rules. The structural analysis machinery handles the rest.

The MCP server is now wired to beagle-lang. A Claude Code agent can
parse beagle source, query cross-function dependencies, rename with
automatic propagation, and incrementally edit — all through tool calls.

## Open issues

- Parameter ordering in rendered output doesn't always match source
  (hash-based claim ordering). Cosmetic — doesn't affect correctness.
- `reduce` renders operator as quoted string (`"+"`). The `+` symbol
  resolves to a string value, not a named entity.
- Match clause patterns are not preserved in claims — only the clause
  bodies. Match renders without pattern context.
- Type declarations (defscalar, defunion, defenum) parse as generic
  entities without internal structure.

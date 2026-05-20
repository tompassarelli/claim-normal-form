# E13: Beagle Bridge — Results

**Date:** 2026-05-20

## Setup

Bridge module (`beagle-lang.rkt`) parses real beagle syntax into CNF's
claim graph. Beagle is a typed Lisp with 50+ form types, 6 emit targets
(CLJ, CLJS, JS, Nix, SQL, Py), 964 tests. The bridge reuses beagle's
existing parser (`beagle/private/parse`) — beagle doesn't change.

Test program: 9 forms (2 records, 7 functions), financial analytics
domain with layered dependencies.

## Timing

| Phase | Operation | Time |
|-------|-----------|-----:|
| Parse | 9 forms → 565 objects, 384 claims | 2.3ms |
| Discover | query fn-depends-on (7 edges) | 1.7ms |
| Materialize | fn-depends-on + trans-dep | 15ms |
| Cache | fn-depends-on (matview hit) | 0ms |
| Cache | trans-dep (15 pairs) | 0ms |
| Rename | trade-value → compute-trade-value | 0.04ms |
| Render | all 9 forms | 0.5ms |
| Add function | incremental | 0.9ms |
| Modify + rename | incremental | 1.2ms |
| Deps after mutation | matview hit (8 edges) | 0ms |

## What the bridge does

Source text → beagle parser → AST structs → entity/claim graph.

```
source.bgl → [beagle parser] → AST structs → [bridge module] → claim graph
```

### Claim mapping

18 predicates. Every beagle form type maps to claims:

- `defn-form` → function entity + typed params (with position) + return type + body expression tree
- `defrecord` → record entity + typed fields with positions
- `def-form` → binding entity + type + value expression
- `call-form` → calls predicate (resolves to function entities when known)
- `if-form`, `if-let-form` → condition/then/else with has-child traversal
- `let-form` → bindings with scope, body, has-child traversal
- `fn-form` → anonymous function with params and body
- `match-form`, `cond-form`, `when-form`, `do-form` → has-child
- `for-form`, `loop-form`, `try-form` → has-child traversal
- `method-call`, `kw-access` → calls predicate
- `vec-form`, `map-form` → collection with children
- 15+ additional form types (if-let, when-let, case, doseq, etc.)

### Datalog rules

`contains-call` walks the expression tree via `has-child` transitively.
`fn-depends-on` is derived: caller has form-kind "defn" + body, callee
has form-kind "defn" + appears in contains-call.

### What the demo showed

1. **Correct cross-function dependencies**: 7 direct edges match the
   program structure exactly (risk-report → portfolio-summary →
   {high-value-trades, portfolio-pnl, portfolio-total} → trade-value).

2. **Transitive closure**: 15 pairs from 7 edges. risk-report
   transitively depends on trade-value (4 hops).

3. **Rename propagation**: Rename trade-value → compute-trade-value
   in 0.04ms. Three call sites (portfolio-total, trade-pnl,
   high-value-trades) auto-update — no find-replace.

4. **Incremental edit**: add-function! (0.9ms), modify-function! with
   simultaneous rename (1.2ms). Dependencies auto-update: new function
   weighted-pnl → portfolio-pnl appears, compute-trade-value →
   net-trade-value rename propagates through all callers.

5. **Render round-trip**: Records render as `(defrecord Name [(field : Type)])`.
   Functions render with typed params, return types, nested expressions.
   Rename propagates in rendered output.

## Key numbers

| Metric | Value |
|--------|------:|
| Forms parsed | 9 (2 records, 7 functions) |
| Objects | 565 |
| Claims | 384 |
| Direct dependencies | 7 edges |
| Transitive dependencies | 15 pairs |
| Parse time | 2.3ms |
| Rename time | 0.04ms |
| Render time | 0.5ms |
| Form types handled | 30+ |
| Predicates | 18 |

## Comparison to E12 (toy language)

E12 used a 100-function toy language with `(defn name [a b] (+ a b))`
syntax. E13 uses real beagle syntax with types, records, match, if-let,
fn (lambda), let bindings, method calls, etc.

| | E12 (toy lang) | E13 (beagle) |
|--|----------------|--------------|
| Parser | 200-line custom | 3000-line beagle parser |
| Form types | 3 (defn, call, binop) | 30+ |
| Type annotations | No | Yes (params, returns, generics) |
| Records | No | Yes (defrecord) |
| Pattern matching | No | Yes (match, case) |
| Closures | No | Yes (fn, let) |
| Dependency accuracy | Correct for simple calls | Correct for nested/transitive |

The bridge is ~900 lines (beagle-lang.rkt) vs ~200 lines for the toy
language (lang.rkt). The extra complexity handles real-world form types,
type annotations, and proper scope tracking.

## Verified against beagle's demo.bclj

Also tested against beagle's official `examples/demo.bclj`:
- 15 forms (records, scalars, unions, enums, functions, top-level calls)
- 381 objects, 220 claims (from prior session — numbers updated with form handler expansion)
- Correctly identifies: typed params, return types, if-let, match, fn (lambda), method calls
- Renders: records, typed functions, if/if-let, let, fn, call expressions

# E12: Real Codebase Demo — Results

**Date:** 2026-05-20

## Setup

100 functions, 5 layers, 298 lines. Financial analytics domain
(portfolio management, risk analysis, performance attribution).

- Layer 0: 15 primitives (scale-rate, discount, compound, blend, etc.)
- Layer 1: 20 functions composing primitives (interest, sharpe, alpha, etc.)
- Layer 2: 25 functions composing layer 1 (portfolio analytics, risk metrics)
- Layer 3: 25 functions composing layers 1+2 (signals, attribution, compliance)
- Layer 4: 15 top-level reports composing everything (board-deck, firm-pnl)

## Timing

| Phase | Operation | Time |
|-------|-----------|-----:|
| Parse | 100 functions → 2399 objects, 1672 claims | 37ms |
| Discover | query fn-depends-on (245 edges) | 0.1ms |
| Rules | define trans-dep + shared-dep | <1ms |
| Rules | materialize 3 rules | 210ms |
| Rules | query trans-dep (1655 pairs) | 0.2ms |
| Hub | define + materialize hub-pair | 3.9s |
| Hub | query hub-pair (1813 triples) | 0.4ms |
| Refactor | rename blend → mix | 0.1ms |
| Refactor | query fn-depends-on post-rename (cache hit) | 0.1ms |
| Incremental | add-function! | 55ms |
| Incremental | query new function's deps (auto-updated) | 0.1ms |
| Incremental | modify-function! | 584ms |
| Incremental | remove-function! | 199ms |

## Key findings

### Parse: 37ms for 100 functions

2399 objects (entities + values), 1672 claims (triples). The live
semantic index is built during parse — no separate indexing step.
Built-in rules (fn-depends-on, contains-call) materialize incrementally
as claims are added.

### Query: O(1) matview hits

After materialization, every query is a cache hit: 0.1-0.4ms regardless
of result size. fn-depends-on returns 245 edges in 0.1ms. trans-dep
returns 1655 pairs in 0.2ms. This is the core thesis: the agent pays
O(N²) once during materialization, then every subsequent query is O(1).

### Materialization cost scales with output size

trans-dep + shared-dep: 210ms. hub-pair (composing both): 3.9s. The
hub-pair rule generates 1813 triples from a 3-way join over large
relations — the semi-naive evaluation touches many candidate tuples.
This is an honest cost that gets amortized across all subsequent queries.

### Rename: 0.1ms with automatic propagation

Renaming `blend` to `mix` takes 0.1ms (two claims: new name, supersede
old). The matview auto-updates — querying fn-depends-on after rename
still returns 245 edges, and rendering any function that called `blend`
now shows `mix`. No reparse, no re-derivation.

### Incremental parse: rules survive mutations

This is the E9 missing piece.

- **add-function!** (55ms): Parses one function, adds to existing graph.
  Matview hooks fire incrementally. Query immediately returns correct
  dependencies for the new function.

- **modify-function!** (584ms): Retracts old body/params via supersession,
  parses new definition reusing the entity ID. Other functions' call
  references still work because the entity is preserved. Matview
  recomputes affected derived relations.

- **remove-function!** (199ms): Invalidates all owned claims. Derived
  relations retract affected tuples automatically.

All 15 rules survived across all three mutations. No re-definition
needed. The claim graph is now a live, editable semantic index.

### Structural analysis

- 245 direct dependency edges
- 1655 transitive dependency pairs (trans-dep)
- firm-pnl (top-level) transitively depends on 62 of 100 functions
- 84 unique hub functions (functions appearing in shared-dep pairs
  that are also transitively connected)
- 1740 transactions tracking every mutation

## What this demonstrates

The full workflow an agent would use:

1. **Parse** a non-trivial codebase (100 functions) → live semantic index
2. **Discover** structure via built-in derived relations
3. **Define custom rules** composing existing relations
4. **Refactor** via rename → all references auto-update
5. **Evolve** via incremental parse → add/modify/remove functions
   without losing accumulated rules or derived relations
6. **Query temporally** — every mutation is a transaction

The agent never re-derives anything. Parse once, define rules once,
query forever. Mutations flow through the graph incrementally.

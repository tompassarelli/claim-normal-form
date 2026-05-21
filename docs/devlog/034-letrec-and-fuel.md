# 034 — Letrec, Fuel, and the Unified Graph

**Date:** 2026-05-21

## What

Added `letrec` and a fuel budget to the graph evaluator. The claim
graph now supports recursive programs. An infinite loop is bounded,
not a crash — fuel exhaustion becomes a queryable claim in the graph.

Factorial(5) = 120, evaluated entirely as claim-graph reductions with
no source file.

## How letrec works in the graph

Standard two-phase environment patching, using CNF's additive semantics:

1. Create binding entity for the recursive name
2. Create env node mapping binding → placeholder
3. Evaluate the lambda in this env → closure captures the env
4. Add a NEW `env-value` claim on the env node pointing to the closure
   (newest claim wins in `env-lookup` due to index ordering)
5. Evaluate the body — recursive calls find the closure through the
   patched env

No formal supersession needed. The placeholder claim is shadowed, not
destroyed. Both are visible in the full history.

## Fuel

`graph-eval` accepts `#:fuel` (default 10000). A shared mutable counter
decrements on every node evaluation. When it hits zero:

1. An "incomplete" entity is created in the graph
2. A reduction record links it to the expression that ran out of fuel
3. `exn:fuel` is raised, carrying the incomplete node ID

"This reduced to X" and "this failed to reduce within budget" are both
queryable facts in the same graph, via the same predicates.

## The fork this doesn't resolve

Fuel answers: "can my evaluator avoid hanging?"

It does **not** answer: "does this program terminate?"

Those are different promises. With a total core, "still runs" is a
decidable guarantee the substrate can make without executing anything.
With fuel, "still runs" means "finished within budget on the inputs
we tried" — empirical, not proven.

**Current position:** scaffold. `letrec` + fuel gets recursion working
and makes non-termination bounded. This is the right immediate move.

**Open design target:** termination/totality as a queryable per-node
property. The strongest version doesn't choose globally between total
and general-recursive. It classifies each node:

- provably total (structural recursion, termination decidable)
- fuel-bounded (general recursion, validated empirically)
- effectful
- unknown / unresolved

"Which parts of this program are guaranteed to terminate and which are
only tested?" is a query no normal language can answer. The claim graph
could.

That makes totality a derived semantic relation — exactly the kind of
thing Datalog is built to express. Not building it now. Holding the
question open.

## Provenance GC predicate (documented, not built)

A reduction claim is collectable when: it has been superseded by a newer
reduction of the same source expression AND is not referenced by any
retained history query or active matview.

## Compat shim: gone

The old `expr!`/`run!`/`eval-step!` API in eval.rkt existed because
lang.rkt used its own expression representation. Now deleted.

## Lang.rkt ported to graph-eval nodes

lang.rkt now constructs graph-eval-compatible nodes directly:

- Numbers → `lit!`
- Variables → `var!` (referencing binding entities)
- Builtins (`+`, `-`, `*`, `/`) → `binop!` with string operator names
- Function calls → nested `app!` (curried: `(f x y)` → `app(app(f, x), y)`)
- `calls-pred` annotation on the outermost app for Datalog `fn-depends-on`

One representation, two uses: the same claim-graph nodes that Datalog
analyzes (dependencies, rename propagation) are the nodes graph-eval
reduces. Parse a function, render it, evaluate it, query its
dependencies — all against the same graph.

### What changed in lang.rkt

- `parse-expr!` builds `lit!`/`var!`/`binop!`/`app!` instead of custom `expr!`
- `render-expr` dispatches on `node-kind` instead of custom predicates
- `collect-app-args` walks `fn-pred` chain to reconstruct multi-arg calls
- `collect-expr-entities` walks `fn-pred`/`arg-pred` (not custom child preds)
- Datalog `contains-call` rules traverse `fn-pred` and `arg-pred`
- Builtins map `'+ → "+"` string names and register as primitives

### body-pred collision

Both eval.rkt and lang.rkt define `body-pred` for different things
(`eval/body` vs `body-pred`). Tests that need both use `ctx-ref`
directly to disambiguate.

## MCP evaluate tool

The agent loop is closed. An agent can now:

1. `parse_program` (language: "cnf") — parse functions into the graph
2. `query` — discover dependencies via Datalog
3. `rename` — rename a function, call sites update automatically
4. `evaluate` — run a function, get result as queryable claims
5. `inspect` — examine the eval-run entity, provenance, errors

The `evaluate` tool creates an eval-run entity with claims:
- `run-root` → function entity
- `run-status` → "complete" | "incomplete" | "error"
- `run-result` → result node (on success)
- `fuel-limit` / `fuel-used` → budget tracking
- `run-reason` → error message or "fuel-exhausted"
- `run-error-node` → problematic node (on failure)

Runtime failure is graph data, not just an exception. Every outcome
is a queryable fact in the same graph as the program itself.

`eval-function!` in lang.rkt does the heavy lifting: discovers all
functions with body claims, builds curried lambdas via eval-layer
predicates, creates a mutual environment with placeholder patching
(same mechanism as letrec), evaluates the call, records the run.

31 MCP tools (was 30: added `evaluate`).

## Server fixes

The compat shim deletion broke server.rkt (references to deleted
`evaluated-pred` / `result-pred`). Fixed:
- Removed dead rules from `register-builtin-rules!`
- Updated `restore-workspace!` to use eval/X ctx keys
- Fixed primitive registration (string keys, not entity IDs)
- Added lang.rkt import + `setup-lang!` in workspace init
- Added "cnf" language to `parse_program` and `render`

## Tests

15 eval tests, 23 lang tests (was 17):

- Lang 18: eval-function! single fn success, run is queryable
- Lang 19: cross-function call via eval-function! (caller(3,4) = 107)
- Lang 20: fuel exhaustion becomes queryable graph data
- Lang 21: runtime error becomes queryable graph data
- Lang 22: evaluation works after rename
- Lang 23: multiple eval runs are independent queryable entities

396 tests across all suites.

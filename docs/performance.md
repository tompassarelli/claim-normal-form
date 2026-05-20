# Performance

## Engine

The Datalog engine uses **semi-naive evaluation** with **materialized
views** and **index-aware base relation dispatch**:

- **Materialized views**: `materialize!` caches all derived facts.
  New claims delta-propagate through rules incrementally — views stay
  current without re-running the fixpoint.
- **Semi-naive fixpoint**: EDB-only rules fire once. IDB rules iterate
  with delta restriction — each iteration only considers rule variants
  where at least one IDB body atom uses new facts from the previous
  iteration.
- **Index-aware joins**: base relation lookups dispatch to hash indexes
  during joins rather than scanning all tuples.
- **Maintained supersession**: `current-claims-where` is O(matching),
  not O(all supersession claims).

## Benchmark numbers

Toy language at 200 functions (chain dependencies):

```
Dep query (cold):     ~67 ms   (full fixpoint, no cache)
Dep query (cache):    ~0 ms    (materialized view hit — 4000x faster)
Parse (incremental):  ~21 ms   (views maintained live during parse)
Dep query after parse: 0 ms    (already computed)
Rename + render 1:    < 0.1 ms (O(1))
Render all 200:       ~3 ms
```

Real codebase demo (100 functions, E12):

```
100 functions, 5 layers, 2399 objects, 1672 claims
Parse:                  37 ms
fn-depends-on (245 edges): 0.1 ms  (matview hit)
trans-dep (1655 pairs):    0.2 ms  (matview hit)
Rename:                 0.1 ms     (+ automatic matview update)
add-function!:          55 ms
modify-function!:       584 ms     (worst case: retract + reparse + rematerialize)
remove-function!:       199 ms
```

Beagle bridge (9 forms, E13):

```
565 objects, 384 claims
Parse:              2.3 ms
fn-depends-on:      0 ms    (matview hit)
trans-dep:          0 ms    (matview hit)
Materialize:        15 ms
Rename:             0.04 ms (propagates to 3 callers)
Render all 9:       0.5 ms
add-function!:      0.9 ms
modify-function!:   1.2 ms
```

Python bridge (9 forms, E14):

```
542 objects, 338 claims
Parse:              55 ms    (includes python3 subprocess)
fn-depends-on:      0 ms     (matview hit)
trans-dep:          0 ms     (matview hit)
Materialize:        8 ms
Rename:             0.03 ms  (propagates to 2 callers)
Render all 9:       0.6 ms
add-function!:      52 ms    (python3 subprocess dominates)
modify-function!:   51 ms    (python3 subprocess dominates)
```

## Honest limitations

- **Materialization cost scales with output size.** Rules producing
  O(N²) tuples (shared-dep, hub-pair) can take seconds at N=100.

- **modify-function! worst case is 584ms** at N=100 — retract all
  body claims, reparse, rematerialize affected views.

- **Dependency queries via Datalog are slower than text search for
  simple cases.** A single `grep 'function_name('` is ~0.1ms. The
  advantage is correctness (complete transitive closure, no false
  positives from string matches) and persistence (rules compose,
  matviews cache, results survive across sessions).

- **Python bridge adds ~50ms per operation** from subprocess overhead.
  In-process bridges (beagle, toy lang) don't pay this cost.

- **Benchmarks are at 50–200 functions**, not 50,000. The correctness
  advantage is structural (entity references vs string matching) and
  doesn't depend on scale. Performance at large scale is unproven.

- **History is cheap but not free.** Superseded claims stay in the
  graph. At very high churn rates, the supersession set grows and
  `current-claims-where` must filter through it.

## Reproducing

```bash
racket engine-bench.rkt    # toy language benchmarks
racket beagle-demo.rkt     # beagle bridge timings
racket python-demo.rkt     # python bridge timings
racket e15-eval.rkt        # correctness evaluation
```

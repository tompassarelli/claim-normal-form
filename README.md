# claim-normal-form-racket

Racket implementation of [Claim Normal Form](https://github.com/tompassarelli/claim-normal-form) — in-memory kernel + Datalog query engine.

## The ontology

```
Object = addressable identity

Entity = object only           (entity!)
Value  = object + literal      (value!)  — interned, canonical
Claim  = object + (l p r)      (claim!)
```

```
Entity ⊂ Object
Value  ⊂ Object
Claim  ⊂ Object

claim : Object × Object × Object → Claim
```

The fact shape is `(l p r)` — each slot can be any object. A predicate
is just an object occupying the middle position. This is not EAV renamed;
EAV defines roles inside a fact, CNF defines kinds of addressable object.

> **Object is addressability. Claim is assertion. Value is grounding.
> Entity is referent.**

## Kernel API (`cnf.rkt`)

```racket
(entity!)              ; pure referent — the thing before description
(value! "Tom")         ; canonical literal — interned (same string = same ID)
(value-object? id)     ; #t if id is a value object (use instead of truthiness)
(claim! left pred right) ; assertion connecting objects

(named! "edge")        ; sugar: entity + symbol claim
(claim-v! l p "val")   ; sugar: value + claim

(resolve-symbol "edge") ; find entity by symbol name
(resolve-value id)      ; look up literal grounding
(claims-about id)       ; claims where id is left
(claims-where #:l l #:p p #:r r)  ; filtered claim query (indexed)
```

Claim lookups are indexed by `l`, `p`, `r`, `(l,p)`, and `(p,r)`.
Constrained queries hit the appropriate index instead of scanning
all claims.

## Datalog (`datalog.rkt`)

Bottom-up naive fixpoint evaluation over the claim graph.

```racket
(require "cnf.rkt" "datalog.rkt")

;; Literals resolve automatically — no value joins needed
(query (triple (? x) name "Tom"))

;; Define derived relations
(define-rule (named-thing (? obj) (? name-val))
  (triple (? obj) (? sym) (? name-val))
  (triple (? sym) (? sym) "symbol"))

(query (named-thing (? who) (? what)))

;; Recursive rules (transitive closure)
(define-rule (path (? x) (? y))
  (triple (? x) edge-pred (? y)))
(define-rule (path (? x) (? z))
  (triple (? x) edge-pred (? y))
  (path (? y) (? z)))
```

Base relations:
- `(claim Id L P R)` — full claim with object ID
- `(triple L P R)` — convenience projection
- `(current-claim Id L P R)` — unsuperseded claims only
- `(current-triple L P R)` — unsuperseded triples only
- `(value Id Literal)` — value objects and their grounded literals
- `(object Id)` — all object IDs

## Evaluator (`eval.rkt`)

Small-step graph evaluator. Datalog finds redexes, Racket executes
primitives, claims record eval events.

```racket
(require "cnf.rkt" "datalog.rkt" "eval.rkt")

(setup-eval!)

(define add-op (named! "add"))
(register-primitive! add-op +)

(define e (expr! add-op (value! 2) (value! 3)))
(define env (entity!))
(define evs (run! env))

(eval-result (first evs))  ; => 5
```

Nested expressions work — inner results feed outer operands
automatically via Datalog derivation:

```racket
(define inner (expr! add-op (value! 1) (value! 2)))
(define outer (expr! mul-op inner (value! 4)))
(run! env)  ; evaluates inner first, then outer => 12
```

Eval events are ordinary claims — queryable like anything else:

```racket
(query (triple (? ev) (evaluated-pred) (? expr)))
(query (triple (? ev) (result-pred) (? val)))
```

## Graph layer (`graph.rkt`)

Supersession, semantic rename, dependency tracking, incremental
recompute — built on claims about claims.

```racket
(require "cnf.rkt" "datalog.rkt" "eval.rkt" "graph.rkt")

(setup-eval!)
(setup-graph!)

;; Names are claims, not identity
(define fn-1 (entity!))
(give-name! fn-1 "calculate-pay")
(render-ref fn-1)  ; => "calculate-pay"

;; Rename: one new claim, zero references changed
(rename! fn-1 "compute-pay")
(render-ref fn-1)  ; => "compute-pay"

;; Dependencies derived from graph structure, not declared
;; expr-depends-on and affected are Datalog rules over current-triple

;; Incremental recompute: change one operand, recompute only affected
(change-operand! expr-1 (right-pred) old-val new-val)
(recompute-affected! env expr-1)
;; Only downstream expressions re-evaluated; unaffected nodes untouched
;; Old eval events remain queryable as provenance
```

Run `racket demo.rkt` to see the full demonstration.

## Performance

Claim store lookups are indexed — `claims-where` with constraints
uses hash indexes rather than full scans.

Incremental recompute touches only the affected subgraph:

```
105 expressions (5-deep chain + 100 independent)
Full build:        ~4000 ms
Incremental (5):   ~400 ms   (10x faster, 100 nodes untouched)
```

Run `racket bench.rkt` to reproduce.

**Honest limitations:**
- Datalog uses naive bottom-up fixpoint — each eval step runs a full
  fixpoint pass over all derived facts. This is the performance
  bottleneck, not claim lookup.
- Indexes accelerate `claims-where` and `current-claims-where`, but
  the Datalog engine itself does not yet use them during fixpoint
  iteration.
- The incremental win comes from evaluating fewer steps (5 instead
  of 105), not from faster individual steps.

## Tests

```
racket cnf-test.rkt      # 10 kernel tests
racket datalog-test.rkt  # 9 datalog tests
racket eval-test.rkt     # 6 evaluator tests
racket demo-test.rkt     # 8 graph layer tests
```

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
(claim! left pred right) ; assertion connecting objects

(named! "edge")        ; sugar: entity + symbol claim
(claim-v! l p "val")   ; sugar: value + claim

(resolve-symbol "edge") ; find entity by symbol name
(resolve-value id)      ; look up literal grounding
(claims-about id)       ; claims where id is left
(claims-where #:l l #:p p #:r r)  ; filtered claim query
```

## Datalog (`datalog.rkt`)

Bottom-up fixpoint evaluation over the claim graph.

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

## Tests

```
racket cnf-test.rkt      # 9 kernel tests
racket datalog-test.rkt  # 9 datalog tests
racket eval-test.rkt     # 6 evaluator tests
```

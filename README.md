# claim-normal-form

Software should not primarily live as text files. It should live as a claim graph where code, data, names, history, dependencies, runtime events, errors, patches, and explanations are all first-class addressable objects.

A data-modeling normal form where everything is objects and claims.
In-memory Racket kernel + Datalog query engine.

See [specification.md](specification.md) for the full spec.

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

All state lives in an opaque `cnf-ctx` struct. Multiple independent
graphs via `parameterize`:

```racket
(define ctx-a (make-cnf-ctx))
(define ctx-b (make-cnf-ctx))

(parameterize ([current-ctx ctx-a])
  (entity!)   ; goes to ctx-a
  (value! 42) ; goes to ctx-a
  ...)
```

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

## Schema layer (`schema.rkt`)

Ergonomic data modeling — CRUD over claims without touching the
raw kernel API.

```racket
(require "cnf.rkt" "datalog.rkt" "schema.rkt")

(setup-schema!)

;; Predicates are just objects — batch-create them
(define-predicates name email status assigned-to)

;; Create entities with properties
(define alice (entity/claims [name "Alice"] [email "alice@co.com"]))
(define bob   (entity/claims [name "Bob"]   [email "bob@co.com"]))

(define task-1 (entity/claims [name "Fix login bug"] [status "open"]))
(link! task-1 assigned-to alice)

;; Lookup
(lookup alice name)            ; => "Alice"
(lookup task-1 assigned-to)    ; => alice's entity ID
(find-by status "open")        ; => (list task-1)
(find-by assigned-to alice)    ; => (list task-1)

;; Update (supersession — old values preserved as history)
(update! alice email "alice@newco.com")
(lookup alice email)            ; => "alice@newco.com"

;; Retract / unlink
(retract! alice email)
(unlink! task-1 assigned-to alice)
```

No tables, no schema migrations, no foreign key declarations.
Predicates are objects. Relationships are claims. History is free.

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

## Lang layer (`lang.rkt`)

Text as projection of the claim graph. Parse a tiny functional
language into claims. Render claims back to text. Rename by claim,
edit by supersession — text updates automatically.

```racket
(require "cnf.rkt" "datalog.rkt" "eval.rkt" "graph.rkt" "lang.rkt")

(reset-store!)
(setup-eval!)
(setup-graph!)
(setup-lang!)

;; Parse source text into claims
(define fns (parse-program! "
(defn base-rate [hours level]
  (* hours level))

(defn total-pay [hours level]
  (+ (base-rate hours level) 100))
"))

;; Render claims back to text (round-trips exactly)
(render-program fns)

;; Rename: 1 claim, 0 find-replace
(rename! (first fns) "hourly-rate")
(render-program fns)
;; => total-pay's call site now says "hourly-rate" automatically

;; Change operator via supersession
(define body (get-body (first fns)))
(define builtins (ctx-ref 'builtins))
(change-operand! body (op-pred)
  (hash-ref builtins '*)
  (hash-ref builtins '+))
(render-program fns)  ;; => hourly-rate body now says (+ hours level)

;; Query structural dependencies (derived by Datalog, not declared)
(query (fn-depends-on (? caller) (? callee)))
;; => total-pay depends on hourly-rate
```

Run `racket lang-demo.rkt` for the full thesis demonstration.

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
racket cnf-test.rkt      # 11 kernel tests
racket datalog-test.rkt  # 9 datalog tests
racket eval-test.rkt     # 6 evaluator tests
racket demo-test.rkt     # 8 graph layer tests
racket schema-test.rkt   # 10 schema layer tests
racket lang-test.rkt     # 8 lang layer tests
```

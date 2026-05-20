# API Reference

## Kernel (`cnf.rkt`)

The kernel provides objects, claims, and indexed lookups. All state
lives in an opaque `cnf-ctx` struct. Multiple independent graphs via
`parameterize`.

```racket
(entity!)                    ; pure referent — identity before description
(value! "Tom")               ; canonical literal — interned (same string = same ID)
(value-object? id)           ; #t if id is a value object
(claim! left pred right)     ; assertion connecting objects — returns claim ID

(named! "edge")              ; sugar: entity + symbol claim
(claim-v! l p "val")         ; sugar: value + claim

(resolve-symbol "edge")      ; find entity by symbol name
(resolve-value id)           ; look up literal grounding
(claims-about id)            ; claims where id is left
(claims-where #:l l #:p p #:r r)  ; filtered claim query (indexed)
```

Claim lookups are indexed by `l`, `p`, `r`, `(l,p)`, and `(p,r)`.
Constrained queries hit the appropriate index.

```racket
(define ctx-a (make-cnf-ctx))
(define ctx-b (make-cnf-ctx))

(parameterize ([current-ctx ctx-a])
  (entity!)   ; goes to ctx-a
  (value! 42) ; goes to ctx-a
  ...)
```

## Datalog (`datalog.rkt`)

Semi-naive bottom-up evaluation over the claim graph.

```racket
(require "cnf.rkt" "datalog.rkt")

;; Literals resolve automatically
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

Materialized views: `(materialize!)` caches all derived facts. New
claims delta-propagate through rules incrementally.

## Evaluator (`eval.rkt`)

Small-step graph evaluator. Datalog finds redexes, Racket executes
primitives, claims record eval events.

```racket
(setup-eval!)

(define add-op (named! "add"))
(register-primitive! add-op +)

(define e (expr! add-op (value! 2) (value! 3)))
(define env (entity!))
(define evs (run! env))
(eval-result (first evs))  ; => 5
```

Eval events are ordinary claims — queryable like anything else.

## Schema layer (`schema.rkt`)

Ergonomic data modeling over claims.

```racket
(setup-schema!)

(define-predicates name email status assigned-to)

(define alice (entity/claims [name "Alice"] [email "alice@co.com"]))
(define task-1 (entity/claims [name "Fix login bug"] [status "open"]))
(link! task-1 assigned-to alice)

(lookup alice name)            ; => "Alice"
(find-by status "open")        ; => (list task-1)

(update! alice email "alice@newco.com")   ; supersession — old value preserved
(retract! alice email)
(unlink! task-1 assigned-to alice)
```

Predicates are objects. Relationships are claims. Structural evolution
happens at the graph/modeling layer, not through table migrations.

## Graph layer (`graph.rkt`)

Supersession, semantic rename, dependency tracking, incremental
recompute.

```racket
(setup-eval!)
(setup-graph!)

(define fn-1 (entity!))
(give-name! fn-1 "calculate-pay")
(render-ref fn-1)  ; => "calculate-pay"

(rename! fn-1 "compute-pay")
(render-ref fn-1)  ; => "compute-pay"
;; All references to fn-1 now render as "compute-pay"
```

## Lang layer (`lang.rkt`)

Text as projection of the claim graph. Parse a toy functional
language into claims, render back to text. The toy language round-trips
exactly.

```racket
(setup-lang!)

(define fns (parse-program! "
(defn base-rate [hours level]
  (* hours level))

(defn total-pay [hours level]
  (+ (base-rate hours level) 100))
"))

(render-program fns)

(rename! (first fns) "hourly-rate")
(render-program fns)
;; => total-pay's call site now says "hourly-rate"

(query (fn-depends-on (? caller) (? callee)))
;; => total-pay depends on hourly-rate
```

## Transactions

Every claim belongs to a transaction. Implicit (one per claim) or
explicit (`begin-tx!`/`commit-tx!`).

```racket
(begin-tx!)
;; ... multiple claims ...
(commit-tx!)   ; atomic — hooks deferred to commit, rollback on error

(claims-since tx-seq)          ; claims after a tx
(claims-visible-as-of tx-seq)  ; temporal query
(all-txs)                      ; sorted tx list
```

Agent identity: `(set-agent! "analyst")` attributes all subsequent
claims. Survives serialization.

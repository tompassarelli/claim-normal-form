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

Semi-naive bottom-up evaluation over the claim graph.

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

## MCP Server (`mcp-server.rkt`)

30 tools over JSON-RPC 2.0 / stdio. Claude Code connects and operates
on the claim graph directly.

### Quick start

```bash
# Prerequisites: Racket 8.x
racket --version

# Stdio mode (Claude Code connects via MCP)
racket mcp-server.rkt

# Daemon mode (TCP, multi-client, auto-restores from checkpoint)
racket mcp-server.rkt --daemon 7888

# Bridge mode (stdio proxy to running daemon)
racket mcp-server.rkt --connect 7888
```

### Claude Code configuration

Add to your MCP settings (`.claude/settings.json`):

```json
{
  "mcpServers": {
    "cnf": {
      "command": "racket",
      "args": ["/path/to/cnf-racket/mcp-server.rkt"]
    }
  }
}
```

For daemon mode (shared state across sessions):

```json
{
  "mcpServers": {
    "cnf": {
      "command": "racket",
      "args": ["/path/to/cnf-racket/mcp-server.rkt", "--connect", "7888"]
    }
  }
}
```

### Tool reference

**Core (6 tools):**
`reset`, `create_entity`, `create_named`, `create_value`, `claim`, `status`

**Query (6 tools):**
`query`, `inspect`, `resolve_symbol`, `claims_where`, `lookup`, `find_by`

**Rules (3 tools):**
`define_rule`, `list_rules`, `supersede_rule`

**Schema (2 tools):**
`define_predicates`, `update`

**Program (6 tools):**
`parse_program`, `render`, `rename`, `add_function`, `remove_function`,
`modify_function`

**Batch (1 tool):**
`batch` — multiple operations in one call, with optional `atomic: true`
for all-or-nothing transactions

**Persistence (2 tools):**
`checkpoint`, `restore`

**Transactions (3 tools):**
`tx_log`, `current_tx_seq`, `set_agent`

### Key workflows

**Parse and query:**
```
parse_program(source) → fn IDs + schema
query("(fn-depends-on (? caller) (? callee))")
```

**Define custom rules:**
```
define_rule(head: "(trans-dep (? f) (? g))", body: "(fn-depends-on (? f) (? g))")
define_rule(head: "(trans-dep (? f) (? g))", body: "(fn-depends-on (? f) (? m)) (trans-dep (? m) (? g))")
query("(trans-dep some-function (? dep))")
```

**Incremental edit (no reparse):**
```
add_function(source: "(defn new-fn (x y) (+ (existing-fn x y) 1))")
modify_function(name: "old-fn", source: "(defn old-fn (x y) (* x y))")
remove_function(name: "deprecated-fn")
# All rules and matviews auto-update through the mutations
```

**Cross-session persistence:**
```
checkpoint()   # save graph to ~/.cnf/checkpoint.json
# ... new session ...
restore()      # rebuild full graph + rules + matviews
```

**Multi-agent collaboration:**
```
set_agent(name: "structural-analyst")
# ... define rules, query ...
checkpoint()

# Agent B:
restore()
set_agent(name: "quality-checker")
list_rules()   # see Agent A's rules
# ... define rules composing Agent A's derived relations ...
tx_log()       # see interleaved agent transactions
```

### Daemon mode

The daemon uses MVCC (multi-version concurrency control). Readers get
a snapshot of the committed state and run without any lock — multiple
queries execute concurrently with zero contention. Writers serialize
and publish a new snapshot on commit. Multiple Claude Code instances
can connect via bridge mode and share the same claim graph.

```bash
# Terminal 1: start daemon
racket mcp-server.rkt --daemon 7888

# Terminal 2: agent A
racket mcp-server.rkt --connect 7888

# Terminal 3: agent B
racket mcp-server.rkt --connect 7888
```

## Performance

The Datalog engine uses **semi-naive evaluation** with
**materialized views** and **index-aware base relation dispatch**:

- **Materialized views**: `materialize!` caches all derived facts.
  New claims delta-propagate through rules incrementally — views
  stay current without re-running the fixpoint. Supersession
  invalidates affected views; next query recomputes and re-caches.
- **Semi-naive fixpoint**: EDB-only rules fire once. IDB rules
  iterate with delta restriction — each iteration only considers
  rule variants where at least one IDB body atom uses new facts
  from the previous iteration. Avoids redundant re-derivation.
- **Index-aware joins**: base relation lookups (`current-triple`,
  `triple`, `value`, etc.) dispatch to hash indexes during joins
  rather than scanning all tuples.
- **Maintained supersession**: `current-claims-where` is O(matching)
  not O(all supersession claims).

Agent-oriented operations at scale:

```
200 functions (chain dependencies)
Dep query (cold):     ~67 ms   (full fixpoint, no cache)
Dep query (cache):    ~0 ms    (materialized view hit — 4000x faster)
Parse (incremental):  ~21 ms   (views maintained live during parse)
Dep query after parse: 0 ms    (already computed — beats grep)
Rename + render 1:    < 0.1 ms (O(1))
Render all 200:       ~3 ms
Text grep:            ~0.1 ms
```

Run `racket engine-bench.rkt` to reproduce.

At scale (100-function financial analytics codebase, E12):

```
100 functions, 5 layers, 2399 objects, 1672 claims
Parse:                  37 ms
fn-depends-on (245 edges): 0.1 ms  (matview hit)
trans-dep (1655 pairs):    0.2 ms  (matview hit)
Rename:                 0.1 ms     (+ automatic matview update)
add-function! (incremental): 55 ms
modify-function!:       584 ms     (retract + reparse + rematerialize)
remove-function!:       199 ms
```

**Honest limitations:**
- Materialization cost scales with output size. Rules producing O(N²)
  tuples (shared-dep, hub-pair) can take seconds at N=100.
- Incremental parse mutations trigger matview recomputation for
  affected relations — modify-function! at 584ms is the worst case.
- Dependency queries via Datalog are slower than grep for simple
  cases. The structural advantage is correctness (guaranteed complete
  transitive closure) and persistence (rules compose, matviews cache).

## Tests

88 tests across 8 files:

```
racket cnf-test.rkt      # 11 kernel tests
racket datalog-test.rkt  # 16 datalog tests (incl. incremental rule add/supersede)
racket eval-test.rkt     # 6 evaluator tests
racket demo-test.rkt     # 8 graph layer tests
racket schema-test.rkt   # 10 schema layer tests
racket lang-test.rkt     # 15 lang tests (incl. incremental parse)
racket tx-test.rkt       # 16 transaction tests (incl. agent identity)
racket rwlock-test.rkt   # 6 read/write lock tests
```

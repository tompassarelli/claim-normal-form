# Language Bridges

CNF does not require abandoning text. Text is parsed into the graph
and rendered back out. The graph becomes the semantic working copy;
text remains the portable artifact.

## Beagle (`beagle-lang.rkt`)

Bridge from [beagle](https://github.com/tompassarelli/beagle) (typed
Lisp, 50+ forms, 6 emit targets) to the claim graph. Beagle's existing
parser produces AST structs; the bridge walks them into entities and
claims. Beagle doesn't change.

```racket
(require "cnf.rkt" "datalog.rkt" "eval.rkt" "graph.rkt" "beagle-lang.rkt")

(reset-store!)
(setup-eval!)
(setup-graph!)
(setup-beagle-lang!)

(define fns (parse-beagle-program! "
(defrecord Trade [(symbol : String) (qty : Int) (price : Float)])

(defn trade-value [(t : Trade)] : Float
  (* (trade-qty t) (trade-price t)))

(defn portfolio-total [(p : Portfolio)] : Float
  (reduce + 0.0 (mapv trade-value (portfolio-trades p))))
"))

(query (fn-depends-on (? caller) (? callee)))
;; => portfolio-total -> trade-value

(rename! (first fns) "compute-trade-value")
(render-beagle-program fns)
;; => portfolio-total's call site says "compute-trade-value"

(add-beagle-function! "(defn net-value [(t : Trade)] : Float
  (- (compute-trade-value t) 0.01))")
```

30+ form types handled: defn, defrecord, def, call, if, if-let, let,
fn, match, cond, when, do, for, loop, try, vec, map, method-call,
kw-access, and more. 18 predicates.

Run `racket beagle-demo.rkt` for the full demonstration.

## Python (`python-lang.rkt`)

Python source → `python3` subprocess (AST → JSON) → Racket bridge →
claim graph.

```racket
(require "cnf.rkt" "datalog.rkt" "eval.rkt" "graph.rkt" "python-lang.rkt")

(reset-store!)
(setup-eval!)
(setup-graph!)
(setup-python-lang!)

(define fns (parse-python-program! "
def trade_value(trade: Trade) -> float:
    return trade.quantity * trade.price

def portfolio_value(portfolio: Portfolio) -> float:
    total = sum(trade_value(t) for t in portfolio.trades)
    return total + portfolio.cash
"))

(query (py-fn-depends-on (? caller) (? callee)))
;; => portfolio_value -> trade_value

(rename! (first fns) "compute_trade_value")
(render-python-program fns)

(add-python-function! "def weighted(p: Portfolio, w: float) -> float:
    return portfolio_value(p) * w
")
```

30+ AST node types: functions, classes, decorators, type annotations,
async, comprehensions, control flow, match statements. 14 predicates.

The Python bridge renders structural summaries, not runnable source.
Function signatures are accurate (types, decorators, async). Body
rendering is approximate — assignments, comprehensions, and control
flow condense. The claim graph captures structure and dependencies;
for exact source, use the original text.

Run `racket python-demo.rkt` for the full demonstration.

## Adding a new language

The pattern:

1. Write a parser that produces some AST (in-process or subprocess)
2. Walk the AST, creating entities (`entity!`, `give-name!`) and
   claims (`claim!`) using predicates for your language's concepts
3. Define Datalog rules for derived relations (e.g. `fn-depends-on`)
4. Implement `add-*-function!`, `remove-*-function!`, `modify-*-function!`
   for incremental operations
5. Write a renderer that reconstructs text from claims

Steps 1 and 2 are the real work — understanding your language's binding
and scoping semantics well enough to map them into entity references.
Steps 3–5 follow the same pattern as the existing bridges.

Once mapped, dependency queries, rename propagation, history, MCP tools,
materialized views, persistence, and multi-agent collaboration are
shared infrastructure. You don't reimplement any of that.

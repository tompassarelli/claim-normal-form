# E14: Python Bridge

## Setup

9-form Python program: 2 dataclass definitions, 7 typed functions with
dependencies. Same financial analytics domain as E13 (beagle) for direct
comparison. Source parsed via `python3` subprocess → JSON AST → CNF claims.

## Results

```
Parse:                  55 ms   (includes python3 subprocess)
Objects:                542
Claims:                 338
py-fn-depends-on:       7 edges, 0 ms (matview hit)
py-trans-dep:           15 pairs, 0 ms (matview hit)
Materialize:            8 ms
Rename:                 0.03 ms (propagates to 2 callers)
Render all 9:           0.6 ms
add-python-function!:   52 ms   (includes python3 subprocess)
modify-python-function!: 51 ms  (includes python3 subprocess)
```

## Comparison with beagle bridge (E13)

| Metric | Beagle (E13) | Python (E14) | Notes |
|--------|-------------|-------------|-------|
| Parse | 2.3 ms | 55 ms | Python pays subprocess cost |
| Objects | 565 | 542 | Comparable |
| Claims | 384 | 338 | Comparable |
| Direct deps | 7 | 7 | Same domain, same structure |
| Trans deps | 15 | 15 | Same domain, same structure |
| Materialize | 15 ms | 8 ms | Fewer claims = faster |
| Rename | 0.04 ms | 0.03 ms | Both O(1) — one claim |
| Render | 0.5 ms | 0.6 ms | Both O(n forms) |
| Incremental add | 0.9 ms | 52 ms | Python pays subprocess |
| Incremental modify | 1.2 ms | 51 ms | Python pays subprocess |

The 50ms overhead on Python operations is entirely the `python3` subprocess
for AST parsing. The claim graph operations (query, rename, render,
materialize) are identical — same engine, same speed.

## What works

1. **Dependency discovery**: `py-fn-depends-on` correctly identifies all
   7 direct edges. Transitive closure via custom rules gives 15 pairs.

2. **Rename propagation**: Renaming `trade_value` → `compute_trade_value`
   auto-updates callers (`trade_pnl`, `portfolio_value`) through entity
   references. Zero find-replace.

3. **Incremental mutations**: `add-python-function!` and
   `modify-python-function!` work correctly. Dependencies auto-update:
   after adding `weighted_pnl` (calls `portfolio_pnl`) and renaming
   `compute_trade_value` → `net_trade_value`, the graph shows 8 edges
   with the new function included.

4. **Classes**: `Trade` and `Portfolio` parsed as class entities with
   `py-form-kind "class"`. Methods are nested function entities.

5. **Type annotations**: Preserved as claims. `trade: Trade`, `-> float`,
   decorator `@dataclass` all survive round-trip.

## Rendering limitations

Python rendering is structural, not syntactic. The renderer reconstructs
from claims — function signatures are accurate (types, decorators,
async), but body rendering is approximate. Assignments show `...`,
comprehensions simplify, control flow condenses. This is by design:
the claim graph captures structure and dependencies, not syntax.

For exact source reconstruction, use the original text. The render is
for verification and diff — "what did the rename change?" — not for
producing runnable Python.

## Language-agnostic MCP server

The MCP server auto-detects language from source syntax:
- `def`/`class`/`import` → Python bridge
- Everything else → beagle bridge

All 30 MCP tools work with both languages. A single agent session can
parse Python and beagle source, query cross-language dependencies
(through shared Datalog rules), and apply mutations to either.

MCP Resources (new capability) push structured summaries into agent
context: `cnf://summary`, `cnf://dependencies`, `cnf://functions`,
`cnf://rules`. This is the architectural shift from tool-call
request/response to context injection.

## Reproducing

```bash
# Prerequisites: Racket 8.x, Python 3.x
racket python-demo.rkt
racket python-lang-test.rkt  # 15 tests
```

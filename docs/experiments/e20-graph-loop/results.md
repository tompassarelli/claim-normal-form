# E20: Graph-Native Agent Loop

**Date:** 2026-05-21

## Question

Does the closed loop give an agent leverage it doesn't have through files?

## Setup

5-function payroll program with cross-dependencies:

```
base-rate(hours, rate) = hours * rate
overtime(hours, rate)  = base-rate(hours, rate) * 2
total-pay(base, extra) = base + extra
tax-amount(income, pct) = (income * pct) / 100
after-tax(income, pct)  = income - tax-amount(income, pct)
```

Dependencies: overtime -> base-rate, after-tax -> tax-amount.

10-step task exercising the full agent loop: parse, query, evaluate,
rename, re-evaluate, add function, evaluate across boundaries, break
with division-by-zero, diagnose error, fix, re-evaluate.

Run: `racket experiments/e20-graph-loop.rkt`

## Results

All 10 steps succeed. 6 eval runs recorded in the graph. Every
evaluation (success and failure) is a queryable entity.

| Step | Operation | Graph result |
|------|-----------|-------------|
| 1 | Parse 5 functions | 317 objects, 177 claims |
| 2 | Query deps | overtime->base-rate, after-tax->tax-amount |
| 3 | Eval base-rate(40,25) | 1000, 9 fuel |
| 4 | Eval after-tax(1500,20) | 1200, 19 fuel |
| 5 | Rename base-rate -> hourly-rate | overtime call site auto-updated |
| 6 | Eval overtime(10,25) post-rename | 500 (correct, semantics preserved) |
| 7 | Add discounted-pay | deps auto-derived: after-tax |
| 8 | Eval discounted-pay(1500,100) | 1100 (crosses 3 function boundaries) |
| 9 | Break: divide by zero | status=error, reason="/: division by zero" |
| 10 | Fix and re-eval | 1100 (correct) |

## Graph vs text comparison

### Where the graph wins

**Dependency queries** (Step 2). Graph: one Datalog query, correct,
transitive. Text: grep for function names, finds string matches not
calls, misses transitive deps.

**Rename** (Step 5). Graph: one operation, all call sites update
because names are projections of entity references. Text:
find-and-replace, risks false positives in strings and comments.

**Error diagnosis** (Step 9). Graph: `run-status = "error"`,
`run-reason = "/: division by zero"`, queryable as claims. The
agent can ask "which runs failed?" and get structured answers.
Text: parse an error message from stderr.

**Execution history** (Summary). The graph retains all 6 eval runs
as queryable entities. The agent can ask "what happened to
discounted-pay over time?" and get: complete -> error -> complete.
Text: logs, if they exist.

**Incremental mutation** (Steps 7, 9, 10). Adding, modifying, and
evaluating functions are all graph operations. Dependencies
auto-derive via matview. Text: edit files, re-run everything,
re-analyze from scratch.

### Where it's a tie

**Simple evaluation** (Steps 3, 4, 8). Both agents can evaluate;
the graph advantage is recording, not computing.

**Simple fixes** (Step 10). Both edit and re-run. The delta is
that the graph retains the error as history.

**Parse** (Step 1). Same effort. Different representation.

### What this demonstrates

The agent loop is:

```
parse -> query -> rename -> evaluate -> break -> diagnose -> fix -> re-evaluate
```

Every step operates against the same claim graph. Source text is a
projection (rendering), not the authority. The graph is:

- **Source**: claims define the program
- **Semantic index**: Datalog derives dependencies
- **Runtime**: graph-eval reduces expressions
- **History**: eval-run entities record outcomes

This is not "a language with a nice API." It is a substrate where
program, analysis, execution, and history are the same artifact.

## What this does NOT demonstrate

- **Scale**: 5 functions, not 500. The graph advantages (transitive
  deps, rename propagation) compound with scale; this demo doesn't
  prove that.

- **Agent autonomy**: the steps are scripted, not agent-initiated.
  A real agent race would show whether agents actually use the
  graph tools when they have them.

- **Multi-agent**: single agent, sequential. The MVCC infrastructure
  exists for concurrent access but isn't tested here.

- **Real language**: the toy lang has 4 builtins and 2-arg functions.
  The beagle and python bridges parse real languages but can't
  evaluate.

## What's next

The honest next step is a real agent race: same task, two Claude
agents, one with files + grep, one with MCP tools. The task must
force structural reasoning that text search can't do reliably.

The graph loop exists. The question is whether agents use it well.

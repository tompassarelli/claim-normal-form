# How CNF works

## The problem with text

A function in a text file:

```python
def add(x, y):
    return x + y
```

To rename `add` → `sum_two`, you grep every file for the string `"add"`,
hope you don't hit a variable called `added` or a comment saying "add
tests later", and do a find-replace. To find what calls `add`, you grep
again. To find what `add` transitively affects, you write a script. Every
operation starts from scratch. Nothing remembers anything.

Text encodes identity as string coincidence. Two things are "the same"
because they happen to contain the same characters in the same position.

## The claim graph

CNF encodes identity as entity reference. Here's the same function:

```
Entity  e1                                  # the function — a stable identity
Entity  e2                                  # param x
Entity  e3                                  # param y
Entity  e5                                  # the return statement
Entity  e6                                  # the (x + y) expression

Claim   e1  name          "add"             # e1 is named "add"
Claim   e1  form-kind     "function"        # e1 is a function
Claim   e1  has-param     e2                # e1 has param e2
Claim   e1  has-param     e3                # e1 has param e3
Claim   e2  name          "x"
Claim   e2  position      0
Claim   e3  name          "y"
Claim   e3  position      1
Claim   e1  body          e4                # function body
Claim   e5  expr-kind     "return"
Claim   e6  expr-kind     "binop:+"
Claim   e6  has-child     e2                # left operand → the x entity
Claim   e6  has-child     e3                # right operand → the y entity
```

Three things to notice:

1. **`x` in the body is not the string `"x"`**. It's a reference to
   entity `e2`. The string `"x"` is just a name claim on that entity.

2. **Names are claims, not identity.** The function "is" `e1`. The name
   `"add"` is something we *say about* `e1`. Changing what we say
   doesn't change what it is.

3. **Everything is an object.** The function, its params, its body, the
   `+` operation — all addressable entities with claims about them.

## Rename: one claim, zero find-replace

To rename param `x` → `a`:

```
Old:  Claim  e2  name  "x"     ← superseded
New:  Claim  e2  name  "a"     ← current
```

One new claim. The old claim is superseded, not deleted — it's history.
Every place that references `e2` (the param list, the `+` expression)
now renders as `"a"` because they point at the entity, not the string.

```
Before: def add(x, y): return x + y
After:  def add(a, y): return a + y
```

This works at the function level too. If another function calls `add`:

```
Claim  other-body  calls  e1     # points to add's ENTITY, not its name
```

Rename `add` → `sum_two`: one claim on `e1`. The caller still points at
`e1`, which now renders as `"sum_two"`. No grep. No find-replace. No
missed references.

## Dependencies: derived, not declared

Given two functions where `total` calls `add`:

```
Claim  total  form-kind     "function"
Claim  total  body          total-body
Claim  expr7  calls         e1              # expr7 (inside total) calls add
Claim  add    form-kind     "function"
```

A Datalog rule derives the dependency:

```
fn-depends-on(?caller, ?callee) :-
    form-kind(?caller, "function"),
    body(?caller, ?body),
    contains-call(?body, ?callee),    # transitive walk through has-child
    form-kind(?callee, "function").
```

This runs once and the result is cached (materialized view). Query it
any time for free:

```
fn-depends-on(total, add)     # ← derived fact, 0ms lookup
```

Add a function, remove a function, rename — the materialized view
auto-updates through delta propagation. No re-analysis needed.

## Transitive closure: one more rule

Text tools can't easily answer "what does `main` transitively depend
on?" CNF can, with one additional rule:

```
trans-dep(?f, ?g) :- fn-depends-on(?f, ?g).
trans-dep(?f, ?g) :- fn-depends-on(?f, ?m), trans-dep(?m, ?g).
```

Materialized and cached. At 100 functions: 1655 transitive pairs,
query time 0ms.

## Incremental mutation

Text approach: edit the file, reparse everything, recompute everything.

CNF approach: mutate specific claims, let hooks propagate.

```
add-function!    → parse one function into claims, matview auto-updates
remove-function! → supersede that function's claims, derived facts retract
modify-function! → retract old body claims, parse new body reusing the
                   entity (so references from other functions still work)
```

After any mutation, `fn-depends-on` and `trans-dep` reflect the new
state. No full reparse. No re-analysis.

## History is free

Every claim that gets superseded stays in the graph:

```
Claim  e1  name  "add"        # superseded at tx 5
Claim  e1  name  "sum_two"    # current (tx 5)
```

"What was this function called before?" is a query, not an
archaeological expedition through git blame. Temporal queries
(`claims-visible-as-of`) show the graph at any point in time.

## Why this matters for AI agents

An AI agent working with text files re-derives understanding every
session. Parse the code, figure out what calls what, build a mental
model — then throw it all away.

An AI agent working with CNF:
- **Parses once**, queries forever (materialized views)
- **Renames in O(1)**, not O(files)
- **Defines rules** that persist across sessions (Datalog rules are claims)
- **Composes rules** — one agent's `fn-depends-on` is another agent's
  building block for `trans-dep` or `high-impact`
- **Shares understanding** — multiple agents on the same claim graph,
  each seeing the other's derived facts

The claim graph is the shared substrate that text files can't be.

## The language-agnostic pattern

CNF doesn't care what language your code is in. The pattern:

1. **Parse** source (however your language works) into AST
2. **Walk** the AST, creating entities and claims
3. **Done.** You get structural analysis, rename propagation, dependency
   queries, materialized views, incremental mutations, persistence,
   multi-agent collaboration — all for free.

Two bridges exist today:
- **Beagle** (typed Lisp) — in-process parser, ~1ms to parse 9 functions
- **Python** — subprocess parser, ~55ms (50ms subprocess overhead)

Post-parse, both are identical. Same engine, same speed, same
capabilities. Adding a third language means writing one file.

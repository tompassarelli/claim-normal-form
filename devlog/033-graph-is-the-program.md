# 033: The graph is the program

## The shift

CNF has been a semantic index — programs are parsed into claims,
agents query the graph, then write normal Python files. The graph
mirrors the code. The code is still the source of truth.

The bigger idea: the graph IS the program. No source files. Agents
construct program shapes as claims. A runtime engine evaluates the
graph directly. Files become projections, not sources.

This is closer to Smalltalk's image or Unison's content-addressed
code database than to a traditional semantic index.

## Architecture: three layers, one graph

### 1. Canonical claim store

The source of truth. Not files. Not AST JSON. Claims.

```
#42 kind "call"
#42 fn #17
#42 arg #99
```

### 2. Datalog-derived semantic layer

Rules derive meaning from the claims:

```
(calls ?caller ?callee)
(depends-on ?a ?b)
(expr-type ?expr ?t)
(invalid-node ?node ?reason)
(reachable ?entry ?node)
```

This is where agents get superpowers. Already works in CNF.

### 3. Execution layer

A small evaluator walks the claim graph and reduces terms.
Not Datalog — graph reduction with provenance.

Pure evaluation happens internally. Effects are boundary claims:

```
#99 kind "effect"
#99 effect-kind "print"
#99 effect-value "hello"
```

## The core calculus

Minimal node types:

- `literal` — numbers, strings, booleans
- `var` — reference to a binding (by entity ID, not string)
- `lambda` — param binding + body
- `apply` — function + argument
- `binop` — arithmetic/logic operations
- `let` — bind a value to a name in a body

Later: `record`, `match`, `effect`, `if`.

## Key design decisions

**Provenance-preserving reduction.** Don't overwrite the original
term. Assert a new result node plus a reduction edge:

```
#1 kind "apply"           ;; original term
#7 kind "literal"         ;; computed result
#7 value 6
#8 kind "reduction"       ;; provenance
#8 from #1
#8 to #7
#8 rule "beta+binop"
```

Datalog can then query: what did this reduce to? By which rule?
What intermediate terms existed? The graph remembers its own
computation.

**Environment-based evaluation.** Use closures and environments,
not naive substitution. Avoids capture/shadowing complexity.

**Structural bindings.** Variables reference binding entities by ID,
not by string name. Names are presentation, bindings are structure.

```
#2 param #9
#9 kind "binding"
#9 name "x"
#5 kind "var"
#5 binding #9
```

## The victory condition

> Construct and run a program that never existed as a source file.

The first proof: `((lambda (x) (+ x 1)) 5)` represented as claims,
evaluated by graph reduction, result `6` as a new claim with
provenance linking it to the original term. No parser. No files.
No text.

## The slogan

Not "Datalog all the way down." Instead:

> Claims all the way down. Datalog for derived truth.
> A reducer for execution. Files are projections.

The graph is the substrate. Datalog is one intelligence that lives
on it. Execution is another. Multiple calculi, one graph.

## What this means for the project

The research question is no longer "can agents code better with a
semantic index?" It's:

> What happens when agents directly mutate the program's semantic
> substrate instead of editing text?

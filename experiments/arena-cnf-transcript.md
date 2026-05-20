# CNF Arena Transcript

Source program: `/home/tom/code/cnf-racket/experiments/arena-program.txt`
20 functions in a linear-algebra-style DSL.

---

## Step 1: Parse the program into the claim graph

**Tool:** `mcp__cnf__reset` -- cleared workspace.
**Tool:** `mcp__cnf__parse_program` -- parsed all 20 functions.

Result: 503 objects, 331 claims, 11 built-in rules.

Function entity IDs:
| ID  | Name               |
|-----|--------------------|
| 56  | distance           |
| 84  | normalize          |
| 104 | dot                |
| 128 | scale              |
| 145 | translate          |
| 162 | transform          |
| 186 | reflect            |
| 206 | midpoint           |
| 226 | lerp               |
| 252 | project            |
| 276 | reject             |
| 296 | basis-x            |
| 312 | basis-y            |
| 332 | decompose          |
| 356 | recompose          |
| 388 | apply-transform    |
| 412 | invert-transform   |
| 436 | compose-transforms |
| 456 | chain              |
| 480 | pipeline           |

---

## Step 2: Discover the dependency structure

### Schema discovery

Inspected entities to identify the claim graph predicates:

| Predicate ID | Name      | Meaning                            |
|--------------|-----------|------------------------------------|
| 1            | symbol    | Entity's symbol name               |
| 4            | op        | Operator of an expression          |
| 7            | left      | Left sub-expression                |
| 10           | right     | Right sub-expression               |
| 22           | name      | Function name                      |
| 28           | has-param | Function parameter                 |
| 34           | body      | Function body expression           |
| 37           | calls     | Call-site references a function    |

### Datalog rules defined

1. **sub-expr** -- direct child (left or right) of an expression node:
   - `(sub-expr ?parent ?child) :- (current-triple ?parent "7" ?child)`
   - `(sub-expr ?parent ?child) :- (current-triple ?parent "10" ?child)`

2. **contains** -- transitive closure of sub-expr:
   - `(contains ?root ?desc) :- (sub-expr ?root ?desc)`
   - `(contains ?root ?desc) :- (contains ?root ?mid) (sub-expr ?mid ?desc)`

3. **fn-calls** -- function A directly calls function B (anywhere in body tree):
   - `(fn-calls ?caller ?callee) :- (current-triple ?caller "34" ?body) (current-triple ?body "37" ?callee)`
   - `(fn-calls ?caller ?callee) :- (current-triple ?caller "34" ?body) (contains ?body ?node) (current-triple ?node "37" ?callee)`

### Full direct call graph

Query: `(fn-calls (? caller) (? callee))`

| Caller             | Callees                              |
|--------------------|--------------------------------------|
| normalize          | distance                             |
| transform          | translate, scale, normalize          |
| reflect            | scale                                |
| midpoint           | scale                                |
| lerp               | scale                                |
| project            | dot, scale                           |
| reject             | project                              |
| basis-x            | normalize                            |
| basis-y            | normalize, reject                    |
| decompose          | project, reject                      |
| recompose          | basis-x, basis-y, scale              |
| apply-transform    | transform, project, reject           |
| invert-transform   | transform, project, reject           |
| compose-transforms | apply-transform                      |
| chain              | compose-transforms, transform, reflect |
| pipeline           | chain                                |

Leaf functions (no outgoing calls): distance, dot, scale, translate.

---

## Step 3: Find the duplication bug

**Tool:** `mcp__cnf__render` on IDs 56 (distance) and 104 (dot).

```
(defn distance [x y]
  (+ (* x x) (* y y)))

(defn dot [x y]
  (+ (* x x) (* y y)))
```

**Finding:** `distance` and `dot` have identical implementations. Same
parameters (`x`, `y`), same body `(+ (* x x) (* y y))`. This is the
known duplication bug.

---

## Step 4: Impact analysis -- consolidating `dot`

### Transitive dependency rule

```
(depends-on ?fn ?dep) :- (fn-calls ?fn ?dep)
(depends-on ?fn ?dep) :- (fn-calls ?fn ?mid) (depends-on ?mid ?dep)
```

### Query: `(depends-on (? fn) "104")`

10 functions transitively depend on `dot`:

| Function           | Relationship to dot                       |
|--------------------|-------------------------------------------|
| project (252)      | Direct caller                             |
| reject (276)       | calls project                             |
| basis-y (312)      | calls reject                              |
| decompose (332)    | calls project + reject                    |
| recompose (356)    | calls basis-y                             |
| apply-transform (388) | calls project + reject                 |
| invert-transform (412) | calls project + reject                |
| compose-transforms (436) | calls apply-transform               |
| chain (456)        | calls compose-transforms                  |
| pipeline (480)     | calls chain                               |

All of these would need review if `dot` were consolidated with `distance`.

---

## Step 5: Rename `dot` to `dot-product`

**Tool:** `mcp__cnf__rename` -- entity 104, new name `dot-product`.

Result: All references updated automatically. The old name claim is
marked `[superseded]` in the claim graph; the new name claim is current.

Verified via `mcp__cnf__inspect` on entity 104:
- Claim 106: `name -> "dot"` [superseded]
- Claim 505: `name -> "dot-product"` (current)

Rendered `project` to confirm propagation:
```
(defn project [x y]
  (scale (dot-product x y) (dot-product y y)))
```

Call sites updated correctly.

---

## Step 6: Datalog rule for transitive `dot-product` dependents

```
(uses-dot-product ?fn) :- (depends-on ?fn "104")
```

Query result -- 10 functions:
1. project (252)
2. reject (276)
3. basis-y (312)
4. decompose (332)
5. recompose (356)
6. apply-transform (388)
7. invert-transform (412)
8. compose-transforms (436)
9. chain (456)
10. pipeline (480)

---

## Step 7: Final rendered state of affected functions

```
(defn dot-product [x y]
  (+ (* x x) (* y y)))

(defn project [x y]
  (scale (dot-product x y) (dot-product y y)))

(defn reject [x y]
  (- x (project x y)))

(defn basis-y [x y]
  (normalize (reject x y) y))

(defn decompose [x y]
  (+ (project x y) (reject x y)))

(defn recompose [x y]
  (+ (scale (basis-x x y) x) (scale (basis-y x y) y)))

(defn apply-transform [x y]
  (transform (project x y) (reject x y)))

(defn invert-transform [x y]
  (transform (reject x y) (project x y)))

(defn compose-transforms [x y]
  (apply-transform (apply-transform x y) y))

(defn chain [x y]
  (compose-transforms (transform x y) (reflect x y)))

(defn pipeline [x y]
  (chain (chain x y) (chain y x)))
```

---

## Summary of Datalog rules defined

| Rule            | Purpose                                      |
|-----------------|----------------------------------------------|
| sub-expr        | Direct child (left/right) of expression node |
| contains        | Transitive closure of sub-expr               |
| fn-calls        | Function A directly calls function B         |
| direct-call     | (initial version, body-level calls only)     |
| depends-on      | Transitive closure of fn-calls               |
| uses-dot-product| All functions transitively depending on dot-product |

## Key findings

1. **Duplication confirmed:** `distance` and `dot` had identical bodies.
2. **Impact radius:** 10 of 20 functions (50%) transitively depend on `dot`.
3. **Rename propagation:** Renaming `dot` -> `dot-product` via the claim graph
   automatically updated the call sites in `project` (the sole direct caller).
   The supersession mechanism preserved the old name as history.
4. **Graph structure:** The call graph has clear layering -- leaf primitives
   (distance, scale, translate) at the bottom, compound operations (project,
   reject, normalize) in the middle, and high-level compositions (chain,
   pipeline) at the top.

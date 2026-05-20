# Arena Program Refactoring Transcript

## Step 1: Read and understand the program structure

Read `/home/tom/code/cnf-racket/experiments/arena-program.txt` — 60 lines, 19
functions in a Clojure-like S-expression syntax. Each function takes 2 params
and has a single-expression body.

Functions defined (in order):
1. `distance`, 2. `normalize`, 3. `dot`, 4. `scale`, 5. `translate`,
6. `transform`, 7. `reflect`, 8. `midpoint`, 9. `lerp`, 10. `project`,
11. `reject`, 12. `basis-x`, 13. `basis-y`, 14. `decompose`, 15. `recompose`,
16. `apply-transform`, 17. `invert-transform`, 18. `compose-transforms`,
19. `chain`, 20. `pipeline`

## Step 2: Direct dependency map

Parsed every function body and matched against all 19 defined names:

| Function           | Calls                          |
|--------------------|--------------------------------|
| distance           | (leaf)                         |
| normalize          | distance                       |
| dot                | (leaf)                         |
| scale              | (leaf)                         |
| translate          | (leaf)                         |
| transform          | normalize, scale, translate    |
| reflect            | scale                          |
| midpoint           | scale                          |
| lerp               | scale                          |
| project            | **dot**, scale                 |
| reject             | project                        |
| basis-x            | normalize                      |
| basis-y            | normalize, reject              |
| decompose          | project, reject                |
| recompose          | scale, basis-x, basis-y        |
| apply-transform    | transform, project, reject     |
| invert-transform   | transform, project, reject     |
| compose-transforms | transform, apply-transform     |
| chain              | transform, reflect, compose-transforms |
| pipeline           | chain                          |

## Step 3: Confirmed duplication bug — `distance` and `dot` are identical

```
distance body: (+ (* x x) (* y y)))
dot body:      (+ (* x x) (* y y)))
```

Both compute the same expression. This is the known duplication bug.

## Step 4: Functions affected if we consolidate dot into distance

**Direct caller of `dot`:** only `project` (line 29).

If `dot` were merged into `distance`, only `project`'s source text would need
updating. However, the semantic impact propagates transitively through the call
graph (see Step 6).

## Step 5: Renamed `dot` to `dot-product`

Created `arena-program-refactored.txt` via `sed 's/\bdot\b/dot-product/g'`.

Diff (2 lines changed, 3 token replacements):
```diff
7c7
< (defn dot [x y]
---
> (defn dot-product [x y]
29c29
<   (scale (dot x y) (dot y y)))
---
>   (scale (dot-product x y) (dot-product y y)))
```

## Step 6: All functions that transitively depend on `dot-product`

Starting from `dot-product`, walked callers recursively:

1. **project** — calls dot-product directly
2. **reject** — calls project
3. **basis-y** — calls reject
4. **decompose** — calls project, reject
5. **recompose** — calls basis-y
6. **apply-transform** — calls project, reject
7. **invert-transform** — calls project, reject
8. **compose-transforms** — calls apply-transform
9. **chain** — calls compose-transforms
10. **pipeline** — calls chain

**10 functions** are transitively dependent on `dot-product`.

Full dependency chains from dot-product to leaves:
```
dot-product -> project -> reject -> basis-y -> recompose
dot-product -> project -> reject -> decompose
dot-product -> project -> reject -> apply-transform -> compose-transforms -> chain -> pipeline
dot-product -> project -> reject -> invert-transform
dot-product -> project -> decompose
dot-product -> project -> apply-transform -> compose-transforms -> chain -> pipeline
dot-product -> project -> invert-transform
```

## Step 7: Final state of affected functions

Only two functions had their **source text** modified:

### `dot-product` (renamed from `dot`)
```
(defn dot-product [x y]
  (+ (* x x) (* y y)))
```

### `project` (call sites updated)
```
(defn project [x y]
  (scale (dot-product x y) (dot-product y y)))
```

The remaining 8 transitively-affected functions (`reject`, `basis-y`,
`decompose`, `recompose`, `apply-transform`, `invert-transform`,
`compose-transforms`, `chain`, `pipeline`) have unchanged source text — they
are affected only because their behavior depends on `project`, which now calls
`dot-product` instead of `dot`.

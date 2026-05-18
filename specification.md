# Claim Normal Form

A data-modeling normal form where everything is objects and claims.

Claims connect objects. Claims are objects. Predicates are objects.
Literals ground objects. There is no other machinery.

## The problem

Most graph/EAV systems smuggle meaning into the schema layer:

```
:person/name "Tom"        ← predicate encodes subject kind
:task/status "open"       ← predicate encodes object kind
tom IS d1, d1 IS name     ← descriptor wrapper needed to reify a fact
```

This creates several problems:

- Predicates are magic keywords, not queryable data
- Adding a new predicate requires a schema change
- You can't make statements about statements without wrapper nodes
- The schema vocabulary grows with every domain

## The normal form

### 1. Everything is an object

An object is anything with a unique identity. People, concepts, values,
claims, predicates — all objects. There is no special category.

### 2. A claim connects two objects via a predicate object

```
left --predicate--> right
```

All three positions are objects. The claim itself is an object.

### 3. Predicates are objects, not keywords

There are no magic predicate strings. "name", "source", "member-of" —
these are all objects with their own identities. They can be described
by other claims.

### 4. Claims are objects

Because a claim has its own identity, you can make claims about claims:

```
c1: me --name--> "tom"

c2: c1 --source--> utterance-1
c3: c1 --confidence--> 0.92
c4: c1 --asserted-by--> process-7
```

Provenance, confidence, derivation, epistemic layer — all attach
directly to claims without wrapper nodes.

## Three kinds of object

```
Object = addressable identity

Entity = object only (pure referent)
Value  = object + host-literal grounding
Claim  = object + assertion structure (l p r)
```

Formally:

```
Entity ⊂ Object
Value  ⊂ Object
Claim  ⊂ Object

claim : Object × Object × Object → Claim
```

The fact shape is `(l p r)`. Each of `l`, `p`, and `r` can be any object:

```
(Entity  name          Value)     — a person has a name
(Claim   source        Entity)    — a claim has provenance
(Entity  related-to    Entity)    — two things are linked
(Value   translated-as Value)     — a literal maps to another
(Entity  deprecated-by Entity)    — a predicate is retired
```

No slot is type-restricted. A predicate is just an object occupying the
middle position.

### Entity

```
entity "e1"
```

Something exists. It is distinguishable from other things. Nothing else
is asserted. This is the **referent before description** — the empty
handle that facts accumulate around.

Without entities, you only have values and claims. Then where does "the
person" live? You'd be forced to collapse the person into `"Tom"` or
into the claim itself. Both are wrong. The entity is the thing being
talked about.

### Value

```
value "v1", grounded to "Tom"
```

An object anchored to a canonical host literal. Values are **interned**:
the string `"Tom"` has exactly one value object in the system. This is
not an assertion — it is substrate contact. The system does not claim
that `v1` is `"Tom"`; `v1` IS `"Tom"`.

Grounding is not truth-apt. It cannot be disputed, sourced, revised,
or given confidence. If it could, you'd have destroyed literal identity.
This is the one place where the graph bottoms out into concrete data.

Claims reference value objects, not raw host literals. The display
form `e1 --name--> "Tom"` is shorthand for `e1 --name--> v1` where
`v1` is the interned value object. "Ungrounded" and "grounded to
host-false" are distinct states — an entity has no literal, while a
value grounded to `false` has one.

### Claim

```
claim "c1": e1 --name--> v1
```

An asserted relationship between objects. Claims are truth-apt — they
can be wrong, sourced, retracted, believed, disputed. Because claims
are objects, provenance and metadata attach as further claims (see
rule 4 above).

## Compared to EAV and Datomic

The distinction is not cosmetic:

```
EAV = roles inside a fact     (entity, attribute, value)
CNF = kinds of addressable object  (entity, value, claim)
```

These are not the same thing renamed. They operate at different levels.

In EAV, the triple `(thing, property, datum)` has three categorically
different slots. The middle slot is special — attributes are schema,
declared with types and cardinalities, living in a privileged registry.
Datomic added time and immutability (EAVT), which was a significant
advance, but kept this boundary: `:db/valueType`, `:db/cardinality`.

CNF does not replace EAV's privileged attribute slot with a different
privileged slot. It replaces it with a **uniform object model**. All
three slots of a triple hold the same kind of thing — an object. A
predicate is just an object occupying the middle position. It can be
described, renamed, queried, versioned, deprecated, sourced, and
claimed about like anything else.

This is the same move Lisp made with code and data: erase the type
boundary.

| | EAV / Datomic | CNF |
|---|---|---|
| Predicate | Schema declaration | Just another object |
| Adding a predicate | Schema migration | Create an object |
| Querying predicates | Special API | Same as querying anything |
| Statements about statements | Not possible / requires reification | Claims are objects — just claim about the claim |
| Attribute metadata | Separate registry | Claims about the predicate object |

EAV says "attributes are a special registry." CNF says "there is no
registry, there are only objects and claims about them."

## Prior art

CNF does not invent first-class triples, reification, Datalog, literal
grounding, or schema-as-data. It takes ideas from the Datomic/RDF family
and removes the privileged attribute/schema slot.

**RDF / RDF 1.2.** The closest semantic ancestor. RDF triples are
subject–predicate–object; predicates denote resources; RDF 1.2 adds
triple terms and reifiers for making statements about statements — close
to CNF's claim objects. But RDF retains more category machinery around
what can appear where, and its reification model is layered onto the
base. CNF's `claim : Object × Object × Object → Claim` is a simpler
primitive.

**Datomic.** The practical ancestor. Immutable atomic facts, EAV,
Datalog queries, transaction time, accretion. A datom is
entity/attribute/value/transaction/added. Datomic proved the value of
this architecture. CNF's delta: dissolve the attribute boundary.
Datomic attributes are declared schema; CNF predicates are ordinary
objects.

**Wikidata.** Relevant for its "statement" model: subject–predicate–object
statements with qualifiers, references, and ranks — structurally similar
to making claims about claims. But Wikidata properties remain a
controlled layer; the property determines valid datatypes.

**OpenCog AtomSpace.** Prior art for "everything addressable, edges are
also atoms." AtomSpace represents vertices and edges as Atoms; Links
can contain other Links. Similar spirit but a broader AI/knowledge
substrate, not a minimal claim kernel.

**Topic Maps.** Worth knowing for subject identity. Topics, associations,
and occurrences with explicit concern for merging and identity of
subjects.

CNF's contribution is not any one of these ideas. It is the specific
compression:

> A minimal kernel where predicates, claims, entities, and values all
> live under one addressability model, with no privileged schema
> registry.

## The kernel

The host-level schema. These are the interpreter's primitives, not
graph-level predicates:

```
objects(id)                   — all addressable identities
values(id, canonical_literal) — subset grounded to host literals
claims(id, l, p, r)          — subset asserting a triple
```

Invariants:

```
values.id  ⊂ objects.id
claims.id  ⊂ objects.id
claims.l/p/r ∈ objects.id
```

The schema never changes. All domain modeling happens in the graph.

## Query surface

The kernel tables define storage. The query surface defines what
programs see — Datalog views derived from those tables, not claims:

```
object(id)                   — every addressable identity
triple(l, p, r)              — assertion as bare triple
claim(id, l, p, r)           — assertion with claim identity
current-triple(l, p, r)      — non-retracted triples
current-claim(id, l, p, r)   — non-retracted with identity
```

The grounding table is not part of the query surface. It is internal
substrate machinery.

When a query mentions a host literal, the query layer resolves it to
the corresponding value object automatically:

```
triple(?person, name, "Tom")    ← you write this
triple(?person, name, v_tom)    ← the system matches this
```

Datalog stays object-pure: it derives structure over object identities.
When the host runtime needs actual literals — for arithmetic, display,
or IO — it crosses the grounding boundary explicitly.

## What disappeared from DGNF

Claim Normal Form evolved from Descriptor Graph Normal Form (DGNF).

| DGNF | CNF |
|---|---|
| Descriptor nodes mediate every property | Claims are directly addressable — no wrapper needed |
| Predicates are keywords (`:is`, `:works-on`) | Predicates are objects |
| 8 schema attributes | 3 kernel structures |
| `tom IS d1, d1 IS name, d1 value "Tom"` | `c1: tom --name--> "Tom"` |

The descriptor was necessary when claims had no identity. Once claims
became first-class objects, the descriptor collapsed into the claim.

## Compound objects and collections

Structured data: create an entity and make claims about it.

```
address-1 --street--> "123 Main St"
address-1 --city--> "Springfield"
me --address--> address-1
```

Collections: membership is a claim.

```
me --member-of--> people
me --member-of--> engineers
```

No special machinery for either. Just claims.

## Where the ground is

Conflating grounding with assertion is a category error. A person being
named `"Tom"` is a claim. The string `"Tom"` being the host string
`"Tom"` is not a claim — it is the substrate boundary. The grounding
table sits outside the claim graph entirely.

> **Object is addressability. Claim is assertion. Value is grounding.
> Entity is referent.**

## Domain vocabularies

CNF is domain-agnostic. Domain meaning comes from predicate objects and
collection objects that accumulate claims:

```
Work:     requires, blocks, produces, assigned-to, effort, outcome
People:   name, email, role, works-at, knows
Code:     calls, reads-field, returns, defined-in, type
Language: word, token, sentence, syntactic-role, semantic-role
```

Same kernel. Different objects. No schema changes.

## Programs as graphs

The thesis:

> Text code should stop being the canonical substrate for complex
> programs. The canonical substrate should be a persistent semantic
> graph. Text becomes an authoring view, export format, or hot-path
> implementation detail.

Every complicated program already secretly becomes graphs:

```
AST               call graph          control-flow graph
data-flow graph   dependency graph    type graph
module graph      build graph         test coverage graph
state machine     migration graph     runtime trace graph
```

Compilers build them, language servers index them, build tools traverse
them, debuggers replay them. Then they are thrown away or hidden behind
tool-specific formats. The move: make the graph durable, addressable,
queryable, and editable.

### Graph the meaning. Compile the motion.

Not every instruction should be a graph node. The distinction:

**Graph objects** — structure and relationships worth preserving:

```
function definitions    types              dependencies
AST nodes              effects             state transitions
build rules            tests               invariants
eval events            generated artifacts provenance
```

**Compiled motion** — things that just need to be fast:

```
arithmetic    branches    loop iterations
byte copies   allocations syscalls
```

Graph the meaning. Lower the motion to host code.

### CNF as program substrate

A program represented as claims:

```
fn-1   has-name  "calculate-pay"
fn-1   has-param employee
expr-7 op        multiply
expr-7 left      hours
expr-7 right     rate
expr-7 inside    fn-1
test-3 covers    expr-7
test-3 expects   1200
c-55   source    parser-run-12
c-55   came-from file-x
```

Then Datalog can answer structural questions text code cannot:

```
what depends on this?
what is ready to evaluate?
what changed since last run?
what claims support this generated file?
what needs recomputation?
what paths lead from input A to output B?
```

Text syntax becomes one projection among many:

```
graph → Racket        graph → docs
graph → Clojure       graph → tests
graph → TypeScript    graph → dependency map
graph → editor view
```

### Architecture

```
CNF graph       = canonical program substrate
Datalog         = query / derivation layer
Evaluator       = graph transition engine
Host primitives = actual effects / arithmetic / IO
Text syntax     = editable projection
Compiler        = lowers stable graph regions to fast code
```

### The strong claim

> Any sufficiently complicated program wants a semantic graph as its
> real substrate. Text files are a lossy authoring format over that
> graph.

This does not mean every program should be written in graph syntax. It
means the durable representation should be graph-shaped — because the
real structure already is.

## Reference implementation

This repository is the reference implementation: an in-memory Racket
kernel with Datalog query engine, small-step graph evaluator, and
incremental recompute.


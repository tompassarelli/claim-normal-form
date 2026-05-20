# E18: Real Baseline — CNF vs Rope vs Regex

## Why this experiment

E17 compared CNF against word-boundary regex. The obvious rebuttal:
regex is a strawman. Real semantic tools exist — Python's `rope`
library does scope-aware rename and reference-counting. If rope ties
CNF on the same tasks, E17 proved regex is dumb, not that CNF is
useful.

E18 answers this directly: three agents, same codebase, same hidden
tests.

## Setup

Same 45-function Python codebase as E16/E17. Three agent conditions:

- **Regex agent**: `\bname\b` word-boundary regex (E17's baseline)
- **Rope agent**: Python's `rope` refactoring library — scope-aware
  `Rename` and `find_occurrences` for dead code detection
- **CNF agent**: entity-reference-informed targeted edits

All agents run the full 26-test suite. Hidden tests score structural
correctness beyond what visible tests catch.

## Part A: Head-to-head results

| Task | Regex | Rope | CNF |
|------|------:|-----:|----:|
| 01. Rename subtotal | 3/5 | **5/5** | **5/5** |
| 04. Dead code removal | 14/16 | **16/16** | **16/16** |
| 05. Tax exemption (control) | 4/4 | 4/4 | 4/4 |
| 09. Rename order_total | 5/5 | 5/5 | 5/5 |
| **Total** | **26/30 (87%)** | **30/30 (100%)** | **30/30 (100%)** |

All three agents pass all 104 visible tests (26 × 4 tasks).

### What this proves

Rope ties CNF on every single-language structural task. The E17 result
was partly about regex being dumb: a real Python semantic tool handles
rename and dead code correctly. CNF has no advantage over rope on
single-language, single-session Python refactoring.

This is the honest result. We present it without spin.

### Task details

**Task 01 (rename subtotal)**: Regex hits 17 occurrences including dict
keys. Rope's scope-aware rename correctly limits to the 5 files that
reference the function. CNF's targeted edits produce the same result.

**Task 04 (dead code)**: Regex can't prove `total()` and `summary()`
are dead because dict keys create false references. Rope's
`find_occurrences` returns only 1 result (the definition) for each,
correctly identifying them as dead. CNF's entity references show the
same: zero callers.

**Task 05 (control)**: All three tie. Local code change, no structural
analysis needed.

**Task 09 (rename order_total)**: All three tie. `order_total` is
specific enough that even regex doesn't hit `"total"` dict keys.

## Part B: Substrate properties

These test properties that only a persistent claim graph provides. Rope
and regex get N/A by construction — they have no persistent state, no
rule engine, no cross-session memory.

| Test | Result |
|------|--------|
| B1: Cross-session rename — Agent A renames, checkpoints. Agent B restores, sees the rename. | **PASS** |
| B1: Transaction log shows Agent A's operations | **PASS** |
| B2: Datalog rule persists across sessions | **PASS** |
| B2: Agent B queries Agent A's derived facts | **PASS** |
| B2: Agent B composes new rules on Agent A's rules | **PASS** |

**5/5 substrate tests pass.**

### B1: Cross-session rename propagation

Agent A parses pricing.py, renames `subtotal` → `compute_subtotal`,
and checkpoints. Agent B restores the checkpoint. The renamed entity
is immediately visible to Agent B — no re-parsing needed.

The transaction log shows Agent A's operations, so Agent B has a
complete audit trail of who changed what and when.

### B2: Datalog rule persistence and cross-agent composition

Agent A parses four Python modules and defines a transitive dependency
rule:

```
(trans-dep ?f ?g) :- (py-fn-depends-on ?f ?g)
(trans-dep ?f ?g) :- (py-fn-depends-on ?f ?m), (trans-dep ?m ?g)
```

Agent A checkpoints. Agent B restores, finds the rule intact, queries
it, and gets derived transitive dependency facts. Agent B then defines
a new rule that composes on Agent A's rule:

```
(blast-radius ?root ?affected) :- (trans-dep ?affected ?root)
```

This composed rule immediately produces results using Agent A's derived
facts. Two agents, two sessions, rule composition with zero re-parsing.

## What the results mean

**Rope is the right baseline** for single-language Python refactoring.
It handles scope-aware rename and reference-counting correctly. CNF
has no correctness advantage over rope on these tasks.

**The difference is the substrate.** Rope gives you correct rename for
Python. CNF gives you a persistent claim graph with:

- Cross-session state (checkpoint/restore)
- Multi-agent collaboration (agent attribution, tx log)
- Composable derived facts (Datalog rules that survive sessions)
- Language-agnostic operation (same graph for Python, Racket, Beagle)
- Temporal history (supersession, not overwrite)

These are structurally impossible with rope. Not hard — impossible.
Rope operates on ASTs in memory for one session, one language. CNF
operates on a shared semantic substrate that persists, composes, and
spans languages.

## What we can and cannot claim

**Can claim**: On single-language structural tasks, CNF matches but
does not beat a real semantic tool (rope). The advantage over regex
was real but not unique — any scope-aware tool achieves it.

**Can claim**: CNF provides substrate properties (cross-session state,
Datalog rules, multi-agent composition, multi-language graph) that
rope cannot provide by construction.

**Cannot claim**: CNF is better than rope at Python refactoring. It
isn't. Rope is purpose-built for that.

**The honest pitch**: If you need Python rename, use rope. If you need
a persistent semantic substrate that agents can reason over across
sessions and languages, that's what CNF provides.

## Bug found during E18

Checkpoint/restore was not re-registering Python bridge Datalog rules
(`py-fn-depends-on`, `py-contains-call`). After restore, these rules
were missing, so any user-defined rule depending on them (like
`trans-dep`) returned no results. Fixed by adding
`restore-python-lang!` to the restore path.

## Reproducing

```bash
nix-shell -p python3Packages.rope --run 'python3 experiments/e18-real-baseline/run-eval.py'
```

Requires Python 3.x + rope. Uses the E16 codebase
(`experiments/e16-agent-grounding/codebase/`).

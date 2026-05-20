# E17: Agent-in-the-Loop Evaluation — Results

## Setup

Same 45-function Python codebase as E16. Two agent conditions:

- **Text agent**: word-boundary regex (`\bname\b`) — the best a
  text-based tool can do without semantic understanding.
- **CNF agent**: entity-reference-informed targeted edits — only
  changes what the claim graph identifies as entity references.

Both agents make actual code changes. Both run the full 26-test suite.
Hidden tests score correctness beyond what the test suite catches.

## The key finding

**Both agents pass all 26 original tests on every task.** The
difference only appears in hidden tests that check API contracts and
structural correctness — things the test suite was never designed to
verify.

This is the realistic failure mode: an agent makes a change, the tests
pass, but external consumers break because dict keys were renamed, dead
code was left behind, or display strings were corrupted.

## Results

### Task 01: Rename subtotal → compute_subtotal

The trap: `"subtotal"` appears as both a function name AND a dict
key/display string. Text agent's `\bsubtotal\b` cannot distinguish them.

| | Text agent | CNF agent |
|--|-----------|-----------|
| Transform | 17 regex replacements | 7 targeted edits |
| Original tests | **26/26 passed** | **26/26 passed** |
| Hidden tests | **3/5** | **5/5** |
| Dict key `"subtotal"` in summary | Wrongly renamed | Preserved |
| Display string `"subtotal"` in line items | Wrongly renamed | Preserved |

The text agent renames consistently — dict keys AND assertions both
change — so the original tests still pass. But any external consumer
expecting `result["subtotal"]` would break. The hidden tests catch this.

The text agent also renames the `subtotal` parameter in `tax_amount`
and the word "subtotal" in two docstrings (4 additional false positive
edits that happen to be harmless).

### Task 04: Dead code removal

The trap: `total()` and `summary()` are dead code, but `grep -w 'total'`
matches dict keys `"total"` and `grep -w 'summary'` matches dict key
`"summary"` — making them appear to have callers.

| | Text agent | CNF agent |
|--|-----------|-----------|
| Dead functions removed | **5/7** | **7/7** |
| Original tests | **26/26 passed** | **26/26 passed** |
| Hidden tests | **14/16** | **16/16** |
| Missed: `processing.total()` | Yes — dict key creates false ref | No — 0 entity references |
| Missed: `processing.summary()` | Yes — dict key creates false ref | No — 0 entity references |

The text agent correctly identifies 5 dead functions (names unique
enough that grep doesn't confuse them). But `total` and `summary` are
common words that appear as dict keys, so grep can't prove they're
uncalled. CNF's entity references show zero callers definitively.

### Task 05: Tax exemption (control)

Both agents add the same `exempt_below` parameter to `tax_amount`.
This is a local code change — structural analysis not needed.

| | Text agent | CNF agent |
|--|-----------|-----------|
| Original tests | **26/26 passed** | **26/26 passed** |
| Hidden tests | **4/4** | **4/4** |

Included to demonstrate that CNF does not claim to win on local code
changes. Both agents are equally capable here.

### Task 09: Rename order_total → compute_order_total

Both agents succeed. `order_total` is specific enough that word-boundary
regex doesn't hit the dict key `"total"` or `processing.total()`.

| | Text agent | CNF agent |
|--|-----------|-----------|
| Transform | 9 regex replacements | 8 targeted edits |
| Original tests | **26/26 passed** | **26/26 passed** |
| Hidden tests | **5/5** | **5/5** |

Included to demonstrate that text search CAN work when function names
are unique enough. The failure mode is specific: common words that
appear as both identifiers and dict keys/strings.

## Scorecard

| Task | Text | CNF | Winner |
|------|------|-----|--------|
| 01. Rename subtotal | 3/5 | **5/5** | CNF |
| 04. Dead code removal | 14/16 | **16/16** | CNF |
| 05. Tax exemption | 4/4 | 4/4 | Tie |
| 09. Rename order_total | 5/5 | 5/5 | Tie |
| **Total** | **26/30 (87%)** | **30/30 (100%)** | **CNF** |

Original test suites: both pass all 104 tests (26 × 4 tasks).

## What this means

The text agent used the BEST available text approach: word-boundary
regex, which avoids substring false positives (`order_subtotal` is not
affected by renaming `subtotal`). Even so, it cannot distinguish:

- `subtotal(items)` (function call) from `"subtotal"` (dict key)
- `total()` (dead function) from `"total"` (dict key in same codebase)

These are not edge cases. Dict keys commonly match function names in
real codebases. The failure is structural: text tools represent
characters, not identity.

CNF's entity references point to objects, not strings. A dict key
`"subtotal"` is not an entity reference to the `subtotal` function.
The claim graph knows this; regex cannot.

## What we can and cannot claim

**Can claim**: A CNF-backed agent produces more correct code changes
than a text-backed agent on structural tasks (rename, dead code
removal). Both pass the original test suite — the difference is in
API contracts that tests don't cover.

**Cannot claim**: CNF makes agents better at ALL tasks. Tasks 05 and
09 show text works fine for local changes and uniquely-named functions.

**The honest framing**: CNF wins where stable identity matters. Text
wins where it doesn't. Most real-world structural tasks involve common
names, shared vocabulary between code and data, and deep dependency
chains — exactly the cases where CNF's advantage is decisive.

## Reproducing

```bash
cd experiments/e17-agent-in-the-loop
python3 run-eval.py
```

Requires Python 3.x. Uses the E16 codebase (`../e16-agent-grounding/codebase/`).

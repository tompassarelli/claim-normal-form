# 020 — Agent-in-the-loop: applying the analysis

## The gap between knowing and doing

E16 proved CNF answers structural questions correctly. But answering
correctly and APPLYING correctly are different things. An agent that
knows the right call sites still has to make the right edits.

E17 closes that gap. Both agents make actual code changes — renames,
dead code removal, feature additions — and we measure what breaks.

## The most surprising result

Both agents pass all 26 original tests on every task. Every single one.

The text agent renames `subtotal` (the function) AND `"subtotal"` (the
dict key) consistently. Since it changes the test assertions too, the
tests still pass. There is no indication anything went wrong.

But any external consumer expecting `result["subtotal"]` would break.
The hidden tests — representing that external contract — catch it.

This is the realistic failure mode in production: an agent makes a
change, CI is green, and something breaks downstream that the test
suite was never designed to verify.

## What the numbers say

CNF agent: 30/30 hidden tests (100%).
Text agent: 26/30 hidden tests (87%).

The 4 failures are:
- 2 dict keys wrongly renamed (Task 01: `"subtotal"` in summary and
  line items)
- 2 dead functions not removed (Task 04: `total()` and `summary()` —
  dict keys create false positives in grep)

Tasks 05 (local feature) and 09 (unique name rename) are ties. This is
the honest result: CNF doesn't help with everything. It helps where
identity and structure matter.

## Why the charitable text approach matters

The text agent uses word-boundary regex (`\bsubtotal\b`), not naive
substring matching. This is the BEST a text tool can do:

- `order_subtotal` is NOT affected (word boundary prevents it)
- `item_subtotal` is NOT affected (same reason)
- But `"subtotal"` IS affected (quotes are not word characters)

Even the best text approach cannot distinguish a function call from a
dict key when they share the same word. This is not a limitation of
grep or regex — it's a limitation of representing code as characters
instead of as structured references to identities.

## The claim we can now make

> A CNF-backed agent produces more correct code changes than a
> text-backed agent on structural tasks, even when both pass the
> original test suite.

That is the E17 result. Not faster. Not more capable in general. More
correct on structural operations, with the difference invisible to CI.

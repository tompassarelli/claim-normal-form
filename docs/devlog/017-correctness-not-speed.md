# 017 — Correctness, not speed

## The challenge

An external reviewer read the whole repo and gave the honest critique:
"The infrastructure is impressive; the payoff is asserted, not yet
demonstrated." 14 experiments proving the engine is fast. Zero
experiments proving an agent gives *better answers* with CNF than
without it.

Fair. So we built the experiment.

## The experiment

50-function Python order processing system. 5 layers of dependencies.
5 functions with names that shadow domain functions (process vs
process_order, total vs subtotal, etc.). Realistic enough that the
answers aren't obvious.

Five tasks — the kind of structural questions an agent actually needs
to answer during refactoring:

1. **Transitive impact**: if `round_cents` changes, what breaks?
2. **Rename safety**: rename `subtotal`, what call sites change?
3. **Name disambiguation**: which `process` is being called?
4. **Dead code detection**: which functions have no callers?
5. **Full dependency tree**: what does `full_report` depend on?

## The results

CNF got all five right. Grep got all five wrong.

Not "grep was slower." Wrong. Grep reported 9 affected functions when
the answer was 17. Grep would rename a dict key that's a string
literal, not a function call. Grep can't tell `process()` from
`process_order()`. Grep can't prove a function is dead. Grep found
7 dependencies when the answer was 21.

The specific numbers:

- Task 1: grep misses 47% of transitively affected functions
- Task 2: grep has false positives from string literal matches
- Task 3: grep conflates 5 pairs of shadowed names
- Task 4: grep can't distinguish calls from definitions/strings
- Task 5: grep misses 67% of the dependency tree

## Why this is the result that matters

Every previous experiment measured speed, call count, or capability
("can the agent define composable rules?"). Those are real, but they
don't answer the question practitioners ask: "will my agent give me
a better answer?"

This experiment answers: yes. Not because it's faster. Because it
has structural understanding. Entity references don't lie. Transitive
closure is exact. Materialized views are complete.

An agent that says "17 functions are affected" when the answer is 17
is more useful than an agent that says "9 functions" when it missed
47% of them. That's not a benchmark game. That's the difference
between a correct refactoring and a broken one.

## What's honest

This is still a 50-function codebase, not 50,000. The Python bridge
has 50ms parse overhead from the subprocess. The rendering is
structural, not syntactic — you won't get runnable Python back from
the renderer.

But the correctness advantage doesn't depend on scale. It depends on
having entity references instead of string matching. That's true at
50 functions and it's true at 50,000. Grep's error rate on transitive
queries doesn't get better with more code — it gets worse.

## What the reviewer asked for

> "One honest head-to-head eval: same agent, same nontrivial
> refactoring task, measured on correctness and token cost."

This is the first half — correctness on structural tasks. The second
half (same agent, same task, measure token cost) is the next experiment.
But correctness is the harder claim to make and the more important one
to prove. Speed you can buy with hardware. Correctness you can only
get from understanding.

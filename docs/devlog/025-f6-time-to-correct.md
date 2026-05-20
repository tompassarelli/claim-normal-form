# 025 — F6: Git was faster

The hypothesis: CNF's correctness advantage outweighs its sequential
pipeline cost. The result: it doesn't. Not at this scale.

## The numbers

Git: 276s to 28/28. CNF: 500s to 28/28. Git wins 1.8x.

Git built in parallel (132s), tested (22/28), repaired in one
round (83s). CNF built sequentially (354s), tested (28/28), no
repair needed.

## Why this happened

The repair loop was cheap. One agent, 56 seconds, read the test
output, made four local fixes, done. The failures had precise
error messages. The fixes didn't interact. The codebase fit in
one context window.

Parallelism is free speed. 8 agents in 132s wall clock vs 354s
sequential. That's 2.7x on the build phase alone. CNF can't
recover from that without its own parallelism.

## What it means

CNF's value proposition at this scale is predictability, not
speed. It produces correct code every time. Git produces broken
code that can be fixed quickly. "Build broken, fix fast" wins
when the fix is cheap.

The interesting question: when does the fix become expensive?

- When repair rounds compound (fix A breaks B)
- When failures are non-local (need architectural understanding)
- When the codebase exceeds one context window
- When merge conflicts interact with semantic errors

None of those happened here. The toy app is too small, the
failures too clean, the repair agent too capable.

## What I'd do differently

If I ran this again at larger scale:

1. **Larger codebase** — 50+ files, multiple directories,
   import chains that span modules
2. **More agents** — 15-20, where merge complexity is O(N²)
3. **Harder cross-cutting requirements** — not just "add a status"
   but "change the authorization model" mid-run
4. **Semantic failures** — bugs that pass tests but break contracts
   (the E17 result suggests these are where CNF shines)

The repair agent's effectiveness is the key variable. It was
suspiciously good here. Real-world repair is rarely one round.

## Honest reflection

This is the first experiment where CNF lost. The instinct is to
explain it away — "the repair was too easy," "the scale is too
small," "real codebases are different." Those might be true. But
the data says what it says: at 8 agents and 28 tests, parallel
build + repair is faster than sequential build + correctness.

The thesis isn't dead. The claim was never "CNF is faster at
everything." It was "shared semantic state reduces structural
coordination failures." F6 confirms that (22/28 vs 28/28 on
first test) while showing that the speed tradeoff is currently
unfavorable.

The path forward is CNF parallelism — concurrent agents writing
to the shared graph simultaneously. That's the BEAM story. F6
shows why it matters: without parallelism, correctness alone
doesn't win on time.

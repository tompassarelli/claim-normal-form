# 019 — Text search is not program understanding

## What E16 actually proved

E16 ran 10 structural tasks on a 45-function Python codebase with
ground truth. CNF answered 7/7 structural tasks correctly. Text search
was wrong on 5 and unable to prove correctness on 2.

But the important framing: E16 is not yet "CNF makes agents better" in
the strongest empirical sense, because we have not run the same model
against the same tasks with different tool surfaces. What E16 proves is
the necessary substrate claim:

> Structural questions require semantic identity. Text search does not
> have it. CNF does.

That is the difference between "a thing is true" and "an agent using
that thing performs better." Both matter. E16 establishes the first.

## The task separation matters

E16 deliberately includes three local code-edit tasks (add tax exemption,
extract helper, fix validation bug). Both approaches can solve those.
Admitting this is what makes the structural results credible:

- Structural tasks: CNF wins hard.
- Local code-edit tasks: both can solve them.
- Conclusion: CNF specifically wins where stable identity, dependency
  closure, history, and cross-session structure matter.

That distinction keeps the project honest.

## Cross-session memory is the real result

The broader agent pain is not merely "search is bad." It is: every agent
session wakes up with amnesia and has to re-derive the project from
scratch.

E16 task 10 tests this directly. The CNF agent checkpoints its rules,
derived facts, and entity graph. A second session restores everything.
Rename propagates through the restored graph. Score: 10/10.

The text agent has no mechanism to persist structural understanding
across sessions. Score: 0/10. Not because it's slow — because the
capability does not exist. There is no shared semantic substrate to
persist, inherit, or compose on.

This may be the most important result in the project. The correct
framing is not "CNF is a better grep." It is:

> Program understanding can persist as shared semantic state.

## What we can and cannot claim

We can credibly say:

> On structural code-understanding tasks, CNF answered 7/7 correctly.
> Text search was wrong or unable to prove correctness on 7/7.

We can say:

> CNF gives agents a structural workspace that text search cannot
> provide.

We cannot yet say:

> CNF makes agents produce better code.

That requires E17: same model, same tasks, same hidden tests, different
tool surfaces. Measure correct task completion, false-positive edits,
missed affected sites, tool calls, tokens, time.

## The phrase

The project has been searching for its one-liner. I think it's this:

> A semantic working copy for coding agents.

"Working copy" is a term developers already understand — it's the local
state you operate on. "Semantic" says what's different: not files, but
meaning. "For coding agents" says who it's for.

Text search finds strings. CNF answers what the program means.

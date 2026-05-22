# 018 — E16 agent grounding harness

## The challenge

An external reviewer said it plainly: "The infrastructure is
impressive; the payoff is asserted, not yet demonstrated."

E15 proved correctness on structural queries — CNF gets the right
answer where text search doesn't. But E15 is a measurement, not an
agent session. The question remains: does a real agent with CNF tools
actually produce better code changes than a real agent with text tools?

## What we built

A complete evaluation harness:

**Codebase**: 4-module Python order processing system with 45 functions,
5 layers of dependencies, 3 shadowed name pairs, 7 dead code functions,
a known bug, and dict-key/string-literal traps. 26 passing tests.

**10 tasks**: each requiring structural understanding, each with a
specific trap that text search falls into. Renames where dict keys
match function names. Dead code detection where grep conflates similar
names. Transitive impact analysis at 5 layers depth. Cross-session
memory that text agents structurally cannot do.

**Ground truth**: expected answers for every task, documented in
`ground-truth/answers.md`.

**Hidden tests**: automated scoring in `ground-truth/hidden_tests.py`.
Run after an agent completes a task to check correctness mechanically.

**CNF baseline**: `cnf-parse.rkt` parses the codebase, materializes
views, and answers the structural questions with ground truth:
- 23 functions transitively affected by `round_cents`
- 25 functions in `full_report`'s dependency tree
- 10 functions with no callers (7 dead + 3 entry points)

## The experiment design

Same model. Same prompts. Same hidden tests.

Text agent gets: read, grep, edit, run tests.
CNF agent gets: parse, query, rename, rules, render, checkpoint.

10 tasks. Each scored on correctness (hidden tests), false positives
(did you rename a dict key?), and tool usage.

Task 10 is the paradigm task: cross-session memory. Agent A builds
rules and checkpoints. Agent B restores and inherits everything.
Text agent scores 0 on this task — it's structurally impossible.
That's not a benchmark game. That's a capability gap.

## What's next

Run both agents. Record sessions. Score results. Write E16 results.

The harness is ready. The ground truth is computed. The hidden tests
are automated. The only thing left is pressing play.

# 031: The harvest — capturing what agents actually think

## The discovery

Claude Code's `--system-prompt` flag replaces the default system
prompt entirely. `--bare` strips hooks, LSP, auto-memory, CLAUDE.md
discovery. `--output-format stream-json --verbose` emits every
thinking block, tool call, and tool result as structured JSON.

Combined:

```bash
claude -p \
  --bare \
  --system-prompt "You are building a Python module..." \
  --output-format stream-json --verbose \
  --model sonnet \
  --mcp-config mcp-config.json \
  --allowed-tools "Bash,Read,mcp__cnf__query,..."
```

This gives us: custom system prompt (no Claude Code behavioral
conditioning), full reasoning capture (extended thinking + tool
calls), MCP graph access, zero API spend on a Max account.

## Why this matters

F2–F10 all ran with `claude -p` which only captures final text
output. We could see what agents *built* but not what they
*thought*. We inferred questions from code diffs — git agents
hardcoded `TERMINAL_STATUSES = {"closed", "resolved"}` so we
guessed they wanted to know "what are the terminal statuses?"

But inference is not measurement. To design the right high-level
graph tools for F11, we need the actual reasoning: what questions
agents ask, what tool calls they make, what verbs they use when
they think about the codebase.

## The confound problem

Claude Code's default system prompt shapes agent behavior. It tells
agents to "prefer Read over cat", "use Edit not sed", etc. An agent
inside that prompt doesn't ask "what are the terminal statuses?" —
it asks "let me read workflow.py" because the harness trained it to
reach for file-read. The natural verbs we'd harvest would be Claude
Code's verbs, not the agent model's verbs.

`--system-prompt` + `--bare` eliminates this. We write a minimal
prompt (just the task, no tool-use instructions), and the agent's
reasoning reflects its own patterns, not the harness.

## The plan

1. **Harvest run** — same ClaimDesk task as F9/F10, but with
   `--bare --system-prompt --output-format stream-json --verbose`.
   Full toolbox for CNF agents (Bash, Read, MCP graph tools).
   Everything to JSONL per agent.

2. **Rebaseline** — same run also tests git vs CNF under the new
   harness. If the margin moves, the harness WAS a confound in
   F2–F10. If it holds, we've earned the right to compare F11.

3. **Mine the corpus** — cluster actual queries from thinking
   blocks and tool calls. Frequency = priority. Long tail = escape
   hatch spec. The clusters ARE the tool set.

4. **F11** — graph-only tools derived from observed agent behavior,
   not from our guesses about what agents should want.

## Sanity check results

Ran the verb-diff sanity check: default Claude Code prompt (with
CLAUDE.md + auto-memory) vs custom `--system-prompt` (from clean
temp directory, no CLAUDE.md).

**Finding: information needs are prompt-invariant.** Both agents
asked the same questions — "what statuses exist?", "which are
terminal?", "what's the lifecycle?" — regardless of prompt. The
thinking verbs were identical ("let me read the file"). Only the
tool-use behavior differed: default agent was disciplined (5 calls),
custom agent thrashed (12 calls, tried Explore/Agent tools that
didn't exist, redundant reads).

This means the question-set for F11 can be derived from these two
runs — no large harvest needed. The questions are intrinsic to the
task, not artifacts of prompting.

**`--bare` doesn't work with Max auth** — it skips keychain reads.
`--system-prompt` alone replaces the prompt but CLAUDE.md/hooks
survive. For the harvest, the important variable turned out to be
tool availability, not the system prompt.

## First agent-tools test

Built `agent-tools.py` — a Python MCP server that wraps the daemon's
Datalog in 7 high-level tools. Tested a single haiku agent on the
notifications task with graph-only tools (no Bash, no Read, no grep).

The agent:
1. Called `list_symbols()` → discovered all code entities
2. Called `list_values("TERMINAL_STATUSES")` → got `["archived", "closed"]`
3. Called `declare_intent()` with dependencies and provisions
4. Wrote correct code with the right values

**Partial success.** The agent got the correct values (would pass
the 4 information-gap tests) but hardcoded them instead of importing
from workflow. The `where_defined` tool returned the kind but not the
source module — the agent wanted to import but didn't know from where.

Fix needed: `where_defined` must return the module name so agents
can write `from workflow import TERMINAL_STATUSES`.

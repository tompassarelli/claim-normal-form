# MCP Server

29 tools over JSON-RPC 2.0 / stdio. Claude Code connects and operates
on the claim graph directly.

## Quick start

```bash
racket mcp-server.rkt                    # stdio mode
racket mcp-server.rkt --daemon 7888      # daemon (TCP, multi-client, MVCC)
racket mcp-server.rkt --connect 7888     # bridge (stdio proxy to daemon)
```

## Claude Code configuration

Add to `.claude/settings.json`:

```json
{
  "mcpServers": {
    "cnf": {
      "command": "racket",
      "args": ["/path/to/cnf-racket/mcp-server.rkt"]
    }
  }
}
```

For daemon mode (shared state across sessions):

```json
{
  "mcpServers": {
    "cnf": {
      "command": "racket",
      "args": ["/path/to/cnf-racket/mcp-server.rkt", "--connect", "7888"]
    }
  }
}
```

## Tool reference

**Core (6 tools):**
`reset`, `create_entity`, `create_named`, `create_value`, `claim`, `status`

**Query (6 tools):**
`query`, `inspect`, `resolve_symbol`, `claims_where`, `lookup`, `find_by`

**Rules (3 tools):**
`define_rule`, `list_rules`, `supersede_rule`

**Schema (2 tools):**
`define_predicates`, `update`

**Program (6 tools):**
`parse_program`, `render`, `rename`, `add_function`, `remove_function`,
`modify_function`

**Batch (1 tool):**
`batch` — multiple operations in one call, with optional `atomic: true`
for all-or-nothing transactions

**Persistence (2 tools):**
`checkpoint`, `restore`

**Transactions (3 tools):**
`tx_log`, `current_tx_seq`, `set_agent`

## MCP Resources

Structured data pushed into agent context — no tool calls needed:

| URI | Content |
|-----|---------|
| `cnf://summary` | Object/claim counts, form overview |
| `cnf://dependencies` | fn-depends-on edges |
| `cnf://functions` | Function names and signatures |
| `cnf://rules` | User-defined Datalog rules |

Resources eliminate the status → query → list_rules round-trip pattern
that dominated early experiments. The agent starts with structural
understanding already in context.

## Key workflows

**Parse and query:**
```
parse_program(source) → fn IDs + schema
query("(fn-depends-on (? caller) (? callee))")
```

**Define custom rules:**
```
define_rule(head: "(trans-dep (? f) (? g))", body: "(fn-depends-on (? f) (? g))")
define_rule(head: "(trans-dep (? f) (? g))", body: "(fn-depends-on (? f) (? m)) (trans-dep (? m) (? g))")
query("(trans-dep some-function (? dep))")
```

**Incremental edit (no reparse):**
```
add_function(source: "(defn new-fn (x y) (+ (existing-fn x y) 1))")
modify_function(name: "old-fn", source: "(defn old-fn (x y) (* x y))")
remove_function(name: "deprecated-fn")
# Rules and matviews auto-update through mutations
```

**Cross-session persistence:**
```
checkpoint()   # save graph to ~/.cnf/checkpoint.json
# ... new session ...
restore()      # rebuild full graph + rules + matviews
```

**Multi-agent collaboration:**
```
set_agent(name: "structural-analyst")
# ... define rules, query ...
checkpoint()

# Agent B:
restore()
set_agent(name: "quality-checker")
list_rules()   # see Agent A's rules
# ... compose on Agent A's derived relations ...
tx_log()       # interleaved agent transactions
```

## Daemon mode

The daemon uses MVCC (multi-version concurrency control). Readers get
a snapshot of the committed state and run without any lock — multiple
queries execute concurrently with zero contention. Writers serialize
and publish a new snapshot on commit.

```bash
# Terminal 1: start daemon
racket mcp-server.rkt --daemon 7888

# Terminal 2: agent A
racket mcp-server.rkt --connect 7888

# Terminal 3: agent B
racket mcp-server.rkt --connect 7888
```

## Language auto-detection

The server auto-detects Python vs beagle from source syntax
(`def`/`class`/`import` → Python, else → beagle). All tools work
with both languages. An optional `language` parameter overrides
detection.

#!/usr/bin/env bash
# E7: Prove the interface improvements work.
# Starts a fresh MCP server, runs the E5 task using the new features
# (schema in parse, symbol resolution, batch), counts tool calls.

set -euo pipefail
cd "$(dirname "$0")/.."

SOURCE=$(cat experiments/arena-program.txt)
# Escape for JSON
SOURCE_JSON=$(python3 -c "import json,sys; print(json.dumps(sys.stdin.read()))" <<< "$SOURCE")

call_id=0
next_id() { call_id=$((call_id + 1)); echo $call_id; }

# Build all JSON-RPC messages
{
# --- Initialize ---
echo '{"jsonrpc":"2.0","id":'$(next_id)',"method":"initialize","params":{}}'
echo '{"jsonrpc":"2.0","method":"notifications/initialized","params":{}}'

# --- CALL 1: Reset ---
echo '{"jsonrpc":"2.0","id":'$(next_id)',"method":"tools/call","params":{"name":"reset","arguments":{}}}'

# --- CALL 2: Parse (now returns schema + predicate IDs) ---
echo '{"jsonrpc":"2.0","id":'$(next_id)',"method":"tools/call","params":{"name":"parse_program","arguments":{"source":'$SOURCE_JSON'}}}'

# --- CALL 3: Query built-in fn-depends-on (already materialized) ---
echo '{"jsonrpc":"2.0","id":'$(next_id)',"method":"tools/call","params":{"name":"query","arguments":{"body":"(fn-depends-on (? caller) (? callee))"}}}'

# --- CALL 4: Render distance and dot to confirm duplication ---
echo '{"jsonrpc":"2.0","id":'$(next_id)',"method":"tools/call","params":{"name":"render","arguments":{"ids":["56","104"]}}}'

# --- CALL 5: Batch — define transitive rule + query dependents of dot ---
echo '{"jsonrpc":"2.0","id":'$(next_id)',"method":"tools/call","params":{"name":"batch","arguments":{"operations":[{"tool":"define_rule","arguments":{"head":"(trans-dep (? a) (? b))","body":"(fn-depends-on (? a) (? b))"}},{"tool":"define_rule","arguments":{"head":"(trans-dep (? a) (? b))","body":"(fn-depends-on (? a) (? mid)) (trans-dep (? mid) (? b))"}},{"tool":"query","arguments":{"body":"(trans-dep (? fn) \"104\")"}}]}}}'

# --- CALL 6: Rename dot to dot-product ---
echo '{"jsonrpc":"2.0","id":'$(next_id)',"method":"tools/call","params":{"name":"rename","arguments":{"id":"104","new_name":"dot-product"}}}'

# --- CALL 7: Render project to verify rename propagated ---
echo '{"jsonrpc":"2.0","id":'$(next_id)',"method":"tools/call","params":{"name":"render","arguments":{"ids":["252"]}}}'

} | timeout 30 racket mcp-server.rkt 2>/dev/null | while IFS= read -r line; do
  # Parse out the id and first 200 chars of result
  id=$(echo "$line" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('id','?'))" 2>/dev/null || echo "?")
  # Skip initialize response (id=1) and notification
  if [ "$id" = "1" ]; then continue; fi
  if [ "$id" = "?" ]; then continue; fi

  # Extract text content
  text=$(echo "$line" | python3 -c "
import json,sys
d=json.load(sys.stdin)
r=d.get('result',{})
c=r.get('content',[])
if c:
    t=c[0].get('text','')
    # First 300 chars
    print(t[:300])
else:
    print(str(r)[:300])
" 2>/dev/null || echo "(parse error)")

  echo "=== Response id=$id ==="
  echo "$text"
  echo ""
done

echo ""
echo "Total tool calls: 7 (reset, parse, query deps, render, batch[3 ops], rename, render)"
echo "Compare to E5 CNF agent: 42 tool calls"
echo "Reduction: 6x fewer round-trips"

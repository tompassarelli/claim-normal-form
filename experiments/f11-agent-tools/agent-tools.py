#!/usr/bin/env python3
"""High-level MCP tool server for CNF agent experiments.

Wraps the low-level CNF daemon (Datalog predicates, entity IDs) in
7 tools that agents can use without knowing the query language:

  Read:
    list_values(name)        — literal values of a named variable
    list_symbols(kind)       — all named entities of a given kind
    get_transitions()        — valid state transition map
    what_depends_on(symbol)  — functions that call/use a symbol
    where_defined(symbol)    — which module defines a symbol

  Write:
    declare_intent(module, depends_on, provides)
                             — declare what this module needs/provides

  Read (intents):
    list_intents()           — all declared intents from all agents

Connects to a running CNF daemon over TCP. Speaks MCP (JSON-RPC 2.0)
over stdio to the agent.
"""

import json
import socket
import sys
import re

DAEMON_PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 7891

# ── Daemon connection ──

def send_rpc(sock, method, params):
    msg = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method,
                       "params": params})
    sock.sendall((msg + "\n").encode())
    data = b""
    while True:
        chunk = sock.recv(65536)
        if not chunk:
            break
        data += chunk
        if b"\n" in data:
            break
    lines = data.decode().strip().split("\n")
    return json.loads(lines[-1])


def tool_text(resp):
    return resp.get("result", {}).get("content", [{}])[0].get("text", "")


def daemon_query(sock, body):
    resp = send_rpc(sock, "tools/call", {
        "name": "query",
        "arguments": {"body": body},
    })
    return tool_text(resp)


def daemon_resolve(sock, name):
    resp = send_rpc(sock, "tools/call", {
        "name": "resolve_symbol",
        "arguments": {"name": name},
    })
    return tool_text(resp)


def daemon_inspect(sock, eid):
    resp = send_rpc(sock, "tools/call", {
        "name": "inspect",
        "arguments": {"id": eid},
    })
    return tool_text(resp)


def daemon_find_by(sock, predicate, value):
    resp = send_rpc(sock, "tools/call", {
        "name": "find_by",
        "arguments": {"predicate": predicate, "value": value},
    })
    return tool_text(resp)


def daemon_claim(sock, left, predicate, right):
    resp = send_rpc(sock, "tools/call", {
        "name": "claim",
        "arguments": {"left": left, "predicate": predicate, "right": right},
    })
    return tool_text(resp)


def daemon_create_entity(sock):
    resp = send_rpc(sock, "tools/call", {
        "name": "create_entity",
        "arguments": {},
    })
    return tool_text(resp)

# ── Intent storage ──

_intents = []


def _get_module_for_entity(sock, eid):
    """Look up which module an entity was defined in via source-module claims."""
    query_text = daemon_query(sock, f"(current-triple {eid} source-module (? mod))")
    if query_text and "?" in query_text:
        match = re.search(r'\(value:\s*([^)]+)\)', query_text)
        if match:
            return match.group(1).strip()
    return "unknown"

# ── High-level tool implementations ──

def handle_list_values(sock, args):
    """Return the literal values of a named variable/constant."""
    name = args.get("name", "")
    resolve_text = daemon_resolve(sock, name)

    if "->" not in resolve_text:
        return f"Symbol '{name}' not found in the graph."

    eid = resolve_text.strip().split("->")[-1].strip()
    inspect_text = daemon_inspect(sock, eid)

    # Find the py-body entity (predicate 53)
    body_eid = None
    for line in inspect_text.split("\n"):
        if "53 (entity)" in line or "py-body" in line:
            match = re.search(r'(\d+)\s+\(entity\)\s*$', line.strip())
            if match:
                body_eid = match.group(1)

    if not body_eid:
        return json.dumps({"name": name, "entity": eid, "values": "could not find body expression", "raw": inspect_text})

    body_inspect = daemon_inspect(sock, body_eid)

    # Extract py-has-child values from body — these are the literal list/set elements
    # Format: "NNN 77 (entity) VALUE (value: actual_string)"
    values = []
    for line in body_inspect.split("\n"):
        if "(value:" in line and "py-has-child" not in line and "py-expr-kind" not in line:
            match = re.search(r'\(value:\s*([^)]+)\)', line)
            if match:
                val = match.group(1).strip()
                if val not in ("list", "set", "dict", "tuple"):
                    values.append(val)

    return json.dumps(values)


def handle_list_symbols(sock, args):
    """Return all named entities, optionally filtered by kind."""
    kind = args.get("kind", "")

    # py-form-kind query returns all code entities with their kinds
    query_text = daemon_query(sock, "(current-triple (? e) py-form-kind (? kind))")

    results = []
    for line in query_text.strip().split("\n"):
        if "?" not in line:
            continue
        # Format: "N. ?e = 423 (is_archived), ?kind = 101 (value: function)"
        e_match = re.search(r'\?e\s*=\s*(\d+)\s*\(([^)]*)\)', line)
        k_match = re.search(r'\?kind\s*=\s*\d+\s*\(value:\s*([^)]+)\)', line)
        if e_match and k_match:
            ename = e_match.group(2)
            ekind = k_match.group(1).strip()
            results.append({"name": ename, "kind": ekind})

    if kind:
        kind_lower = kind.lower()
        results = [r for r in results if r["kind"].lower() == kind_lower]

    return json.dumps(results)


def handle_get_transitions(sock, args):
    """Return the valid state transition map."""
    resolve_text = daemon_resolve(sock, "VALID_TRANSITIONS")
    if "->" not in resolve_text:
        return "No VALID_TRANSITIONS found in the graph."

    eid = resolve_text.strip().split("->")[-1].strip()
    inspect_text = daemon_inspect(sock, eid)

    # Find the py-body entity
    body_eid = None
    for line in inspect_text.split("\n"):
        if "53 (entity)" in line:
            match = re.search(r'(\d+)\s+\(entity\)\s*$', line.strip())
            if match:
                body_eid = match.group(1)

    if not body_eid:
        return f"VALID_TRANSITIONS exists but body not found.\n{inspect_text}"

    body_inspect = daemon_inspect(sock, body_eid)

    # The dict body has key-value children. Extract them.
    # For now, return the raw inspection which shows the structure
    # TODO: walk the dict tree to reconstruct {status: [targets]}
    return f"VALID_TRANSITIONS defines the ticket state machine:\n{body_inspect}"


def handle_what_depends_on(sock, args):
    """Return functions that call or depend on a given symbol."""
    symbol = args.get("symbol", "")

    resolve_text = daemon_resolve(sock, symbol)
    if "->" not in resolve_text:
        return f"Symbol '{symbol}' not found."

    eid = resolve_text.strip().split("->")[-1].strip()

    dep_text = daemon_query(sock, f"(py-fn-depends-on (? caller) {eid})")

    callers = []
    if dep_text and "?" in dep_text:
        for line in dep_text.strip().split("\n"):
            parts = line.strip().split()
            if parts:
                caller_id = parts[0].replace("?caller=", "").replace("caller=", "")
                caller_resolve = daemon_inspect(sock, caller_id)
                for cl in caller_resolve.split("\n"):
                    if "symbol" in cl:
                        name_match = re.findall(r'"([^"]*)"', cl)
                        if name_match:
                            callers.append(name_match[0])

    call_text = daemon_query(sock, f"(current-triple (? caller) calls {eid})")
    if call_text and "?" in call_text:
        for line in call_text.strip().split("\n"):
            parts = line.strip().split()
            if parts:
                caller_id = parts[0].replace("?caller=", "").replace("caller=", "")
                caller_resolve = daemon_inspect(sock, caller_id)
                for cl in caller_resolve.split("\n"):
                    if "symbol" in cl:
                        name_match = re.findall(r'"([^"]*)"', cl)
                        if name_match:
                            callers.append(name_match[0])

    if callers:
        return json.dumps({"symbol": symbol, "depended_on_by": sorted(set(callers))})
    return json.dumps({"symbol": symbol, "depended_on_by": [], "note": "No dependents found via py-fn-depends-on or calls predicates."})


def handle_where_defined(sock, args):
    """Return which module defines a symbol and what kind it is."""
    symbol = args.get("symbol", "")

    resolve_text = daemon_resolve(sock, symbol)
    if "->" not in resolve_text:
        return f"Symbol '{symbol}' not found in the graph."

    eid = resolve_text.strip().split("->")[-1].strip()
    inspect_text = daemon_inspect(sock, eid)

    kind = "unknown"
    for line in inspect_text.split("\n"):
        # Look for py-form-kind claim: "NNN 81 (entity) 101 (value: function)"
        if "py-form-kind" in line or ("81 (entity)" in line and "(value:" in line):
            match = re.search(r'\(value:\s*([^)]+)\)', line)
            if match:
                kind = match.group(1).strip()

    module = _get_module_for_entity(sock, eid)
    return json.dumps({"symbol": symbol, "entity": eid, "kind": kind, "module": module})


def handle_declare_intent(sock, args):
    """Declare what a module needs and provides."""
    module = args.get("module", "")
    depends_on = args.get("depends_on", [])
    provides = args.get("provides", [])

    intent = {"module": module, "depends_on": depends_on, "provides": provides}
    _intents.append(intent)

    # Write into the graph as claims
    eid_text = daemon_create_entity(sock)
    eid_match = re.search(r'#(\d+)', eid_text)
    if eid_match:
        eid = eid_match.group(0)
        daemon_claim(sock, eid, "intent-module", f'"{module}"')
        for dep in depends_on:
            daemon_claim(sock, eid, "intent-depends-on", f'"{dep}"')
        for prov in provides:
            daemon_claim(sock, eid, "intent-provides", f'"{prov}"')

    return json.dumps({"status": "declared", "intent": intent})


def handle_list_intents(sock, args):
    """Return all declared intents."""
    return json.dumps(_intents)


TOOLS = {
    "list_values": {
        "handler": handle_list_values,
        "schema": {
            "name": "list_values",
            "description": "Get the literal values of a named variable or constant. Example: list_values('TERMINAL_STATUSES') returns ['closed', 'archived'].",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "The variable/constant name to look up"}
                },
                "required": ["name"],
            },
        },
    },
    "list_symbols": {
        "handler": handle_list_symbols,
        "schema": {
            "name": "list_symbols",
            "description": "List all named symbols (functions, variables, classes) in the codebase. Optionally filter by kind ('function', 'variable', 'class').",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "description": "Optional filter: 'function', 'variable', 'class', or empty for all"}
                },
                "required": [],
            },
        },
    },
    "get_transitions": {
        "handler": handle_get_transitions,
        "schema": {
            "name": "get_transitions",
            "description": "Get the valid state transition map for tickets. Shows which statuses can transition to which other statuses.",
            "inputSchema": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    "what_depends_on": {
        "handler": handle_what_depends_on,
        "schema": {
            "name": "what_depends_on",
            "description": "Find what functions or modules depend on (call or reference) a given symbol. Example: what_depends_on('update_ticket') shows all callers.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "The symbol name to find dependents of"}
                },
                "required": ["symbol"],
            },
        },
    },
    "where_defined": {
        "handler": handle_where_defined,
        "schema": {
            "name": "where_defined",
            "description": "Find where a symbol is defined — which module it's in and what kind (function, variable, class). Use the module name to write correct import statements.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "The symbol name to locate"}
                },
                "required": ["symbol"],
            },
        },
    },
    "declare_intent": {
        "handler": handle_declare_intent,
        "schema": {
            "name": "declare_intent",
            "description": "Declare what your module depends on and what it provides. This is written into the shared graph so other agents can see your intent. Example: declare_intent(module='notifications', depends_on=['TERMINAL_STATUSES', 'is_archived'], provides=['notify_transition', 'get_notifications'])",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "module": {"type": "string", "description": "Name of the module you are building"},
                    "depends_on": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Symbols this module needs from the existing codebase"
                    },
                    "provides": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Symbols this module will define/export"
                    },
                },
                "required": ["module"],
            },
        },
    },
    "list_intents": {
        "handler": handle_list_intents,
        "schema": {
            "name": "list_intents",
            "description": "List all declared intents from all agents. Shows what each module needs and provides.",
            "inputSchema": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
}


# ── MCP protocol handling ──

def handle_request(sock, req):
    method = req.get("method", "")
    req_id = req.get("id")
    params = req.get("params", {})

    if method == "initialize":
        return {
            "jsonrpc": "2.0", "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "cnf-agent-tools", "version": "0.1"},
            },
        }

    if method == "notifications/initialized":
        return None

    if method == "tools/list":
        tool_list = [t["schema"] for t in TOOLS.values()]
        return {
            "jsonrpc": "2.0", "id": req_id,
            "result": {"tools": tool_list},
        }

    if method == "tools/call":
        tool_name = params.get("name", "")
        tool_args = params.get("arguments", {})

        if tool_name not in TOOLS:
            return {
                "jsonrpc": "2.0", "id": req_id,
                "result": {
                    "content": [{"type": "text",
                                 "text": f"Unknown tool: {tool_name}"}],
                    "isError": True,
                },
            }

        try:
            result_text = TOOLS[tool_name]["handler"](sock, tool_args)
            return {
                "jsonrpc": "2.0", "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": result_text}],
                },
            }
        except Exception as e:
            return {
                "jsonrpc": "2.0", "id": req_id,
                "result": {
                    "content": [{"type": "text",
                                 "text": f"Error in {tool_name}: {e}"}],
                    "isError": True,
                },
            }

    return {
        "jsonrpc": "2.0", "id": req_id,
        "error": {"code": -32601, "message": f"Unknown method: {method}"},
    }


def main():
    sys.stderr.write(f"agent-tools: connecting to daemon on port {DAEMON_PORT}\n")
    sys.stderr.flush()

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(("127.0.0.1", DAEMON_PORT))

    send_rpc(sock, "initialize", {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "agent-tools", "version": "0.1"},
    })

    sys.stderr.write("agent-tools: connected to daemon, ready for MCP\n")
    sys.stderr.flush()

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue

        resp = handle_request(sock, req)
        if resp is not None:
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()

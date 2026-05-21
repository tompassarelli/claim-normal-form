#!/usr/bin/env python3
"""MCP tool server — 4 high-level tools for agent graph reasoning.

Each tool returns a complete, actionable answer to one natural question.
No chaining required. No Datalog exposed to the agent.

  discover(name)                  — everything about one symbol
  discover_all(kind?)             — all symbols with modules and values
  dependencies(symbol?)           — what calls what
  declare_intent(module, ...)     — write coordination intent into graph
"""

import json
import re
import socket
import sys

DAEMON_PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 7891


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
    return tool_text(send_rpc(sock, "tools/call",
                              {"name": "query", "arguments": {"body": body}}))


def daemon_resolve(sock, name):
    return tool_text(send_rpc(sock, "tools/call",
                              {"name": "resolve_symbol",
                               "arguments": {"name": name}}))


def daemon_inspect(sock, eid):
    return tool_text(send_rpc(sock, "tools/call",
                              {"name": "inspect",
                               "arguments": {"id": eid}}))


def daemon_claim(sock, left, predicate, right):
    return tool_text(send_rpc(sock, "tools/call",
                              {"name": "claim",
                               "arguments": {"left": left,
                                             "predicate": predicate,
                                             "right": right}}))


def daemon_create_entity(sock):
    return tool_text(send_rpc(sock, "tools/call",
                              {"name": "create_entity", "arguments": {}}))


# ── Internal helpers ──

def _resolve_eid(sock, name):
    text = daemon_resolve(sock, name)
    if "->" not in text:
        return None
    return text.strip().split("->")[-1].strip()


def _get_module(sock, eid):
    text = daemon_query(sock, f"(current-triple {eid} source-module (? m))")
    if text and "?" in text:
        match = re.search(r'\(value:\s*([^)]+)\)', text)
        if match:
            return match.group(1).strip()
    return None


def _get_kind(sock, eid):
    text = daemon_inspect(sock, eid)
    for line in text.split("\n"):
        if "py-form-kind" in line or ("(value:" in line and ("function" in line or "variable" in line or "class" in line)):
            match = re.search(r'\(value:\s*([^)]+)\)', line)
            if match:
                val = match.group(1).strip()
                if val in ("function", "variable", "class"):
                    return val
    return None


def _extract_values(sock, eid):
    text = daemon_inspect(sock, eid)
    body_eid = None
    for line in text.split("\n"):
        if "53 (entity)" in line or "py-body" in line:
            match = re.search(r'(\d+)\s+\(entity\)\s*$', line.strip())
            if match:
                body_eid = match.group(1)
    if not body_eid:
        return None

    body_text = daemon_inspect(sock, body_eid)
    values = []
    for line in body_text.split("\n"):
        if "(value:" in line:
            match = re.search(r'\(value:\s*([^)]+)\)', line)
            if match:
                val = match.group(1).strip()
                if val not in ("list", "set", "dict", "tuple",
                               "binop:+", "binop:-", "binop:*"):
                    values.append(val)
    return values if values else None


def _all_modules(sock):
    """Batch-query all source-module claims. Returns {eid: module_name}."""
    text = daemon_query(sock, "(current-triple (? e) source-module (? m))")
    result = {}
    if not text:
        return result
    for line in text.strip().split("\n"):
        if "?" not in line:
            continue
        e_match = re.search(r'\?e\s*=\s*(\d+)', line)
        m_match = re.search(r'\(value:\s*([^)]+)\)', line)
        if e_match and m_match:
            result[e_match.group(1)] = m_match.group(1).strip()
    return result


def _all_symbols(sock):
    """Query all code entities, deduplicated, with kind and module."""
    text = daemon_query(sock, "(current-triple (? e) py-form-kind (? kind))")
    modules = _all_modules(sock)
    seen = {}
    if not text:
        return seen
    for line in text.strip().split("\n"):
        if "?" not in line:
            continue
        e_match = re.search(r'\?e\s*=\s*(\d+)\s*\(([^)]*)\)', line)
        k_match = re.search(r'\?kind\s*=\s*\d+\s*\(value:\s*([^)]+)\)', line)
        if e_match and k_match:
            name = e_match.group(2)
            if name not in seen:
                eid = e_match.group(1)
                kind = k_match.group(1).strip()
                entry = {"name": name, "kind": kind, "entity": eid}
                mod = modules.get(eid)
                if mod:
                    entry["module"] = mod
                seen[name] = entry
    return seen


# ── Tool handlers ──

def handle_discover(sock, args):
    """Everything about one symbol: kind, module, values, import statement."""
    name = args.get("name", "")
    eid = _resolve_eid(sock, name)
    if not eid:
        return json.dumps({"error": f"Symbol '{name}' not found in the graph."})

    kind = _get_kind(sock, eid)
    modules = _all_modules(sock)
    module = modules.get(eid)

    result = {"name": name, "kind": kind or "unknown"}
    if module:
        result["module"] = module
        result["import"] = f"from {module} import {name}"

    if kind == "variable":
        vals = _extract_values(sock, eid)
        if vals:
            result["values"] = vals

    return json.dumps(result)


def handle_discover_all(sock, args):
    """All symbols with modules. Optionally filter by kind."""
    kind_filter = args.get("kind", "")
    symbols = _all_symbols(sock)

    results = []
    for sym in sorted(symbols.values(), key=lambda s: (s.get("module", ""), s["name"])):
        if kind_filter and sym["kind"] != kind_filter:
            continue
        entry = {"name": sym["name"], "kind": sym["kind"]}
        if "module" in sym:
            entry["module"] = sym["module"]
        if sym["kind"] == "variable":
            vals = _extract_values(sock, sym["entity"])
            if vals:
                entry["values"] = vals
        results.append(entry)

    return json.dumps(results, indent=2)


def handle_dependencies(sock, args):
    """Dependency graph. Optionally filtered to one symbol."""
    symbol = args.get("symbol", "")
    symbols = _all_symbols(sock)
    eid_to_name = {s["entity"]: s["name"] for s in symbols.values()}

    if symbol:
        eid = _resolve_eid(sock, symbol)
        if not eid:
            return json.dumps({"error": f"Symbol '{symbol}' not found."})
        text = daemon_query(sock, f"(py-fn-depends-on (? caller) {eid})")
        callers = []
        if text and "?" in text:
            for line in text.strip().split("\n"):
                m = re.search(r'\?caller\s*=\s*(\d+)', line)
                if m:
                    n = eid_to_name.get(m.group(1))
                    if n:
                        callers.append(n)
        return json.dumps({"symbol": symbol,
                           "depended_on_by": sorted(set(callers))})

    text = daemon_query(sock, "(py-fn-depends-on (? caller) (? callee))")
    deps = {}
    if text and "?" in text:
        for line in text.strip().split("\n"):
            caller_m = re.search(r'\?caller\s*=\s*(\d+)', line)
            callee_m = re.search(r'\?callee\s*=\s*(\d+)', line)
            if caller_m and callee_m:
                cn = eid_to_name.get(caller_m.group(1))
                ce = eid_to_name.get(callee_m.group(1))
                if cn and ce:
                    deps.setdefault(cn, []).append(ce)
    return json.dumps({fn: sorted(set(cs)) for fn, cs in sorted(deps.items())},
                      indent=2)


_intents = []


def handle_declare_intent(sock, args):
    """Declare what a module needs and provides."""
    module = args.get("module", "")
    depends_on = args.get("depends_on", [])
    provides = args.get("provides", [])

    intent = {"module": module, "depends_on": depends_on,
              "provides": provides}
    _intents.append(intent)

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


TOOLS = {
    "discover": {
        "handler": handle_discover,
        "schema": {
            "name": "discover",
            "description": "Everything about one symbol: kind, module, values, and the exact import statement to use. Example: discover('TERMINAL_STATUSES') returns its values and 'from workflow import TERMINAL_STATUSES'.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string",
                             "description": "Symbol name to look up"},
                },
                "required": ["name"],
            },
        },
    },
    "discover_all": {
        "handler": handle_discover_all,
        "schema": {
            "name": "discover_all",
            "description": "List all symbols in the codebase with their kinds, modules, and values. Optionally filter by kind ('function', 'variable', 'class'). This is how you learn what exists.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string",
                             "description": "Optional: 'function', 'variable', or 'class'"},
                },
                "required": [],
            },
        },
    },
    "dependencies": {
        "handler": handle_dependencies,
        "schema": {
            "name": "dependencies",
            "description": "Show the dependency graph — what calls what. Pass a symbol name to see what depends on it, or omit for the full graph.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string",
                               "description": "Optional: symbol to find dependents of"},
                },
                "required": [],
            },
        },
    },
    "declare_intent": {
        "handler": handle_declare_intent,
        "schema": {
            "name": "declare_intent",
            "description": "Declare what your module depends on and what it provides. Written into the shared graph for other agents to see.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "module": {"type": "string",
                               "description": "Module you are building"},
                    "depends_on": {"type": "array",
                                   "items": {"type": "string"},
                                   "description": "Symbols you need"},
                    "provides": {"type": "array",
                                 "items": {"type": "string"},
                                 "description": "Symbols you will define"},
                },
                "required": ["module"],
            },
        },
    },
}


# ── MCP protocol ──

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
                "serverInfo": {"name": "cnf-graph-tools", "version": "0.2"},
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
    sys.stderr.write(f"graph-tools: connecting to daemon on port {DAEMON_PORT}\n")
    sys.stderr.flush()

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(("127.0.0.1", DAEMON_PORT))

    send_rpc(sock, "initialize", {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "graph-tools", "version": "0.2"},
    })

    import time as _time
    for attempt in range(5):
        test = daemon_query(sock,
                            "(current-triple (? e) py-form-kind (? kind))")
        count = sum(1 for l in test.strip().split("\n")
                    if "?" in l) if test else 0
        if count > 0:
            sys.stderr.write(
                f"graph-tools: connected, {count} entities visible\n")
            sys.stderr.flush()
            break
        sys.stderr.write(
            f"graph-tools: attempt {attempt+1}, 0 entities, retrying...\n")
        sys.stderr.flush()
        if attempt < 4:
            sock.close()
            _time.sleep(1)
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect(("127.0.0.1", DAEMON_PORT))
            send_rpc(sock, "initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "graph-tools", "version": "0.2"},
            })

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

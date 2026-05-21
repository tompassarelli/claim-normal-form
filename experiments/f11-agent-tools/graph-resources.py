#!/usr/bin/env python3
"""MCP server with resources — graph data injected into context at startup.

On connect, queries the CNF daemon for all symbols, values, modules,
and dependencies. Exposes them as an MCP resource (zero tool calls to
read). Keeps declare_intent as a write-back tool.
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
    resp = send_rpc(sock, "tools/call",
                    {"name": "query", "arguments": {"body": body}})
    return tool_text(resp)


def daemon_resolve(sock, name):
    resp = send_rpc(sock, "tools/call",
                    {"name": "resolve_symbol", "arguments": {"name": name}})
    return tool_text(resp)


def daemon_inspect(sock, eid):
    resp = send_rpc(sock, "tools/call",
                    {"name": "inspect", "arguments": {"id": eid}})
    return tool_text(resp)


def daemon_claim(sock, left, predicate, right):
    resp = send_rpc(sock, "tools/call",
                    {"name": "claim",
                     "arguments": {"left": left, "predicate": predicate,
                                   "right": right}})
    return tool_text(resp)


def daemon_create_entity(sock):
    resp = send_rpc(sock, "tools/call",
                    {"name": "create_entity", "arguments": {}})
    return tool_text(resp)


# ── Build the resource at startup ──

def _extract_values(sock, eid):
    """Walk entity → py-body → py-has-child to get literal values."""
    inspect_text = daemon_inspect(sock, eid)
    body_eid = None
    for line in inspect_text.split("\n"):
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
                if val not in ("list", "set", "dict", "tuple"):
                    values.append(val)
    return values if values else None


def _get_module(sock, eid):
    text = daemon_query(sock, f"(current-triple {eid} source-module (? m))")
    if text and "?" in text:
        match = re.search(r'\(value:\s*([^)]+)\)', text)
        if match:
            return match.group(1).strip()
    return None


def build_resource(sock):
    """Query the full graph and format as a text resource."""
    query_text = daemon_query(
        sock, "(current-triple (? e) py-form-kind (? kind))")

    seen = {}
    for line in query_text.strip().split("\n"):
        if "?" not in line:
            continue
        e_match = re.search(r'\?e\s*=\s*(\d+)\s*\(([^)]*)\)', line)
        k_match = re.search(
            r'\?kind\s*=\s*\d+\s*\(value:\s*([^)]+)\)', line)
        if e_match and k_match:
            name = e_match.group(2)
            if name not in seen:
                seen[name] = {
                    "eid": e_match.group(1),
                    "name": name,
                    "kind": k_match.group(1).strip(),
                }
    symbols = list(seen.values())

    by_module = {}
    for sym in symbols:
        mod = _get_module(sock, sym["eid"]) or "unknown"
        sym["module"] = mod
        by_module.setdefault(mod, []).append(sym)

    lines = ["=== CODEBASE GRAPH ===", ""]

    for mod in sorted(by_module):
        lines.append(f"--- {mod} ---")
        for sym in sorted(by_module[mod], key=lambda s: s["name"]):
            entry = f"  {sym['name']} ({sym['kind']})"
            if sym["kind"] == "variable":
                vals = _extract_values(sock, sym["eid"])
                if vals and not any(v.startswith("binop:") for v in vals):
                    entry += f" = {json.dumps(vals)}"
            lines.append(entry)
        lines.append("")

    dep_text = daemon_query(
        sock, "(py-fn-depends-on (? caller) (? callee))")
    if dep_text and "?" in dep_text:
        eid_to_name = {s["eid"]: s["name"] for s in symbols}
        deps = {}
        for line in dep_text.strip().split("\n"):
            caller_m = re.search(r'\?caller\s*=\s*(\d+)', line)
            callee_m = re.search(r'\?callee\s*=\s*(\d+)', line)
            if caller_m and callee_m:
                cn = eid_to_name.get(caller_m.group(1))
                ce = eid_to_name.get(callee_m.group(1))
                if cn and ce:
                    deps.setdefault(cn, set()).add(ce)

        if deps:
            lines.append("--- dependencies ---")
            for fn in sorted(deps):
                callees = ", ".join(sorted(deps[fn]))
                lines.append(f"  {fn} -> {callees}")
            lines.append("")

    return "\n".join(lines)


# ── Intent storage (write-back) ──

_intents = []


def handle_declare_intent(sock, args):
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


def handle_list_intents(sock, args):
    return json.dumps(_intents)


TOOLS = {
    "declare_intent": {
        "handler": handle_declare_intent,
        "schema": {
            "name": "declare_intent",
            "description": "Declare what your module depends on and provides. Written into the shared graph so other agents can see.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "module": {"type": "string"},
                    "depends_on": {"type": "array", "items": {"type": "string"}},
                    "provides": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["module"],
            },
        },
    },
    "list_intents": {
        "handler": handle_list_intents,
        "schema": {
            "name": "list_intents",
            "description": "List all declared intents from all agents.",
            "inputSchema": {"type": "object", "properties": {}, "required": []},
        },
    },
}

RESOURCE_TEXT = ""


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
                "capabilities": {
                    "tools": {"listChanged": False},
                    "resources": {"listChanged": False},
                },
                "serverInfo": {"name": "cnf-graph-resources", "version": "0.1"},
            },
        }

    if method == "notifications/initialized":
        return None

    if method == "resources/list":
        return {
            "jsonrpc": "2.0", "id": req_id,
            "result": {
                "resources": [{
                    "uri": "cnf://graph",
                    "name": "Codebase Graph",
                    "description": "All symbols, values, modules, and dependencies from the semantic graph.",
                    "mimeType": "text/plain",
                }],
            },
        }

    if method == "resources/read":
        uri = params.get("uri", "")
        if uri == "cnf://graph":
            return {
                "jsonrpc": "2.0", "id": req_id,
                "result": {
                    "contents": [{
                        "uri": "cnf://graph",
                        "mimeType": "text/plain",
                        "text": RESOURCE_TEXT,
                    }],
                },
            }
        return {
            "jsonrpc": "2.0", "id": req_id,
            "error": {"code": -32602, "message": f"Unknown resource: {uri}"},
        }

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
                "result": {"content": [{"type": "text", "text": result_text}]},
            }
        except Exception as e:
            return {
                "jsonrpc": "2.0", "id": req_id,
                "result": {
                    "content": [{"type": "text",
                                 "text": f"Error: {e}"}],
                    "isError": True,
                },
            }

    return {
        "jsonrpc": "2.0", "id": req_id,
        "error": {"code": -32601, "message": f"Unknown method: {method}"},
    }


def main():
    global RESOURCE_TEXT
    sys.stderr.write(
        f"graph-resources: connecting to daemon on port {DAEMON_PORT}\n")
    sys.stderr.flush()

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(("127.0.0.1", DAEMON_PORT))

    send_rpc(sock, "initialize", {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "graph-resources", "version": "0.1"},
    })

    sys.stderr.write("graph-resources: building resource...\n")
    sys.stderr.flush()
    RESOURCE_TEXT = build_resource(sock)
    sys.stderr.write(
        f"graph-resources: ready ({len(RESOURCE_TEXT)} chars)\n")
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

#!/usr/bin/env python3
"""Thin MCP passthrough — 2 tools: query + claim.

No domain wrappers. The agent reasons in Datalog directly,
guided by schema documentation in the prompt.
"""

import json
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


TOOLS_SCHEMA = [
    {
        "name": "query",
        "description": "Run a Datalog query against the semantic graph. Returns matching facts. Use (? var) for variables. Examples: (current-triple (? e) py-form-kind \"function\") finds all functions. (py-fn-depends-on (? caller) (? callee)) finds all call dependencies.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "body": {
                    "type": "string",
                    "description": "Datalog query expression"
                }
            },
            "required": ["body"],
        },
    },
    {
        "name": "claim",
        "description": "Assert a new fact into the graph. Creates a claim (left, predicate, right). Use for declaring intent, dependencies, or any new knowledge. Example: claim(left=\"my-module\", predicate=\"depends-on\", right='\"TERMINAL_STATUSES\"')",
        "inputSchema": {
            "type": "object",
            "properties": {
                "left": {"type": "string", "description": "Subject entity or ID"},
                "predicate": {"type": "string", "description": "Predicate name"},
                "right": {"type": "string", "description": "Object entity, ID, or quoted value"},
            },
            "required": ["left", "predicate", "right"],
        },
    },
    {
        "name": "resolve_symbol",
        "description": "Resolve a name to its entity ID. Use this to get the entity ID of a known symbol before querying its properties. Example: resolve_symbol('TERMINAL_STATUSES') -> entity 193",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Symbol name to resolve"},
            },
            "required": ["name"],
        },
    },
    {
        "name": "inspect",
        "description": "Show all claims about an entity. Takes an entity ID and returns all facts where that entity appears as subject. Use after resolve_symbol to see an entity's properties.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "Entity ID to inspect"},
            },
            "required": ["id"],
        },
    },
]


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
                "serverInfo": {"name": "cnf-graph-raw", "version": "0.1"},
            },
        }

    if method == "notifications/initialized":
        return None

    if method == "tools/list":
        return {
            "jsonrpc": "2.0", "id": req_id,
            "result": {"tools": TOOLS_SCHEMA},
        }

    if method == "tools/call":
        tool_name = params.get("name", "")
        tool_args = params.get("arguments", {})

        if tool_name in ("query", "claim", "resolve_symbol", "inspect"):
            resp = send_rpc(sock, "tools/call", {
                "name": tool_name,
                "arguments": tool_args,
            })
            result_text = tool_text(resp)
            return {
                "jsonrpc": "2.0", "id": req_id,
                "result": {"content": [{"type": "text", "text": result_text}]},
            }

        return {
            "jsonrpc": "2.0", "id": req_id,
            "result": {
                "content": [{"type": "text", "text": f"Unknown tool: {tool_name}"}],
                "isError": True,
            },
        }

    return {
        "jsonrpc": "2.0", "id": req_id,
        "error": {"code": -32601, "message": f"Unknown method: {method}"},
    }


def main():
    sys.stderr.write(f"graph-raw: connecting to daemon on port {DAEMON_PORT}\n")
    sys.stderr.flush()

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(("127.0.0.1", DAEMON_PORT))

    send_rpc(sock, "initialize", {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "graph-raw", "version": "0.1"},
    })

    sys.stderr.write("graph-raw: connected, ready\n")
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

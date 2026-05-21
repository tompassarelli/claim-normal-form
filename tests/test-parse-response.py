#!/usr/bin/env python3
"""Check parse_program response format."""
import sys, json, socket
sys.path.insert(0, "experiments/e23-concurrent-agents")
from runner import start_daemon, stop_daemon, send_rpc, get_tool_text, STARTING_PROGRAM

proc, backup = start_daemon()
try:
    sock = socket.socket()
    sock.connect(("localhost", 7892))
    send_rpc(sock, "initialize", {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "test", "version": "0.1"},
    })
    send_rpc(sock, "tools/call", {"name": "reset", "arguments": {}})
    resp = send_rpc(sock, "tools/call", {
        "name": "parse_program",
        "arguments": {"source": STARTING_PROGRAM, "language": "cnf"},
    })
    text = get_tool_text(resp)
    print("=== parse_program response ===")
    print(text[:2000])
    sock.close()
finally:
    stop_daemon(proc, backup)

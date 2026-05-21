#!/usr/bin/env python3
"""Debug: check parse text line format."""
import sys, json, socket, re
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

    lines = text.split("\n")
    print(f"Total lines: {len(lines)}")
    print(f"First 5 lines (repr):")
    for line in lines[:5]:
        print(f"  {repr(line)}")

    fn_ids = []
    for line in lines:
        m = re.match(r'(\d+):\s+\S+\s+\(defn\)', line)
        if m:
            fn_ids.append(m.group(1))
    print(f"\nMatched {len(fn_ids)} IDs")
    if fn_ids:
        print(f"  First 3: {fn_ids[:3]}")

    sock.close()
finally:
    stop_daemon(proc, backup)

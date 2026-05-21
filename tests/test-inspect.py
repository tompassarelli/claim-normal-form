#!/usr/bin/env python3
"""Quick check: what does inspect return for entity 491 (ratio)?"""
import sys, json, socket, re, shutil, subprocess, time, os
from pathlib import Path

sys.path.insert(0, "experiments/e23-concurrent-agents")
from runner import start_daemon, stop_daemon, init_graph, send_rpc, get_tool_text

proc, backup = start_daemon()
try:
    init_graph()
    sock = socket.socket()
    sock.connect(("localhost", 7892))
    send_rpc(sock, "initialize", {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "test", "version": "0.1"},
    })

    for eid in ["491", "2085", "222"]:
        resp = send_rpc(sock, "tools/call", {
            "name": "inspect",
            "arguments": {"id": eid},
        })
        text = get_tool_text(resp)
        print(f"\n=== Entity {eid} ===")
        print(text[:500])

    sock.close()
finally:
    stop_daemon(proc, backup)

#!/usr/bin/env python3
"""Test daemon MVCC cross-connection snapshot visibility.

The bug: Connection A parses a program (2000+ objects). Connection B
connects, sends initialize, then queries status. Before the fix,
Connection B's initialize clobbered the committed snapshot, so B saw
the pre-parse state (166 objects) instead of A's parsed state.

Usage:
    python tests/test-daemon-mvcc.py
"""

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent.resolve()
SERVER_RKT = ROOT / "cnf-lib" / "server.rkt"
PORT = 7893

PROGRAM = """\
(defn add (a b) (+ a b))
(defn sub (a b) (- a b))
(defn mul (a b) (* a b))
(defn div-unsafe (a b) (/ a b))
(defn double (x) (mul x 2))
(defn square (x) (mul x x))
(defn inc (x) (add x 1))
(defn dec (x) (sub x 1))
(defn safe-div (a b) (if (= b 0) 0 (/ a b)))
(defn compute (a b) (add (mul a b) (sub a b)))
"""


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


def send_notification(sock, method, params):
    """Send a JSON-RPC notification (no id, no response expected)."""
    msg = json.dumps({"jsonrpc": "2.0", "method": method, "params": params})
    sock.sendall((msg + "\n").encode())


def tool_text(resp):
    return resp.get("result", {}).get("content", [{}])[0].get("text", "")


def kill_port(port):
    try:
        result = subprocess.run(["ss", "-tlnp"], capture_output=True, text=True)
        for line in result.stdout.splitlines():
            if f":{port}" in line:
                m = re.search(r'pid=(\d+)', line)
                if m:
                    os.kill(int(m.group(1)), 9)
                    time.sleep(0.5)
    except Exception:
        pass


def wait_for_port(port, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            s = socket.socket()
            s.settimeout(1)
            s.connect(("localhost", port))
            s.close()
            return True
        except (ConnectionRefusedError, OSError):
            time.sleep(0.2)
    return False


def start_daemon():
    kill_port(PORT)
    checkpoint = Path.home() / ".cnf" / "checkpoint.json"
    backup = None
    if checkpoint.exists():
        backup = checkpoint.with_suffix(".json.mvcc-test-bak")
        shutil.copy2(checkpoint, backup)
        checkpoint.unlink()

    proc = subprocess.Popen(
        ["racket", str(SERVER_RKT), "--daemon", str(PORT)],
        stderr=subprocess.PIPE, text=True,
    )
    if not wait_for_port(PORT):
        proc.kill()
        raise RuntimeError("Daemon failed to start")
    return proc, backup


def stop_daemon(proc, backup):
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
    checkpoint = Path.home() / ".cnf" / "checkpoint.json"
    if backup and backup.exists():
        shutil.move(str(backup), str(checkpoint))


def extract_object_count(status_text):
    m = re.search(r'Objects:\s*(\d+)', status_text)
    return int(m.group(1)) if m else None


def test_cross_connection_visibility():
    """Connection A writes, Connection B reads — B must see A's state."""
    print("Test: cross-connection snapshot visibility")

    proc, backup = start_daemon()
    try:
        # --- Connection A: initialize + parse program ---
        conn_a = socket.socket()
        conn_a.connect(("localhost", PORT))

        send_rpc(conn_a, "initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test-conn-a", "version": "0.1"},
        })
        send_notification(conn_a, "notifications/initialized", {})

        send_rpc(conn_a, "tools/call", {"name": "reset", "arguments": {}})
        send_rpc(conn_a, "tools/call", {
            "name": "parse_program",
            "arguments": {"source": PROGRAM, "language": "cnf"},
        })

        resp_a = send_rpc(conn_a, "tools/call", {"name": "status", "arguments": {}})
        status_a = tool_text(resp_a)
        count_a = extract_object_count(status_a)
        print(f"  Connection A: {count_a} objects")
        assert count_a and count_a > 50, f"Connection A parse failed: {status_a}"

        # --- Connection B: initialize + read status ---
        conn_b = socket.socket()
        conn_b.connect(("localhost", PORT))

        send_rpc(conn_b, "initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test-conn-b", "version": "0.1"},
        })
        send_notification(conn_b, "notifications/initialized", {})

        resp_b = send_rpc(conn_b, "tools/call", {"name": "status", "arguments": {}})
        status_b = tool_text(resp_b)
        count_b = extract_object_count(status_b)
        print(f"  Connection B: {count_b} objects")

        assert count_b == count_a, (
            f"MVCC BUG: Connection B sees {count_b} objects, "
            f"expected {count_a} (Connection A's state)"
        )
        print("  PASS: Connection B sees Connection A's state")

        conn_a.close()
        conn_b.close()

    finally:
        stop_daemon(proc, backup)


def test_write_from_second_connection():
    """Connection B writes AFTER Connection A — committed reflects both."""
    print("\nTest: write from second connection builds on first")

    proc, backup = start_daemon()
    try:
        # --- Connection A: parse program ---
        conn_a = socket.socket()
        conn_a.connect(("localhost", PORT))
        send_rpc(conn_a, "initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test-conn-a", "version": "0.1"},
        })
        send_notification(conn_a, "notifications/initialized", {})
        send_rpc(conn_a, "tools/call", {"name": "reset", "arguments": {}})
        send_rpc(conn_a, "tools/call", {
            "name": "parse_program",
            "arguments": {"source": PROGRAM, "language": "cnf"},
        })
        resp_a = send_rpc(conn_a, "tools/call", {"name": "status", "arguments": {}})
        count_a = extract_object_count(tool_text(resp_a))
        print(f"  Connection A: {count_a} objects after parse")

        # --- Connection B: add a function ---
        conn_b = socket.socket()
        conn_b.connect(("localhost", PORT))
        send_rpc(conn_b, "initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test-conn-b", "version": "0.1"},
        })
        send_notification(conn_b, "notifications/initialized", {})
        resp_add = send_rpc(conn_b, "tools/call", {
            "name": "add_function",
            "arguments": {"source": "(defn triple (x) (mul x 3))"},
        })
        add_text = tool_text(resp_add)
        print(f"  Connection B add_function: {add_text[:80]}")

        resp_b = send_rpc(conn_b, "tools/call", {"name": "status", "arguments": {}})
        count_b = extract_object_count(tool_text(resp_b))
        print(f"  Connection B: {count_b} objects after add")

        assert count_b and count_b > count_a, (
            f"Connection B add_function did not grow the graph: "
            f"{count_b} <= {count_a}"
        )
        print("  PASS: Connection B's write built on Connection A's state")

        # --- Connection C: verify the accumulated state ---
        conn_c = socket.socket()
        conn_c.connect(("localhost", PORT))
        send_rpc(conn_c, "initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test-conn-c", "version": "0.1"},
        })
        send_notification(conn_c, "notifications/initialized", {})
        resp_c = send_rpc(conn_c, "tools/call", {"name": "status", "arguments": {}})
        count_c = extract_object_count(tool_text(resp_c))
        print(f"  Connection C: {count_c} objects (should match B)")

        assert count_c == count_b, (
            f"Connection C sees {count_c} objects, expected {count_b}"
        )

        print("  PASS: Connection C sees both A's and B's changes")

        conn_a.close()
        conn_b.close()
        conn_c.close()

    finally:
        stop_daemon(proc, backup)


if __name__ == "__main__":
    ok = True
    try:
        test_cross_connection_visibility()
    except AssertionError as e:
        print(f"  FAIL: {e}")
        ok = False

    try:
        test_write_from_second_connection()
    except AssertionError as e:
        print(f"  FAIL: {e}")
        ok = False

    if ok:
        print("\nAll MVCC tests passed.")
    else:
        print("\nSome tests FAILED.")
        sys.exit(1)

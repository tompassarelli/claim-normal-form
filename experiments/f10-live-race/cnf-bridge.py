#!/usr/bin/env python3
"""Lightweight MCP bridge — forwards JSON-RPC between stdio and TCP daemon.

Replaces `racket server.rkt --connect <port>` for agent subprocesses.
Starts instantly (no racket compilation), enabling 6+ simultaneous bridges.
"""
import socket
import sys
import threading


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 7891

    sys.stderr.write(f"cnf-bridge-py: connecting to port {port}\n")
    sys.stderr.flush()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(("127.0.0.1", port))
    sys.stderr.write(f"cnf-bridge-py: connected\n")
    sys.stderr.flush()
    sf = sock.makefile("rw", buffering=1)

    def tcp_to_stdout():
        try:
            for line in sf:
                sys.stdout.write(line)
                sys.stdout.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass

    t = threading.Thread(target=tcp_to_stdout, daemon=True)
    t.start()

    try:
        for line in sys.stdin:
            if line.strip():
                sf.write(line)
                sf.flush()
    except (BrokenPipeError, KeyboardInterrupt):
        pass
    finally:
        sock.close()


if __name__ == "__main__":
    main()

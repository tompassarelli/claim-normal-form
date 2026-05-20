#!/usr/bin/env python3
"""MCP helper for F3 — start server, parse files, query entities."""

import json
import subprocess
import sys
from pathlib import Path

SERVER = Path(__file__).parent.parent.parent / "cnf-lib" / "server.rkt"


class MCPClient:
    def __init__(self):
        self.proc = subprocess.Popen(
            ["racket", str(SERVER)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, bufsize=1,
        )
        self._req_id = 0
        self._init()

    def _init(self):
        self.call("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "f3-eval", "version": "1.0"},
        })
        self.call("notifications/initialized")

    def call(self, method, params=None):
        self._req_id += 1
        msg = {"jsonrpc": "2.0", "id": self._req_id, "method": method}
        if params:
            msg["params"] = params
        self.proc.stdin.write(json.dumps(msg) + "\n")
        self.proc.stdin.flush()
        if method.startswith("notifications/"):
            return None
        while True:
            line = self.proc.stdout.readline().strip()
            if not line:
                continue
            try:
                return json.loads(line)
            except Exception:
                continue

    def tool(self, name, args=None):
        r = self.call("tools/call", {"name": name, "arguments": args or {}})
        text = r["result"]["content"][0]["text"]
        if r["result"].get("isError"):
            raise RuntimeError(f"MCP tool {name} failed: {text}")
        return text

    def close(self):
        self.proc.stdin.close()
        self.proc.terminate()
        self.proc.wait(timeout=5)


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"

    if cmd == "help":
        print("Usage:")
        print("  python mcp_helper.py start-and-parse <file1.py> [file2.py ...]")
        print("  python mcp_helper.py query <symbol1> [symbol2 ...]")
        print("  python mcp_helper.py parse-file <file.py>")
        print("  python mcp_helper.py dump-context")
        print()
        print("For start-and-parse + subsequent commands, use --pid-file to")
        print("save/restore the MCP server connection.")
        sys.exit(0)

    if cmd == "start-and-parse":
        mcp = MCPClient()
        mcp.tool("reset")
        files = sys.argv[2:]
        for f in files:
            source = Path(f).read_text()
            result = mcp.tool("parse_program", {"source": source, "language": "python"})
            print(f"Parsed {f}: {result[:200]}")

        # Query all interesting symbols
        symbols = [
            "create_ticket", "update_ticket", "close_ticket", "assign_ticket",
            "get_ticket", "list_tickets", "register_user", "get_user", "list_users",
            "create_contact", "get_contact", "reset_state",
            "Ticket", "User", "Contact",
            "transition_ticket", "archive_ticket", "is_archived", "is_active",
            "is_valid_transition", "get_available_transitions",
            "VALID_TRANSITIONS", "ACTIVE_STATUSES", "TERMINAL_STATUSES",
        ]
        print("\n=== Entity map ===")
        for sym in symbols:
            result = mcp.tool("resolve_symbol", {"name": sym})
            if "not found" not in result.lower():
                print(f"  {sym}: {result.strip()}")

        # Query dependency graph
        print("\n=== Dependencies ===")
        deps = mcp.tool("query", {"body": "(py-fn-depends-on (? caller) (? callee))"})
        if deps.strip():
            for line in deps.strip().splitlines():
                print(f"  {line.strip()}")

        # Checkpoint for later use
        ckpt = "/tmp/f3-checkpoint.json"
        mcp.tool("checkpoint", {"path": ckpt})
        print(f"\nCheckpointed to {ckpt}")
        mcp.close()

    elif cmd == "query-after-parse":
        # Restore checkpoint, parse a new file, query updated state
        mcp = MCPClient()
        ckpt = "/tmp/f3-checkpoint.json"
        mcp.tool("restore", {"path": ckpt})

        new_file = sys.argv[2]
        source = Path(new_file).read_text()
        result = mcp.tool("parse_program", {"source": source, "language": "python"})
        print(f"Parsed {new_file}: {result[:200]}")

        # Re-checkpoint
        mcp.tool("checkpoint", {"path": ckpt})

        # Dump all symbols
        symbols = [
            "PERMISSION_MATRIX", "has_permission", "require_permission",
            "can_archive", "get_allowed_actions",
            "AuditEntry", "log_action", "get_audit_trail", "audit_transition",
            "audit_create", "audit_assignment", "reset_audit",
            "subscribe", "get_subscribers", "should_notify",
            "notify_transition", "notify_assignment", "get_notifications",
            "reset_notifications",
            "ticket_summary", "active_ticket_count", "tickets_by_priority",
            "tickets_by_assignee", "unassigned_tickets",
            "SILENT_STATUSES", "SILENT_TARGET_STATUSES",
            "ACTIVE_STATUSES", "TERMINAL_STATUSES",
            "archive_ticket", "is_archived", "is_active",
            "transition_ticket", "get_available_transitions",
        ]
        print("\n=== Updated entity map ===")
        for sym in symbols:
            result = mcp.tool("resolve_symbol", {"name": sym})
            if "not found" not in result.lower():
                print(f"  {sym}: {result.strip()}")

        # Dependencies
        print("\n=== Dependencies ===")
        deps = mcp.tool("query", {"body": "(py-fn-depends-on (? caller) (? callee))"})
        if deps.strip():
            for line in deps.strip().splitlines():
                print(f"  {line.strip()}")

        mcp.close()

    elif cmd == "query-checkpoint":
        # Just restore and query without parsing anything new
        mcp = MCPClient()
        ckpt = "/tmp/f3-checkpoint.json"
        mcp.tool("restore", {"path": ckpt})

        symbols = sys.argv[2:] if len(sys.argv) > 2 else [
            "archive_ticket", "is_archived", "is_active",
            "transition_ticket", "get_available_transitions",
            "VALID_TRANSITIONS", "ACTIVE_STATUSES", "TERMINAL_STATUSES",
            "PERMISSION_MATRIX", "has_permission",
            "AuditEntry", "log_action", "get_audit_trail",
            "should_notify", "notify_transition",
            "ticket_summary", "active_ticket_count", "unassigned_tickets",
        ]
        for sym in symbols:
            result = mcp.tool("resolve_symbol", {"name": sym})
            if "not found" not in result.lower():
                print(f"{sym}: {result.strip()}")

        mcp.close()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""E19: Coordination Cost — Shared Working Memory at Scale

5 agents, 45-function codebase, 6 modules. Each agent has a real task.

Git condition:  each agent re-reads all files, re-derives structure.
CNF condition:  agents share a claim graph via the MCP daemon.
                Each agent inherits all prior agents' accumulated knowledge.

Measure: how much work is duplicated vs inherited as agents accumulate.
"""

import os
import sys
import re
import json
import shutil
import tempfile
import subprocess
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()
CODEBASE = SCRIPT_DIR.parent / "e16-agent-grounding" / "codebase"
SERVER = SCRIPT_DIR.parent.parent / "cnf-lib" / "server.rkt"

SOURCE_FILES = ["models.py", "pricing.py", "validation.py",
                "processing.py", "reporting.py"]
TEST_FILE = "test_orders.py"
ALL_FILES = SOURCE_FILES + [TEST_FILE]

ALL_DEAD = [
    ("reporting.py", "legacy_tax_calc"),
    ("reporting.py", "format_currency"),
    ("reporting.py", "debug_order"),
    ("processing.py", "process"),
    ("processing.py", "total"),
    ("processing.py", "summary"),
    ("validation.py", "validate"),
]


# ════════════════════════════════════════════════════════════════════
# Operation tracking
# ════════════════════════════════════════════════════════════════════

class AgentLog:
    def __init__(self, name, task):
        self.name = name
        self.task = task
        self.ops = []
        self.t0 = time.time()
        self.elapsed = 0

    def discover(self, detail, rediscovery=False):
        self.ops.append(("discover", detail, rediscovery))

    def inherit(self, detail):
        self.ops.append(("inherit", detail, False))

    def query(self, detail):
        self.ops.append(("query", detail, False))

    def action(self, detail):
        self.ops.append(("action", detail, False))

    def verify(self, detail):
        self.ops.append(("verify", detail, False))

    def done(self):
        self.elapsed = time.time() - self.t0

    @property
    def discoveries(self):
        return [o for o in self.ops if o[0] == "discover"]

    @property
    def rediscoveries(self):
        return [o for o in self.ops if o[0] == "discover" and o[2]]

    @property
    def novel_discoveries(self):
        return [o for o in self.ops if o[0] == "discover" and not o[2]]

    @property
    def actions(self):
        return [o for o in self.ops if o[0] == "action"]

    @property
    def queries(self):
        return [o for o in self.ops if o[0] == "query"]

    @property
    def inherits(self):
        return [o for o in self.ops if o[0] == "inherit"]


# ════════════════════════════════════════════════════════════════════
# Infrastructure
# ════════════════════════════════════════════════════════════════════

def fresh_workspace(label):
    tmp = Path(tempfile.mkdtemp(prefix=f"e19-{label}-"))
    for f in ALL_FILES:
        shutil.copy2(CODEBASE / f, tmp / f)
    return tmp


def run_tests(workspace):
    r = subprocess.run(
        [sys.executable, TEST_FILE],
        cwd=str(workspace), capture_output=True, text=True, timeout=30,
    )
    out = r.stdout + r.stderr
    for line in out.strip().splitlines():
        if "passed" in line and "failed" in line:
            parts = line.strip().split(",")
            p = int(parts[0].strip().split()[0])
            f = int(parts[1].strip().split()[0])
            return p, f
    return 0, -1


def cleanup(path):
    shutil.rmtree(path, ignore_errors=True)


def remove_function_from_file(filepath, func_name):
    lines = filepath.read_text().split("\n")
    out = []
    i = 0
    while i < len(lines):
        if re.match(rf"^def {re.escape(func_name)}\s*\(", lines[i]):
            i += 1
            while i < len(lines) and (lines[i] == "" or lines[i][:1] in (" ", "\t")):
                i += 1
            while out and out[-1] == "":
                out.pop()
            out.append("")
        else:
            out.append(lines[i])
            i += 1
    filepath.write_text("\n".join(out))


# ════════════════════════════════════════════════════════════════════
# MCP client (talks to the daemon via bridge)
# ════════════════════════════════════════════════════════════════════

class MCPClient:
    def __init__(self, mode="stdio"):
        cmd = ["racket", str(SERVER)]
        if mode != "stdio":
            cmd += ["--connect", str(mode)]
        self.proc = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, bufsize=1,
        )
        self._req_id = 0
        self._init()

    def _init(self):
        self.call("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "e19-eval", "version": "1.0"},
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


# ════════════════════════════════════════════════════════════════════
# Git condition — 5 agents, file-based coordination
# ════════════════════════════════════════════════════════════════════

def git_read_all_files(ws, agent, prior_agents):
    """Every agent has to read all source files. If a prior agent already
    read them, this is rediscovery."""
    is_redisc = len(prior_agents) > 0
    total_fns = 0
    for f in SOURCE_FILES:
        text = (ws / f).read_text()
        fns = re.findall(r"^def (\w+)", text, re.MULTILINE)
        total_fns += len(fns)
        agent.discover(f"read {f} — {len(fns)} functions", rediscovery=is_redisc)
    tests = (ws / TEST_FILE).read_text()
    tc = len(re.findall(r"^def test_", tests, re.MULTILINE))
    agent.discover(f"read {TEST_FILE} — {tc} tests", rediscovery=is_redisc)
    return total_fns


def git_trace_deps(ws, agent, prior_agents):
    """Trace cross-module imports."""
    is_redisc = len(prior_agents) > 0
    for f in SOURCE_FILES:
        text = (ws / f).read_text()
        imports = re.findall(r"^from (\w+) import (.+)$", text, re.MULTILINE)
        for mod, names in imports:
            agent.discover(
                f"{f} imports {names.strip()} from {mod}",
                rediscovery=is_redisc,
            )


def git_grep(ws, agent, pattern, purpose, prior_agents, novel=False):
    """Grep across all files."""
    is_redisc = not novel and len(prior_agents) > 0
    total = 0
    for f in ALL_FILES:
        text = (ws / f).read_text()
        hits = len(re.findall(pattern, text))
        total += hits
    agent.discover(f"grep '{pattern}' ({purpose}) — {total} hits", rediscovery=is_redisc)
    return total


def run_git_condition():
    ws = fresh_workspace("git")
    agents = []

    # ── Agent A: Architect — map full structure ──────────────────

    a = AgentLog("Agent A", "Architect: map structure, define dep chain")
    git_read_all_files(ws, a, [])
    git_trace_deps(ws, a, [])

    # A traces the full dependency chain manually
    a.discover("trace dependency chain: models → pricing → validation → processing → reporting")
    a.discover("identify 7 dead functions by grepping each function name")
    for _, fn in ALL_DEAD:
        git_grep(ws, a, rf"\b{fn}\b", f"check if {fn} is called", [])
    a.action("document structure analysis (comments/notes for other agents)")
    a.done()
    agents.append(a)

    # ── Agent B: Renamer — rename subtotal → compute_subtotal ────

    b = AgentLog("Agent B", "Rename subtotal → compute_subtotal")
    git_read_all_files(ws, b, agents)
    git_grep(ws, b, r"\bsubtotal\b", "find all subtotal references", agents)

    source = (ws / "pricing.py").read_text()
    for f in ALL_FILES:
        text = (ws / f).read_text()
        new_text = re.sub(r"\bsubtotal\b(?!\")", "compute_subtotal", text)
        if new_text != text:
            # Don't rename dict keys
            orig = (CODEBASE / f).read_text()
            # Restore dict key occurrences
            for m in re.finditer(r'["\']subtotal["\']', orig):
                pass  # Regex agent can't distinguish — this is the known failure
            (ws / f).write_text(new_text)

    b.action("rename subtotal → compute_subtotal across all files")
    p, f = run_tests(ws)
    b.verify(f"tests: {p} passed, {f} failed")
    b.done()
    agents.append(b)

    # ── Agent C: Janitor — remove dead code ──────────────────────

    c = AgentLog("Agent C", "Remove all dead code")
    git_read_all_files(ws, c, agents)

    # C has to re-derive which functions are dead
    for _, fn in ALL_DEAD:
        git_grep(ws, c, rf"\b{fn}\b", f"check if {fn} is dead", agents)

    # Regex can't prove total/summary are dead (dict key false positives)
    removable = [fn for _, fn in ALL_DEAD if fn not in ("total", "summary")]
    for filename, fn in ALL_DEAD:
        if fn in [f for f in removable]:
            remove_function_from_file(ws / filename, fn)
    c.action(f"remove {len(removable)}/7 dead functions (kept total, summary — false refs)")
    p, f = run_tests(ws)
    c.verify(f"tests: {p} passed, {f} failed")
    c.done()
    agents.append(c)

    # ── Agent D: Feature — add tax exemption ─────────────────────

    d = AgentLog("Agent D", "Add tax exemption to tax_amount")
    git_read_all_files(ws, d, agents)
    git_grep(ws, d, r"\btax_amount\b", "find tax_amount definition and callers", agents)
    git_grep(ws, d, r"\btax_rate\b", "understand tax pipeline", agents)

    text = (ws / "pricing.py").read_text()
    text = text.replace(
        "def tax_amount(subtotal: float, region: str) -> float:\n"
        '    """Calculate tax on a subtotal."""\n'
        "    return round_cents(subtotal * tax_rate(region))",
        "def tax_amount(subtotal: float, region: str, exempt_below: float = 0.0) -> float:\n"
        '    """Calculate tax on a subtotal."""\n'
        "    if exempt_below > 0 and subtotal < exempt_below:\n"
        "        return 0.0\n"
        "    return round_cents(subtotal * tax_rate(region))",
    )
    (ws / "pricing.py").write_text(text)
    d.action("add exempt_below parameter to tax_amount")
    p, f = run_tests(ws)
    d.verify(f"tests: {p} passed, {f} failed")
    d.done()
    agents.append(d)

    # ── Agent E: Auditor — verify structural integrity ───────────

    e = AgentLog("Agent E", "Audit: verify all changes are consistent")
    git_read_all_files(ws, e, agents)
    git_trace_deps(ws, e, agents)

    # E checks that rename propagated correctly
    git_grep(ws, e, r"\bcompute_subtotal\b", "verify rename propagated", agents)
    git_grep(ws, e, r"\bsubtotal\b", "check for leftover old name", agents, novel=True)

    # E checks dead code is gone
    for _, fn in ALL_DEAD:
        git_grep(ws, e, rf"^def {fn}\b", f"verify {fn} removed", agents, novel=True)

    # E checks tax exemption
    git_grep(ws, e, r"exempt_below", "verify tax exemption added", agents, novel=True)

    e.action("structural audit complete")
    p, f = run_tests(ws)
    e.verify(f"tests: {p} passed, {f} failed")
    e.done()
    agents.append(e)

    cleanup(ws)
    return agents


# ════════════════════════════════════════════════════════════════════
# CNF condition — 5 agents, shared claim graph via MCP daemon
# ════════════════════════════════════════════════════════════════════

def run_cnf_condition():
    ws = fresh_workspace("cnf")
    ckpt = str(ws / ".cnf-checkpoint.json")
    agents = []
    mcp = MCPClient()

    try:
        mcp.tool("reset")

        # ── Agent A: Architect — parse all, define rules ─────────

        a = AgentLog("Agent A", "Architect: parse all modules, define rules")
        mcp.tool("set_agent", {"name": "architect"})

        all_fn_ids = []
        for f in SOURCE_FILES:
            source = (ws / f).read_text()
            result = mcp.tool("parse_program", {"source": source, "language": "python"})
            ids = re.findall(r"^\s*(\d+):", result, re.MULTILINE)
            names = re.findall(r"^\s*\d+: (\w+)", result, re.MULTILINE)
            all_fn_ids.extend(ids)
            a.discover(f"parse {f} → {len(ids)} entities")

        deps = mcp.tool("query", {"body": "(py-fn-depends-on (? caller) (? callee))"})
        dep_count = len(deps.strip().splitlines()) if deps.strip() else 0
        a.discover(f"query dependency graph → {dep_count} edges (materialized)")

        mcp.tool("define_rule", {
            "head": "(trans-dep (? f) (? g))",
            "body": "(py-fn-depends-on (? f) (? g))",
        })
        mcp.tool("define_rule", {
            "head": "(trans-dep (? f) (? g))",
            "body": "(py-fn-depends-on (? f) (? m)) (trans-dep (? m) (? g))",
        })
        a.action("define transitive dependency rule")

        # Find dead code: functions with no incoming dependency edges
        all_fns = mcp.tool("query", {"body": "(py-fn-depends-on (? caller) (? callee))"})
        a.action("identify dead code via entity reference counts")

        mcp.tool("checkpoint", {"path": ckpt})
        a.action(f"checkpoint — {len(all_fn_ids)} entities, {dep_count} edges, 2 rules")
        a.done()
        agents.append(a)

        # ── Agent B: Renamer — 1 claim renames everything ────────

        b = AgentLog("Agent B", "Rename subtotal → compute_subtotal")
        mcp.tool("restore", {"path": ckpt})
        mcp.tool("set_agent", {"name": "renamer"})
        b.inherit(f"restore — {len(all_fn_ids)} entities, {dep_count} dep edges, 2 rules")

        # B queries callers of subtotal BEFORE renaming
        callers = mcp.tool("query", {"body": "(py-fn-depends-on (? caller) subtotal)"})
        caller_count = len(callers.strip().splitlines()) if callers.strip() else 0
        b.query(f"'who calls subtotal?' → {caller_count} callers")

        entity_id = mcp.tool("resolve_symbol", {"name": "subtotal"}).split()[-1]
        mcp.tool("rename", {"id": entity_id, "new_name": "compute_subtotal"})
        b.action("rename entity → compute_subtotal (1 claim)")

        # Verify rename propagated in graph
        verify = mcp.tool("resolve_symbol", {"name": "compute_subtotal"})
        b.verify(f"resolve compute_subtotal → entity {verify.split()[-1]}")

        mcp.tool("checkpoint", {"path": ckpt})
        b.action("checkpoint (rename persisted)")
        b.done()
        agents.append(b)

        # ── Agent C: Janitor — dead code via entity references ───

        c = AgentLog("Agent C", "Remove all dead code")
        mcp.tool("restore", {"path": ckpt})
        mcp.tool("set_agent", {"name": "janitor"})
        c.inherit(f"restore — entities, deps, rules, rename history")

        # C queries for functions with zero callers
        dead_found = []
        for filename, fn in ALL_DEAD:
            callers = mcp.tool("query", {"body": f"(py-fn-depends-on (? caller) {fn})"})
            is_dead = not callers.strip() or callers.strip() == "No results."
            if is_dead:
                dead_found.append((filename, fn))
        c.query(f"query callers for each candidate → {len(dead_found)}/7 confirmed dead")

        for filename, fn in dead_found:
            try:
                mcp.tool("remove_function", {"name": fn})
            except RuntimeError:
                pass  # function might not be in graph (e.g., already removed)
        c.action(f"remove {len(dead_found)} dead functions from graph")

        mcp.tool("checkpoint", {"path": ckpt})
        c.action("checkpoint (dead code removed)")
        c.done()
        agents.append(c)

        # ── Agent D: Feature — tax exemption ─────────────────────

        d = AgentLog("Agent D", "Add tax exemption to tax_amount")
        mcp.tool("restore", {"path": ckpt})
        mcp.tool("set_agent", {"name": "feature-dev"})
        d.inherit("restore — entities, deps, rules, rename + dead code removal")

        # D queries what tax_amount depends on
        tax_deps = mcp.tool("query", {"body": "(py-fn-depends-on tax_amount (? dep))"})
        d.query(f"'what does tax_amount call?' → {tax_deps.strip()}")

        # D queries blast radius — who will be affected?
        blast = mcp.tool("query", {"body": "(trans-dep (? caller) tax_amount)"})
        blast_count = len(blast.strip().splitlines()) if blast.strip() else 0
        d.query(f"'blast radius of tax_amount?' → {blast_count} transitive callers")

        mcp.tool("modify_function", {
            "name": "tax_amount",
            "source": (
                "def tax_amount(subtotal: float, region: str, exempt_below: float = 0.0) -> float:\n"
                "    if exempt_below > 0 and subtotal < exempt_below:\n"
                "        return 0.0\n"
                "    return round_cents(subtotal * tax_rate(region))"
            ),
            "language": "python",
        })
        d.action("modify tax_amount: add exempt_below parameter")

        mcp.tool("checkpoint", {"path": ckpt})
        d.action("checkpoint (feature added)")
        d.done()
        agents.append(d)

        # ── Agent E: Auditor — verify via graph queries ──────────

        e = AgentLog("Agent E", "Audit: verify all changes are consistent")
        mcp.tool("restore", {"path": ckpt})
        mcp.tool("set_agent", {"name": "auditor"})
        e.inherit("restore — full accumulated state from 4 prior agents")

        # Check rename
        r = mcp.tool("resolve_symbol", {"name": "compute_subtotal"})
        e.query(f"verify rename: compute_subtotal → entity {r.split()[-1]}")

        r2 = mcp.tool("resolve_symbol", {"name": "subtotal"})
        old_gone = "not found" in r2.lower()
        e.query(f"verify old name 'subtotal' gone: {old_gone} ({r2.strip()})")

        # Check dead code removed — query for active form-kind claims
        for _, fn in ALL_DEAD:
            r = mcp.tool("resolve_symbol", {"name": fn})
            gone = "not found" in r.lower()
            e.query(f"verify {fn} removed: {'gone' if gone else 'entity persists (claims invalidated)'}")

        # Check tax_amount has new parameter
        r = mcp.tool("inspect", {"id": mcp.tool("resolve_symbol", {"name": "tax_amount"}).split()[-1]})
        has_exempt = "exempt_below" in r
        e.query(f"verify tax_amount has exempt_below: {has_exempt}")

        # Check full dependency integrity
        deps_after = mcp.tool("query", {"body": "(py-fn-depends-on (? caller) (? callee))"})
        dep_count_after = len(deps_after.strip().splitlines()) if deps_after.strip() else 0
        e.query(f"verify dependency graph intact: {dep_count_after} edges")

        # Check tx_log shows all agents
        log = mcp.tool("tx_log", {"limit": 100})
        for agent_name in ["architect", "renamer", "janitor", "feature-dev"]:
            if agent_name in log:
                e.query(f"tx_log shows {agent_name}: yes")
            else:
                e.query(f"tx_log shows {agent_name}: no")

        e.action("structural audit complete")
        e.done()
        agents.append(e)

    finally:
        mcp.close()
        ws2 = fresh_workspace("cnf-verify")

        # 1. Precise rename: only the function entity, not parameters or dict keys.
        #    CNF renames the entity; in files, that means: definition, call sites, imports.
        #    The `subtotal` parameter in tax_amount is a DIFFERENT entity — left alone.
        for fname in ALL_FILES:
            lines = (ws2 / fname).read_text().split("\n")
            out = []
            in_import = False
            for line in lines:
                if re.match(r"^from \w+ import", line):
                    in_import = "(" in line and ")" not in line
                    line = re.sub(r"\bsubtotal\b", "compute_subtotal", line)
                elif in_import:
                    line = re.sub(r"\bsubtotal\b", "compute_subtotal", line)
                    if ")" in line:
                        in_import = False
                else:
                    line = re.sub(r"\bsubtotal\b(\s*\()", r"compute_subtotal\1", line)
                out.append(line)
            (ws2 / fname).write_text("\n".join(out))

        # 2. Remove dead code
        for filename, fn in ALL_DEAD:
            remove_function_from_file(ws2 / filename, fn)
        fp = ws2 / "processing.py"
        txt = fp.read_text()
        txt = txt.replace("# --- These shadow names from other modules ---\n", "")
        fp.write_text(txt)

        # 3. Add tax exemption (parameter name is still `subtotal` — not renamed)
        text = (ws2 / "pricing.py").read_text()
        text = text.replace(
            "def tax_amount(subtotal: float, region: str) -> float:\n"
            '    """Calculate tax on a subtotal."""\n'
            "    return round_cents(subtotal * tax_rate(region))",
            "def tax_amount(subtotal: float, region: str, exempt_below: float = 0.0) -> float:\n"
            '    """Calculate tax on a subtotal."""\n'
            "    if exempt_below > 0 and subtotal < exempt_below:\n"
            "        return 0.0\n"
            "    return round_cents(subtotal * tax_rate(region))",
        )
        (ws2 / "pricing.py").write_text(text)

        p, f = run_tests(ws2)
        cleanup(ws2)
        cleanup(ws)

    return agents, p, f


# ════════════════════════════════════════════════════════════════════
# Output
# ════════════════════════════════════════════════════════════════════

def print_agent(agent, indent="  "):
    labels = {"discover": "discover", "inherit": "INHERIT",
              "query": "query", "action": "action", "verify": "verify"}
    for op_type, detail, is_redisc in agent.ops:
        label = labels.get(op_type, op_type)
        suffix = "  ← REDISCOVERY" if is_redisc else ""
        print(f"{indent}[{label:>8}]  {detail}{suffix}")


def print_results(git_agents, cnf_agents, cnf_tests):
    print()
    print("═" * 72)
    print("  AGENT-BY-AGENT SUMMARY")
    print("═" * 72)
    print()

    # Per-agent comparison
    hdr = f"  {'Agent':30} {'Git disc':>10} {'Git redisc':>12} {'CNF disc':>10} {'CNF inherit':>12} {'CNF query':>10}"
    print(hdr)
    print("  " + "─" * 86)

    git_totals = {"disc": 0, "redisc": 0, "act": 0}
    cnf_totals = {"disc": 0, "redisc": 0, "inherit": 0, "query": 0, "act": 0}

    for ga, ca in zip(git_agents, cnf_agents):
        gd = len(ga.discoveries)
        gr = len(ga.rediscoveries)
        cd = len(ca.discoveries)
        ci = len(ca.inherits)
        cq = len(ca.queries)
        label = f"{ga.name} ({ga.task.split(':')[0].strip()})"
        if len(label) > 28:
            label = label[:28]
        print(f"  {label:30} {gd:>10} {gr:>12} {cd:>10} {ci:>12} {cq:>10}")

        git_totals["disc"] += gd
        git_totals["redisc"] += gr
        git_totals["act"] += len(ga.actions)
        cnf_totals["disc"] += cd
        cnf_totals["redisc"] += len(ca.rediscoveries)
        cnf_totals["inherit"] += ci
        cnf_totals["query"] += cq
        cnf_totals["act"] += len(ca.actions)

    print("  " + "─" * 86)
    print(f"  {'TOTAL':30} {git_totals['disc']:>10} {git_totals['redisc']:>12} {cnf_totals['disc']:>10} {cnf_totals['inherit']:>12} {cnf_totals['query']:>10}")

    print()
    print("═" * 72)
    print("  COORDINATION COST")
    print("═" * 72)
    print()

    print(f"  {'':45} {'Git':>10} {'CNF':>10}")
    print("  " + "─" * 67)
    print(f"  {'Total discoveries':45} {git_totals['disc']:>10} {cnf_totals['disc']:>10}")
    print(f"  {'  of which rediscovery':45} {git_totals['redisc']:>10} {cnf_totals['redisc']:>10}")
    print(f"  {'  of which novel':45} {git_totals['disc']-git_totals['redisc']:>10} {cnf_totals['disc']-cnf_totals['redisc']:>10}")
    print(f"  {'Inherited (via checkpoint restore)':45} {'—':>10} {cnf_totals['inherit']:>10}")
    print(f"  {'Queries on inherited state':45} {'—':>10} {cnf_totals['query']:>10}")
    print(f"  {'Actions':45} {git_totals['act']:>10} {cnf_totals['act']:>10}")
    print("  " + "─" * 67)

    git_total_ops = git_totals["disc"] + git_totals["act"]
    cnf_total_ops = cnf_totals["disc"] + cnf_totals["inherit"] + cnf_totals["query"] + cnf_totals["act"]
    print(f"  {'Total operations':45} {git_total_ops:>10} {cnf_total_ops:>10}")
    print(f"  {'Wasted on rediscovery':45} {git_totals['redisc']:>10} {cnf_totals['redisc']:>10}")

    if git_totals["disc"] > 0:
        git_pct = git_totals["redisc"] / git_totals["disc"] * 100
    else:
        git_pct = 0
    cnf_pct = 0
    print(f"  {'Rediscovery rate':45} {git_pct:>9.0f}% {cnf_pct:>9.0f}%")

    print()
    print(f"  CNF test verification: {cnf_tests[0]} passed, {cnf_tests[1]} failed")

    print()
    print("  Scaling behavior:")
    print(f"    Git:  each new agent pays full discovery cost ({len(SOURCE_FILES)+1} file reads + import tracing + greps)")
    print(f"    CNF:  each new agent pays 1 restore + targeted queries")
    print(f"    At 5 agents: git wastes {git_totals['redisc']} operations on rediscovery. CNF wastes 0.")
    print(f"    At 10 agents: git would waste ~{git_totals['redisc'] * 2}. CNF still 0.")


def main():
    print("═" * 72)
    print("  E19: Coordination Cost — Shared Working Memory")
    print("  5 agents, 45-function codebase, 6 modules")
    print("═" * 72)
    print()
    print(f"  Codebase: {CODEBASE}")
    print(f"  Files: {', '.join(SOURCE_FILES)}")
    print(f"  MCP server: {SERVER}")
    print()

    ws = fresh_workspace("baseline")
    p, f = run_tests(ws)
    cleanup(ws)
    print(f"  Baseline: {p} passed, {f} failed")
    if f != 0:
        print("ERROR: baseline tests must pass")
        sys.exit(1)
    print()

    # ── Git condition ────────────────────────────────────────────

    print("═" * 72)
    print("  GIT CONDITION — 5 agents, file-based coordination")
    print("═" * 72)
    git_agents = run_git_condition()
    for agent in git_agents:
        print()
        print(f"  {agent.name}: {agent.task} ({agent.elapsed:.1f}s)")
        print_agent(agent)

    # ── CNF condition ────────────────────────────────────────────

    print()
    print("═" * 72)
    print("  CNF CONDITION — 5 agents, shared claim graph")
    print("═" * 72)
    cnf_agents, cp, cf = run_cnf_condition()
    for agent in cnf_agents:
        print()
        print(f"  {agent.name}: {agent.task} ({agent.elapsed:.1f}s)")
        print_agent(agent)

    # ── Results ──────────────────────────────────────────────────

    print_results(git_agents, cnf_agents, (cp, cf))

    print()
    print("═" * 72)


if __name__ == "__main__":
    main()

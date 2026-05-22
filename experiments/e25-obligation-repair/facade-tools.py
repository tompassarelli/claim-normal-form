#!/usr/bin/env python3
"""MCP tool server — 6 high-level tools for agent graph reasoning.

Extends graph-tools with semantic facade tools that surface domain
patterns (lifecycles, state machines) and validate agent-written code
against the graph.

  discover(name)                  — everything about one symbol
  discover_all(kind?, module?)    — all symbols with modules and values
  dependencies(symbol?)           — what calls what
  declare_intent(module, ...)     — write coordination intent into graph
  discover_lifecycle(domain?)     — scan for state machines and workflows
  verify_references(code)         — check imports/references against graph
"""

import ast
import json
import re
import socket
import sys

DAEMON_PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 7891
EXCLUDE_TOOLS = set()
for _i, _arg in enumerate(sys.argv):
    if _arg == "--exclude" and _i + 1 < len(sys.argv):
        EXCLUDE_TOOLS = set(sys.argv[_i + 1].split(","))


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


_py_body_pred_cache = {}


def _get_py_body_pred(sock):
    """Resolve py-body predicate entity ID (cached per session)."""
    if "id" not in _py_body_pred_cache:
        eid = _resolve_eid(sock, "py-body")
        _py_body_pred_cache["id"] = eid
    return _py_body_pred_cache["id"]


def _find_body_eid(sock, eid):
    """Find the py-body entity for a given entity."""
    py_body = _get_py_body_pred(sock)
    if not py_body:
        return None
    text = daemon_inspect(sock, eid)
    for line in text.split("\n"):
        if f" {py_body} (entity)" in line:
            match = re.search(r'(\d+)\s+\(entity\)\s*$', line.strip())
            if match:
                return match.group(1)
    return None


def _extract_values(sock, eid):
    body_eid = _find_body_eid(sock, eid)
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


def _get_body_form_kind(sock, eid):
    """Get the py-form-kind of a variable's py-body entity (list, dict, etc)."""
    body_eid = _find_body_eid(sock, eid)
    if not body_eid:
        return None

    body_text = daemon_inspect(sock, body_eid)
    for line in body_text.split("\n"):
        if "py-form-kind" in line:
            match = re.search(r'\(value:\s*([^)]+)\)', line)
            if match:
                return match.group(1).strip()
    return None


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
        # Parser-created values show as (value: X), claim-created as "X" (unknown)
        m_match = re.search(r'\(value:\s*([^)]+)\)', line)
        if not m_match:
            m_match = re.search(r'\?m\s*=\s*"([^"]+)"', line)
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


# ── Lifecycle detection helpers ──

_LIFECYCLE_NAME_HINTS = {
    "active": "active",
    "terminal": "terminal",
    "status": "status",
    "state": "status",
    "transition": "transitions",
    "valid_transition": "transitions",
    "workflow": "transitions",
}


def _classify_lifecycle_variable(name, values, body_form_kind):
    """Classify a variable as a lifecycle component based on value shape and name.

    Returns a classification string or None if it does not look lifecycle-shaped.
    """
    name_lower = name.lower()

    # Dict-shaped body -> transition map
    if body_form_kind == "dict":
        return "transitions"

    # List of short strings -> could be status/state list
    if values and all(isinstance(v, str) and len(v) < 40 for v in values):
        # Name heuristics for sub-classification
        for hint, classification in _LIFECYCLE_NAME_HINTS.items():
            if hint in name_lower:
                return classification
        # Fallback: a list of short strings with no specific hint is still
        # potentially status-shaped; mark it as generic status list
        if len(values) >= 2:
            return "status"

    return None


def _matches_domain(name, module, domain):
    """Check if a symbol or its module relates to the given domain string."""
    d = domain.lower()
    return d in name.lower() or (module and d in module.lower())


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
    """All symbols with modules. Optionally filter by kind and/or module."""
    kind_filter = args.get("kind", "")
    module_filter = args.get("module", "")
    symbols = _all_symbols(sock)

    results = []
    for sym in sorted(symbols.values(), key=lambda s: (s.get("module", ""), s["name"])):
        if kind_filter and sym["kind"] != kind_filter:
            continue
        if module_filter and sym.get("module", "") != module_filter:
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


def handle_discover_lifecycle(sock, args):
    """Scan the graph for state machines, workflows, and lifecycle patterns."""
    domain = args.get("domain", "")
    symbols = _all_symbols(sock)

    # Collect all variables and check for lifecycle shapes
    lifecycle_vars = {}   # name -> {classification, module, values, body_form_kind}
    lifecycle_modules = set()

    for sym in symbols.values():
        if sym["kind"] != "variable":
            continue

        name = sym["name"]
        eid = sym["entity"]
        module = sym.get("module", "")

        # Domain filter: skip symbols not related to the requested domain
        if domain and not _matches_domain(name, module, domain):
            continue

        values = _extract_values(sock, eid)
        if not values:
            continue

        body_form_kind = _get_body_form_kind(sock, eid)
        classification = _classify_lifecycle_variable(name, values, body_form_kind)

        if classification:
            lifecycle_vars[name] = {
                "classification": classification,
                "module": module,
                "values": values,
                "body_form_kind": body_form_kind,
            }
            if module:
                lifecycle_modules.add(module)

    # No lifecycle patterns found
    if not lifecycle_vars:
        msg = "No lifecycle or state-machine patterns found"
        if domain:
            msg += f" for domain '{domain}'"
        return json.dumps({"message": msg, "states": {}, "transitions": {},
                           "variables": {}, "functions": {}})

    # Build the states section from classified variables
    states = {"active": [], "terminal": [], "other": []}
    transitions = {}
    variables_out = {}

    for var_name, info in sorted(lifecycle_vars.items()):
        cls = info["classification"]
        mod = info["module"]

        # Populate states buckets
        if cls == "active":
            states["active"] = info["values"]
        elif cls == "terminal":
            states["terminal"] = info["values"]
        elif cls == "transitions":
            # For dict-shaped transition maps, represent as a note with raw values
            # since _extract_values returns flattened key/value strings
            transitions[var_name] = info["values"]
        elif cls == "status":
            states["other"].extend(info["values"])

        # Build variable reference
        variables_out[var_name] = {"module": mod}
        if mod:
            variables_out[var_name]["import"] = f"from {mod} import {var_name}"
        if info["body_form_kind"]:
            variables_out[var_name]["shape"] = info["body_form_kind"]
        variables_out[var_name]["values"] = info["values"]

    # Clean up empty state buckets
    if not states["active"]:
        del states["active"]
    if not states["terminal"]:
        del states["terminal"]
    if not states["other"]:
        del states["other"]

    # Find functions in the same modules as lifecycle variables
    functions_out = {}
    for sym in sorted(symbols.values(), key=lambda s: s["name"]):
        if sym["kind"] != "function":
            continue
        mod = sym.get("module", "")
        if mod not in lifecycle_modules:
            continue
        if domain and not _matches_domain(sym["name"], mod, domain):
            continue
        fn_name = sym["name"]
        functions_out[fn_name] = {"module": mod}
        if mod:
            functions_out[fn_name]["import"] = f"from {mod} import {fn_name}"

    result = {
        "states": states,
        "transitions": transitions,
        "variables": variables_out,
        "functions": functions_out,
    }

    return json.dumps(result, indent=2)


def handle_verify_references(sock, args):
    """Parse code, check imports and references against the graph."""
    code = args.get("code", "")

    # Parse the code with ast
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return json.dumps({"error": f"Syntax error in provided code: {e}"})

    # Extract imports: list of (module, name, alias) tuples
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            for alias in node.names:
                imports.append({
                    "module": mod,
                    "name": alias.name,
                    "alias": alias.asname or alias.name,
                    "statement": f"from {mod} import {alias.name}"
                                 + (f" as {alias.asname}" if alias.asname else ""),
                })
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imports.append({
                    "module": alias.name,
                    "name": alias.name,
                    "alias": alias.asname or alias.name,
                    "statement": f"import {alias.name}"
                                 + (f" as {alias.asname}" if alias.asname else ""),
                })

    # Extract all referenced names in function/method bodies and module level
    referenced_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            referenced_names.add(node.id)
        elif isinstance(node, ast.Attribute):
            # Capture the root name of attribute chains (e.g., 'workflow' in workflow.x)
            root = node
            while isinstance(root, ast.Attribute):
                root = root.value
            if isinstance(root, ast.Name):
                referenced_names.add(root.id)

    # Check each import against the graph
    resolved = []
    missing = []
    all_symbols = _all_symbols(sock)
    all_names = list(all_symbols.keys())

    for imp in imports:
        name = imp["name"]
        eid = _resolve_eid(sock, name)
        if eid:
            entry = {
                "name": name,
                "statement": imp["statement"],
                "entity": eid,
            }
            graph_sym = all_symbols.get(name)
            if graph_sym and graph_sym.get("module"):
                entry["graph_module"] = graph_sym["module"]
                expected_import = f"from {graph_sym['module']} import {name}"
                if imp["statement"] != expected_import:
                    entry["suggested_import"] = expected_import
            resolved.append(entry)
        else:
            entry = {
                "name": name,
                "statement": imp["statement"],
            }
            # Find similar names by substring/prefix matching
            suggestions = []
            name_lower = name.lower()
            for candidate in all_names:
                cand_lower = candidate.lower()
                if (name_lower in cand_lower
                        or cand_lower in name_lower
                        or _common_prefix_len(name_lower, cand_lower) >= 4):
                    sym = all_symbols[candidate]
                    suggestion = {"name": candidate, "kind": sym["kind"]}
                    if sym.get("module"):
                        suggestion["import"] = f"from {sym['module']} import {candidate}"
                    suggestions.append(suggestion)
            if suggestions:
                entry["suggestions"] = suggestions[:5]
            missing.append(entry)

    # Check for unused imports (imported but never referenced in code body)
    imported_aliases = {imp["alias"] for imp in imports}
    unused = []
    for imp in imports:
        alias = imp["alias"]
        if alias not in referenced_names:
            unused.append({
                "name": imp["name"],
                "statement": imp["statement"],
            })

    result = {
        "resolved": resolved,
        "missing": missing,
        "unused": unused,
        "summary": {
            "total_imports": len(imports),
            "resolved": len(resolved),
            "missing": len(missing),
            "unused": len(unused),
        },
    }

    return json.dumps(result, indent=2)


def _common_prefix_len(a, b):
    """Length of the common prefix between two strings."""
    n = min(len(a), len(b))
    for i in range(n):
        if a[i] != b[i]:
            return i
    return n


def handle_finish_check(sock, args):
    """Analyze generated code against the graph to find missing obligations."""
    task = args.get("task", "")
    code = args.get("code", "")
    module_name = args.get("module", "")

    obligations = []

    # 1. Parse the code
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return json.dumps({"status": "error",
                           "error": f"Syntax error: {e}",
                           "obligations": []})

    # Extract imports
    code_imports = set()
    import_modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            import_modules.add(mod)
            for alias in node.names:
                code_imports.add(alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                import_modules.add(alias.name)
                code_imports.add(alias.name)

    # Extract string literals (potential hardcoded statuses)
    string_literals = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            string_literals.add(node.value)

    # Extract all referenced names
    referenced_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            referenced_names.add(node.id)

    # Extract function definitions
    defined_functions = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            defined_functions.add(node.name)

    # 2. Query the graph for domain knowledge
    symbols = _all_symbols(sock)
    lifecycle_info = _get_lifecycle_info(sock, symbols)

    # 3. Determine what domains this task touches
    task_lower = task.lower()
    code_lower = code.lower()

    touches_tickets = any(kw in task_lower or kw in code_lower
                          for kw in ["ticket", "create_ticket", "get_ticket",
                                     "update_ticket", "list_ticket"])
    touches_statuses = any(kw in task_lower or kw in code_lower
                           for kw in ["status", "transition", "state",
                                      "active", "terminal", "archived",
                                      "closed", "resolved"])
    touches_permissions = any(kw in task_lower or kw in code_lower
                              for kw in ["permission", "access", "role",
                                         "admin", "can_manage", "can_archive",
                                         "authorize"])
    touches_notifications = any(kw in task_lower or kw in code_lower
                                for kw in ["notif", "subscribe", "alert",
                                           "notify"])
    touches_analytics = any(kw in task_lower or kw in code_lower
                            for kw in ["analytics", "summary", "count",
                                       "report", "unassigned"])

    # 4. Check for missing obligations

    # -- Obligation: workflow module not imported --
    workflow_imported = "workflow" in import_modules
    workflow_symbols_used = bool(code_imports & set(lifecycle_info.get("variables", {}).keys()))

    if not workflow_imported and not workflow_symbols_used:
        if touches_tickets or touches_statuses or touches_permissions or \
           touches_notifications or touches_analytics:
            obligation = {
                "domain": "ticket lifecycle",
                "severity": "critical",
                "reason": (
                    "This module operates on tickets but does not import from "
                    "the workflow module. The workflow module defines lifecycle "
                    "constants and functions that govern ticket behavior."
                ),
                "evidence": [],
                "required_imports": [],
            }
            for var_name, info in lifecycle_info.get("variables", {}).items():
                obligation["evidence"].append({
                    "symbol": var_name,
                    "module": info.get("module", ""),
                    "classification": info.get("classification", ""),
                    "values": info.get("values", []),
                })
                mod = info.get("module", "")
                if mod:
                    obligation["required_imports"].append(
                        f"from {mod} import {var_name}")
            for fn_name, info in lifecycle_info.get("functions", {}).items():
                mod = info.get("module", "")
                if mod:
                    obligation["evidence"].append({
                        "symbol": fn_name,
                        "module": mod,
                        "type": "function",
                    })
            obligations.append(obligation)

    # -- Obligation: terminal statuses not handled --
    terminal_statuses = set(lifecycle_info.get("terminal", []))
    if terminal_statuses and (touches_tickets or touches_statuses or
                              touches_permissions or touches_notifications or
                              touches_analytics):
        # Check if code references TERMINAL_STATUSES or the actual values
        knows_terminal = ("TERMINAL_STATUSES" in code_imports or
                          "TERMINAL_STATUSES" in referenced_names or
                          "terminal" in code_lower)
        handles_archived = ("archived" in string_literals or
                            "archived" in code_lower)

        if not knows_terminal and not handles_archived:
            obligations.append({
                "domain": "terminal status handling",
                "severity": "critical",
                "reason": (
                    f"Terminal statuses exist ({', '.join(sorted(terminal_statuses))}) "
                    f"but this code does not check for them. Terminal tickets "
                    f"should be excluded from active operations, notifications "
                    f"should be suppressed, and management should be restricted."
                ),
                "evidence": [{
                    "symbol": "TERMINAL_STATUSES",
                    "values": sorted(terminal_statuses),
                    "import": "from workflow import TERMINAL_STATUSES",
                }],
                "impact_by_task": {
                    "notifications": "suppress notifications for terminal tickets",
                    "analytics": "exclude terminal tickets from active counts",
                    "permissions": "deny management of archived/terminal tickets",
                },
            })

    # -- Obligation: hardcoded statuses --
    known_statuses = set()
    for vals in [lifecycle_info.get("terminal", []),
                 lifecycle_info.get("active", []),
                 lifecycle_info.get("other", [])]:
        known_statuses.update(vals)

    hardcoded_in_code = string_literals & known_statuses
    if hardcoded_in_code and not workflow_symbols_used:
        obligations.append({
            "domain": "hardcoded constants",
            "severity": "warning",
            "reason": (
                f"Status values {sorted(hardcoded_in_code)} are hardcoded as "
                f"string literals. These should be imported from the workflow "
                f"module to stay synchronized with the canonical definitions."
            ),
            "evidence": [{
                "hardcoded": sorted(hardcoded_in_code),
                "should_import": [f"from workflow import {v}"
                                  for v in sorted(lifecycle_info.get("variables", {}).keys())],
            }],
        })

    # -- Obligation: permissions must gate on lifecycle --
    if touches_permissions:
        # Check if permission functions consider ticket status
        gates_on_status = any(kw in code_lower for kw in
                              ["status", "terminal", "archived", "is_active",
                               "TERMINAL_STATUSES", "ACTIVE_STATUSES"])
        if not gates_on_status:
            obligations.append({
                "domain": "lifecycle-gated permissions",
                "severity": "critical",
                "reason": (
                    "Permission checks must account for ticket lifecycle state. "
                    "Archived tickets should not be manageable by non-admin users. "
                    "The workflow module defines which statuses are terminal."
                ),
                "evidence": [{
                    "constraint": "archived tickets are terminal",
                    "import": "from workflow import TERMINAL_STATUSES",
                    "check": "ticket status in TERMINAL_STATUSES → deny non-admin",
                }],
            })

    # -- Obligation: analytics must distinguish active/terminal --
    if touches_analytics:
        handles_active = any(kw in code_lower for kw in
                             ["active_statuses", "is_active",
                              "terminal_statuses", "terminal"])
        if not handles_active:
            active = lifecycle_info.get("active", [])
            terminal = lifecycle_info.get("terminal", [])
            if active or terminal:
                obligations.append({
                    "domain": "active/terminal distinction",
                    "severity": "critical",
                    "reason": (
                        f"Analytics must distinguish active ({', '.join(active)}) "
                        f"from terminal ({', '.join(terminal)}) tickets. Active "
                        f"ticket counts and unassigned lists must exclude terminal."
                    ),
                    "evidence": [{
                        "active": active,
                        "terminal": terminal,
                        "imports": [
                            "from workflow import ACTIVE_STATUSES",
                            "from workflow import TERMINAL_STATUSES",
                        ],
                    }],
                })

    # -- Obligation: notifications must suppress for terminal --
    if touches_notifications:
        suppresses_terminal = any(kw in code_lower for kw in
                                  ["terminal", "archived", "suppress",
                                   "TERMINAL_STATUSES"])
        if not suppresses_terminal:
            obligations.append({
                "domain": "notification suppression",
                "severity": "critical",
                "reason": (
                    "Notifications must be suppressed for terminal ticket states. "
                    "Transitions to or from archived/terminal states should not "
                    "trigger notifications."
                ),
                "evidence": [{
                    "terminal_statuses": sorted(terminal_statuses),
                    "import": "from workflow import TERMINAL_STATUSES",
                    "check": "if old_status in TERMINAL_STATUSES or new_status in TERMINAL_STATUSES: return",
                }],
            })

    status = "pass" if not obligations else "failed"
    critical_count = sum(1 for o in obligations if o.get("severity") == "critical")

    return json.dumps({
        "status": status,
        "obligations_found": len(obligations),
        "critical": critical_count,
        "obligations": obligations,
    }, indent=2)


def _get_lifecycle_info(sock, symbols):
    """Extract lifecycle info from graph symbols for finish_check analysis."""
    result = {"variables": {}, "functions": {},
              "terminal": [], "active": [], "other": []}

    for sym in symbols.values():
        if sym["kind"] != "variable":
            continue
        name = sym["name"]
        eid = sym["entity"]
        values = _extract_values(sock, eid)
        if not values:
            continue
        body_form_kind = _get_body_form_kind(sock, eid)
        classification = _classify_lifecycle_variable(name, values, body_form_kind)
        if classification:
            mod = sym.get("module", "")
            result["variables"][name] = {
                "classification": classification,
                "module": mod,
                "values": values,
            }
            if classification == "terminal":
                result["terminal"] = values
            elif classification == "active":
                result["active"] = values

    for sym in symbols.values():
        if sym["kind"] != "function":
            continue
        mod = sym.get("module", "")
        if any(mod == v.get("module") for v in result["variables"].values()):
            result["functions"][sym["name"]] = {"module": mod}

    return result


TOOLS = {
    "discover": {
        "handler": handle_discover,
        "schema": {
            "name": "discover",
            "description": (
                "Look up one specific symbol by name. Returns its kind "
                "(function/variable/class), module, values (for variables), "
                "and the exact import statement to use. "
                "Example: discover('TERMINAL_STATUSES') returns its values "
                "and 'from workflow import TERMINAL_STATUSES'."
            ),
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
            "description": (
                "List all symbols in the codebase with their kinds, modules, "
                "and values. Optionally filter by kind ('function', 'variable', "
                "'class') and/or module name. This is how you learn what exists."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string",
                             "description": "Optional: 'function', 'variable', or 'class'"},
                    "module": {"type": "string",
                               "description": "Optional: filter to symbols from this module only"},
                },
                "required": [],
            },
        },
    },
    "dependencies": {
        "handler": handle_dependencies,
        "schema": {
            "name": "dependencies",
            "description": (
                "Show the call graph — what depends on what. Pass a symbol "
                "name to see what depends on it, or omit for the full "
                "dependency graph across all modules."
            ),
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
            "description": (
                "Declare what your module depends on and what it provides. "
                "Written into the shared graph for other agents to see."
            ),
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
    "discover_lifecycle": {
        "handler": handle_discover_lifecycle,
        "schema": {
            "name": "discover_lifecycle",
            "description": (
                "Discover lifecycle/state-machine information in the codebase. "
                "Call this before writing code involving tickets, states, "
                "statuses, transitions, active/terminal records, archived "
                "records, notifications, analytics, permissions, access "
                "control, role-based rules, workflow rules, or "
                "status-dependent logic. Returns known states, "
                "active/terminal groups, valid transitions, related "
                "constants, related functions, and import statements."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "domain": {
                        "type": "string",
                        "description": (
                            "Optional: filter to a specific domain "
                            "(e.g. 'ticket', 'order', 'user')"
                        ),
                    },
                },
                "required": [],
            },
        },
    },
    "verify_references": {
        "handler": handle_verify_references,
        "schema": {
            "name": "verify_references",
            "description": (
                "Check whether your code's imports and references exist in "
                "the codebase. Pass your complete module source code. Returns "
                "which imports resolve, which are missing (with suggestions), "
                "and which are unused."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "Complete Python module source code to validate",
                    },
                },
                "required": ["code"],
            },
        },
    },
    "finish_check": {
        "handler": handle_finish_check,
        "schema": {
            "name": "finish_check",
            "description": (
                "Verify completed code against the graph. Analyzes your module "
                "for missing obligations — cross-domain constraints your code "
                "must account for but doesn't yet. Returns specific, actionable "
                "fixes with import statements and graph evidence."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "task": {
                        "type": "string",
                        "description": "Description of what this module does",
                    },
                    "code": {
                        "type": "string",
                        "description": "Complete module source code to check",
                    },
                    "module": {
                        "type": "string",
                        "description": "Module filename (e.g. 'permissions.py')",
                    },
                },
                "required": ["task", "code"],
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
                "serverInfo": {"name": "cnf-facade-tools", "version": "0.3"},
            },
        }

    if method == "notifications/initialized":
        return None

    if method == "tools/list":
        tool_list = [t["schema"] for t in TOOLS.values()
                     if t["schema"]["name"] not in EXCLUDE_TOOLS]
        return {
            "jsonrpc": "2.0", "id": req_id,
            "result": {"tools": tool_list},
        }

    if method == "tools/call":
        tool_name = params.get("name", "")
        tool_args = params.get("arguments", {})
        if tool_name not in TOOLS or tool_name in EXCLUDE_TOOLS:
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
    sys.stderr.write(f"facade-tools: connecting to daemon on port {DAEMON_PORT}\n")
    sys.stderr.flush()

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(("127.0.0.1", DAEMON_PORT))

    send_rpc(sock, "initialize", {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "facade-tools", "version": "0.3"},
    })

    import time as _time
    for attempt in range(5):
        test = daemon_query(sock,
                            "(current-triple (? e) py-form-kind (? kind))")
        count = sum(1 for l in test.strip().split("\n")
                    if "?" in l) if test else 0
        if count > 0:
            sys.stderr.write(
                f"facade-tools: connected, {count} entities visible\n")
            sys.stderr.flush()
            break
        sys.stderr.write(
            f"facade-tools: attempt {attempt+1}, 0 entities, retrying...\n")
        sys.stderr.flush()
        if attempt < 4:
            sock.close()
            _time.sleep(1)
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect(("127.0.0.1", DAEMON_PORT))
            send_rpc(sock, "initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "facade-tools", "version": "0.3"},
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

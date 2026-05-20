#!/usr/bin/env python3
"""Parse Python source into JSON AST for CNF bridge.

Usage: python3 python-ast-helper.py < source.py
       python3 python-ast-helper.py path/to/source.py
"""

import ast
import json
import sys


def convert_node(node):
    if isinstance(node, ast.Module):
        return {"type": "module", "body": [convert_node(n) for n in node.body]}

    # --- Top-level definitions ---

    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        params = []
        for arg in node.args.args:
            p = {"name": arg.arg}
            if arg.annotation:
                p["annotation"] = unparse_safe(arg.annotation)
            params.append(p)
        result = {
            "type": "function_def",
            "name": node.name,
            "params": params,
            "body": [convert_node(n) for n in node.body],
            "decorators": [unparse_safe(d) for d in node.decorator_list],
            "async": isinstance(node, ast.AsyncFunctionDef),
        }
        if node.returns:
            result["return_annotation"] = unparse_safe(node.returns)
        if node.args.vararg:
            result["vararg"] = node.args.vararg.arg
        if node.args.kwarg:
            result["kwarg"] = node.args.kwarg.arg
        defaults = node.args.defaults
        if defaults:
            offset = len(params) - len(defaults)
            for i, d in enumerate(defaults):
                params[offset + i]["default"] = unparse_safe(d)
        return result

    if isinstance(node, ast.ClassDef):
        return {
            "type": "class_def",
            "name": node.name,
            "bases": [unparse_safe(b) for b in node.bases],
            "body": [convert_node(n) for n in node.body],
            "decorators": [unparse_safe(d) for d in node.decorator_list],
        }

    if isinstance(node, (ast.Import, ast.ImportFrom)):
        names = [{"name": a.name, "asname": a.asname} for a in node.names]
        result = {"type": "import", "names": names}
        if isinstance(node, ast.ImportFrom) and node.module:
            result["module"] = node.module
        return result

    # --- Assignments ---

    if isinstance(node, ast.Assign):
        targets = []
        for t in node.targets:
            targets.append(unparse_safe(t))
        result = {"type": "assign", "targets": targets, "value": convert_node(node.value)}
        return result

    if isinstance(node, ast.AnnAssign):
        result = {"type": "ann_assign", "target": unparse_safe(node.target)}
        if node.annotation:
            result["annotation"] = unparse_safe(node.annotation)
        if node.value:
            result["value"] = convert_node(node.value)
        return result

    if isinstance(node, ast.AugAssign):
        return {
            "type": "aug_assign",
            "target": unparse_safe(node.target),
            "op": op_name(node.op),
            "value": convert_node(node.value),
        }

    # --- Expressions ---

    if isinstance(node, ast.Call):
        func_str = unparse_safe(node.func)
        return {
            "type": "call",
            "func": func_str,
            "func_node": convert_node(node.func),
            "args": [convert_node(a) for a in node.args],
            "kwargs": [{"key": kw.arg, "value": convert_node(kw.value)} for kw in node.keywords],
        }

    if isinstance(node, ast.Name):
        return {"type": "name", "id": node.id}

    if isinstance(node, ast.Attribute):
        return {"type": "attribute", "value": convert_node(node.value), "attr": node.attr}

    if isinstance(node, ast.Constant):
        v = node.value
        if isinstance(v, (int, float, bool)):
            return {"type": "constant", "value": v}
        if isinstance(v, str):
            return {"type": "constant", "value": v, "kind": "str"}
        if v is None:
            return {"type": "constant", "value": None}
        return {"type": "constant", "value": repr(v)}

    # --- Operators ---

    if isinstance(node, ast.BinOp):
        return {
            "type": "binop",
            "op": op_name(node.op),
            "left": convert_node(node.left),
            "right": convert_node(node.right),
        }

    if isinstance(node, ast.UnaryOp):
        return {"type": "unaryop", "op": op_name(node.op), "operand": convert_node(node.operand)}

    if isinstance(node, ast.BoolOp):
        return {
            "type": "boolop",
            "op": "and" if isinstance(node.op, ast.And) else "or",
            "values": [convert_node(v) for v in node.values],
        }

    if isinstance(node, ast.Compare):
        return {
            "type": "compare",
            "left": convert_node(node.left),
            "ops": [op_name(o) for o in node.ops],
            "comparators": [convert_node(c) for c in node.comparators],
        }

    # --- Control flow ---

    if isinstance(node, ast.If):
        result = {
            "type": "if",
            "test": convert_node(node.test),
            "body": [convert_node(n) for n in node.body],
        }
        if node.orelse:
            result["orelse"] = [convert_node(n) for n in node.orelse]
        return result

    if isinstance(node, ast.For):
        return {
            "type": "for",
            "target": unparse_safe(node.target),
            "iter": convert_node(node.iter),
            "body": [convert_node(n) for n in node.body],
        }

    if isinstance(node, ast.While):
        return {
            "type": "while",
            "test": convert_node(node.test),
            "body": [convert_node(n) for n in node.body],
        }

    if isinstance(node, ast.With):
        items = []
        for item in node.items:
            entry = {"context": convert_node(item.context_expr)}
            if item.optional_vars:
                entry["as"] = unparse_safe(item.optional_vars)
            items.append(entry)
        return {
            "type": "with",
            "items": items,
            "body": [convert_node(n) for n in node.body],
        }

    if isinstance(node, ast.Try):
        result = {"type": "try", "body": [convert_node(n) for n in node.body]}
        if node.handlers:
            result["handlers"] = []
            for h in node.handlers:
                handler = {"body": [convert_node(n) for n in h.body]}
                if h.type:
                    handler["type_name"] = unparse_safe(h.type)
                if h.name:
                    handler["name"] = h.name
                result["handlers"].append(handler)
        if node.orelse:
            result["orelse"] = [convert_node(n) for n in node.orelse]
        if node.finalbody:
            result["finalbody"] = [convert_node(n) for n in node.finalbody]
        return result

    if isinstance(node, ast.Return):
        result = {"type": "return"}
        if node.value:
            result["value"] = convert_node(node.value)
        return result

    if isinstance(node, ast.Yield):
        result = {"type": "yield"}
        if node.value:
            result["value"] = convert_node(node.value)
        return result

    if isinstance(node, ast.YieldFrom):
        return {"type": "yield_from", "value": convert_node(node.value)}

    if isinstance(node, ast.Raise):
        result = {"type": "raise"}
        if node.exc:
            result["exc"] = convert_node(node.exc)
        return result

    if isinstance(node, ast.Assert):
        result = {"type": "assert", "test": convert_node(node.test)}
        if node.msg:
            result["msg"] = convert_node(node.msg)
        return result

    # --- Comprehensions ---

    if isinstance(node, ast.ListComp):
        return {
            "type": "listcomp",
            "elt": convert_node(node.elt),
            "generators": [convert_generator(g) for g in node.generators],
        }

    if isinstance(node, ast.DictComp):
        return {
            "type": "dictcomp",
            "key": convert_node(node.key),
            "value": convert_node(node.value),
            "generators": [convert_generator(g) for g in node.generators],
        }

    if isinstance(node, ast.SetComp):
        return {
            "type": "setcomp",
            "elt": convert_node(node.elt),
            "generators": [convert_generator(g) for g in node.generators],
        }

    if isinstance(node, ast.GeneratorExp):
        return {
            "type": "genexp",
            "elt": convert_node(node.elt),
            "generators": [convert_generator(g) for g in node.generators],
        }

    # --- Collections ---

    if isinstance(node, ast.List):
        return {"type": "list", "elts": [convert_node(e) for e in node.elts]}

    if isinstance(node, ast.Tuple):
        return {"type": "tuple", "elts": [convert_node(e) for e in node.elts]}

    if isinstance(node, ast.Dict):
        return {
            "type": "dict",
            "keys": [convert_node(k) if k else None for k in node.keys],
            "values": [convert_node(v) for v in node.values],
        }

    if isinstance(node, ast.Set):
        return {"type": "set", "elts": [convert_node(e) for e in node.elts]}

    # --- Other expressions ---

    if isinstance(node, ast.Lambda):
        params = [{"name": a.arg} for a in node.args.args]
        return {"type": "lambda", "params": params, "body": convert_node(node.body)}

    if isinstance(node, ast.IfExp):
        return {
            "type": "ifexp",
            "test": convert_node(node.test),
            "body": convert_node(node.body),
            "orelse": convert_node(node.orelse),
        }

    if isinstance(node, ast.Subscript):
        return {
            "type": "subscript",
            "value": convert_node(node.value),
            "slice": convert_node(node.slice),
        }

    if isinstance(node, ast.Starred):
        return {"type": "starred", "value": convert_node(node.value)}

    if isinstance(node, ast.JoinedStr):
        return {"type": "fstring", "values": [convert_node(v) for v in node.values]}

    if isinstance(node, ast.FormattedValue):
        return {"type": "formatted_value", "value": convert_node(node.value)}

    # --- Statements ---

    if isinstance(node, ast.Expr):
        return {"type": "expr_stmt", "value": convert_node(node.value)}

    if isinstance(node, ast.Pass):
        return {"type": "pass"}

    if isinstance(node, ast.Break):
        return {"type": "break"}

    if isinstance(node, ast.Continue):
        return {"type": "continue"}

    if isinstance(node, ast.Delete):
        return {"type": "delete", "targets": [unparse_safe(t) for t in node.targets]}

    if isinstance(node, ast.Global):
        return {"type": "global", "names": node.names}

    if isinstance(node, ast.Nonlocal):
        return {"type": "nonlocal", "names": node.names}

    if isinstance(node, ast.Match):
        return {
            "type": "match",
            "subject": convert_node(node.subject),
            "cases": [
                {
                    "pattern": unparse_safe(c.pattern) if hasattr(ast, "unparse") else str(c.pattern),
                    "body": [convert_node(n) for n in c.body],
                }
                for c in node.cases
            ],
        }

    return {"type": "unknown", "ast_type": type(node).__name__, "source": unparse_safe(node)}


def convert_generator(gen):
    return {
        "target": unparse_safe(gen.target),
        "iter": convert_node(gen.iter),
        "ifs": [convert_node(i) for i in gen.ifs],
    }


def op_name(op):
    names = {
        ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/",
        ast.FloorDiv: "//", ast.Mod: "%", ast.Pow: "**",
        ast.BitOr: "|", ast.BitAnd: "&", ast.BitXor: "^",
        ast.LShift: "<<", ast.RShift: ">>",
        ast.Eq: "==", ast.NotEq: "!=", ast.Lt: "<", ast.LtE: "<=",
        ast.Gt: ">", ast.GtE: ">=", ast.Is: "is", ast.IsNot: "is not",
        ast.In: "in", ast.NotIn: "not in",
        ast.Not: "not", ast.UAdd: "+", ast.USub: "-", ast.Invert: "~",
        ast.MatMult: "@",
    }
    return names.get(type(op), type(op).__name__)


def unparse_safe(node):
    try:
        return ast.unparse(node)
    except Exception:
        return str(node)


def main():
    if len(sys.argv) > 1:
        with open(sys.argv[1]) as f:
            source = f.read()
    else:
        source = sys.stdin.read()

    tree = ast.parse(source)
    result = convert_node(tree)
    json.dump(result, sys.stdout, indent=None, separators=(",", ":"))


if __name__ == "__main__":
    main()

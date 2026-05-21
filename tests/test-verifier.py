#!/usr/bin/env python3
"""Smoke test for E23b verifier: start daemon, parse, verify, stop."""
import sys
sys.path.insert(0, "experiments/e23-concurrent-agents")
from runner import (
    start_daemon, stop_daemon, init_graph, verify_daemon_state,
    _extract_count,
)

proc, backup = start_daemon()
try:
    print("Parsing...")
    status, fn_ids = init_graph()

    print(f"\nVerifier check ({len(fn_ids)} function IDs)...")
    state = verify_daemon_state(fn_ids, "smoke-test")

    objs = _extract_count(state["status"], r'Objects:\s*(\d+)')
    txs = _extract_count(state["status"], r'Transactions:\s*(\d+)')
    rendered_len = len(state["rendered"])

    print(f"  Objects: {objs}")
    print(f"  Transactions: {txs}")
    print(f"  Rendered: {rendered_len} chars")
    print(f"  Rendered preview:\n{state['rendered'][:500]}")
    print(f"\n  Tx log lines: {state['tx_log'].count(chr(10)) + 1}")

    ok = True
    if not objs or objs < 2000:
        print(f"\nFAIL: objects {objs}, expected ~2474")
        ok = False
    if not txs or txs < 1000:
        print(f"\nFAIL: transactions {txs}, expected ~1757")
        ok = False
    if rendered_len < 100:
        print(f"\nFAIL: rendered too short ({rendered_len} chars)")
        ok = False
    if "helper" not in state["rendered"]:
        print(f"\nFAIL: 'helper' not in rendered (pre-rename)")
        ok = False
    if "ratio" not in state["rendered"]:
        print(f"\nFAIL: 'ratio' not in rendered")
        ok = False

    if ok:
        print("\nAll verifier checks PASS.")
    else:
        print("\nSome checks FAILED.")
        sys.exit(1)
finally:
    stop_daemon(proc, backup)

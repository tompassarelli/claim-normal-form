#!/usr/bin/env bash
# E16: Text-search agent simulation
# What would grep/text search find for each task?

CD="$(dirname "$0")/codebase"

echo "=== E16: Agent Grounding Evaluation — Text Search Side ==="
echo ""

# ================================================================
# TASK 01: Rename subtotal — grep for call sites
# ================================================================
echo "━━━ TASK 01: Rename subtotal ━━━"
echo "grep 'subtotal' finds:"
grep -n 'subtotal' "$CD"/pricing.py "$CD"/validation.py "$CD"/processing.py "$CD"/reporting.py "$CD"/test_orders.py 2>/dev/null | while read line; do
    echo "  $line"
done
echo ""
echo "Problem: grep matches dict keys ('\"subtotal\"'), display strings,"
echo "function definitions, and actual calls indiscriminately."
SUBTOTAL_MATCHES=$(grep -c 'subtotal' "$CD"/pricing.py "$CD"/validation.py "$CD"/processing.py "$CD"/reporting.py "$CD"/test_orders.py 2>/dev/null | awk -F: '{s+=$2} END{print s}')
echo "Total matches: $SUBTOTAL_MATCHES (includes false positives)"
echo ""

# ================================================================
# TASK 02: Blast radius of round_cents
# ================================================================
echo "━━━ TASK 02: Blast radius of round_cents ━━━"
echo "grep 'round_cents' finds direct references:"
DIRECT=$(grep -l 'round_cents' "$CD"/*.py 2>/dev/null | xargs -I{} basename {} | sort -u)
echo "  Files: $DIRECT"
DIRECT_COUNT=$(grep -rh 'round_cents(' "$CD"/*.py 2>/dev/null | grep -v '^\s*def ' | grep -v '^\s*#' | wc -l)
echo "  Direct call sites: $DIRECT_COUNT"
echo ""
echo "Problem: grep finds direct callers only. Cannot trace:"
echo "  round_cents <- line_total <- subtotal <- order_subtotal <- build_summary <- ..."
echo "  Manual recursion needed for each level."
echo ""

# ================================================================
# TASK 03: Shadowed names
# ================================================================
echo "━━━ TASK 03: Shadowed names ━━━"
for name in process total summary validate; do
    COUNT=$(grep -rn "${name}(" "$CD"/*.py 2>/dev/null | wc -l)
    echo "  grep '${name}(' matches: $COUNT lines"
    echo "    Sample:"
    grep -rn "${name}(" "$CD"/*.py 2>/dev/null | head -3 | while read line; do
        echo "      $line"
    done
done
echo ""
echo "Problem: 'process(' matches process() AND process_order()."
echo "         'total(' matches total(), subtotal(), order_total(), line_total()."
echo "         Cannot disambiguate which function is being called."
echo ""

# ================================================================
# TASK 04: Dead code
# ================================================================
echo "━━━ TASK 04: Dead code ━━━"
echo "Checking each function for callers via grep:"
for func in legacy_tax_calc format_currency debug_order process total summary validate; do
    # Count references outside the definition
    REFS=$(grep -rn "${func}" "$CD"/*.py 2>/dev/null | grep -v "^\s*def ${func}" | grep -v "^\s*#" | grep -v "import" | wc -l)
    echo "  ${func}: $REFS references (includes definition, strings, comments)"
done
echo ""
echo "Problem: grep for 'total' matches subtotal, order_total, line_total, daily_total,"
echo "etc. Cannot determine if standalone total() has zero callers."
echo ""

# ================================================================
# TASK 08: full_report dependency tree
# ================================================================
echo "━━━ TASK 08: full_report dependency tree ━━━"
echo "grep for function calls in full_report body:"
# Extract full_report function body (rough)
echo "  Direct calls found by grep:"
sed -n '/^def full_report/,/^def /p' "$CD"/reporting.py | grep -oP '[a-z_]+\(' | sort -u | while read call; do
    echo "    $call"
done
echo ""
echo "Problem: only finds depth-1 calls. The full tree is 25+ functions"
echo "deep through 5 layers. Manual recursion required for each."
echo ""

# ================================================================
# TASK 09: Rename order_total
# ================================================================
echo "━━━ TASK 09: Rename order_total ━━━"
echo "grep 'order_total' finds:"
grep -rn 'order_total' "$CD"/*.py 2>/dev/null | while read line; do
    echo "  $line"
done
echo ""
echo "Separate grep for 'total(' to check for shadowing:"
grep -rn '[^_]total(' "$CD"/processing.py 2>/dev/null | while read line; do
    echo "  $line"
done
echo "Problem: must manually verify processing.total() is a different function."
echo ""

# ================================================================
# TASK 10: Cross-session
# ================================================================
echo "━━━ TASK 10: Cross-session ━━━"
echo "Text search has no persistence mechanism."
echo "Agent must re-read, re-grep, re-analyze from scratch."
echo "Score: 0/10 (structurally impossible)"
echo ""

echo "=== Text search evaluation complete ==="

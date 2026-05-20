import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from order_system import *


def test_line_total():
    assert line_total("WIDGET", 2) == 50.00


def test_cart_total():
    assert cart_total([("WIDGET", 2), ("GIZMO", 1)]) == 65.00


def test_checkout_standard():
    result = checkout([("WIDGET", 2)], "standard")
    assert result["subtotal"] == 50.00
    assert result["total"] == 50.00


def test_checkout_premium():
    result = checkout([("WIDGET", 2)], "premium")
    assert result["total"] == 45.00
    assert result["saved"] == 5.00


def test_receipt():
    result = checkout([("GADGET", 1)], "standard")
    assert "49.99" in format_receipt(result)


if __name__ == "__main__":
    passed = failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                passed += 1
            except Exception as e:
                print(f"FAIL: {name}: {e}")
                failed += 1
    print(f"{passed} passed, {failed} failed")

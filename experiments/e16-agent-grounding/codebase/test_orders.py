"""Test suite for the order processing system.

These tests verify current behavior. Tasks may require updating
tests alongside code changes.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from models import Item, Order, Address, Discount, OrderStatus
from pricing import (
    round_cents, clamp, safe_divide, tax_rate, tax_amount,
    unit_price, line_total, subtotal, discount_rate, discount_amount,
    shipping_base, shipping_weight_surcharge, shipping_cost,
    order_subtotal, order_discount, order_tax, order_shipping, order_total
)
from validation import (
    validate_item, validate_items, validate_address,
    validate_discount, validate_region, validate_order, is_valid_order
)
from processing import (
    build_line_items, build_summary, build_receipt, process_order, process_batch
)
from reporting import (
    order_margin, high_value_items, region_breakdown, discount_impact,
    shipping_breakdown, daily_revenue, revenue_report, full_report
)


# --- Test fixtures ---

def make_item(sku="SKU001", name="Widget", qty=2, price=25.00, weight=1.0, cost=10.0):
    return Item(sku=sku, name=name, quantity=qty, price=price, weight=weight, cost=cost)

def make_address(region="US-CA"):
    return Address(street="123 Main St", city="Springfield", region=region,
                   postal_code="90210", country="US")

def make_order(items=None, region="US-CA", discount_code=None, shipping="standard"):
    if items is None:
        items = [make_item()]
    order = Order(id="ORD-001", items=items, address=make_address(region),
                  shipping_method=shipping)
    if discount_code:
        order.discount = Discount(code=discount_code, rate=discount_rate(discount_code))
    return order


# --- Pricing tests ---

def test_round_cents():
    assert round_cents(1.005) == 1.0  # Python banker's rounding
    assert round_cents(1.015) == 1.01
    assert round_cents(99.999) == 100.0

def test_clamp():
    assert clamp(5, 0, 10) == 5
    assert clamp(-1, 0, 10) == 0
    assert clamp(15, 0, 10) == 10

def test_tax_rate():
    assert tax_rate("US-CA") == 0.0725
    assert tax_rate("US-OR") == 0.0
    assert tax_rate("UNKNOWN") == 0.0

def test_line_total():
    item = make_item(qty=3, price=10.50)
    assert line_total(item) == 31.50

def test_subtotal():
    items = [make_item(qty=2, price=25.00), make_item(qty=1, price=10.00)]
    assert subtotal(items) == 60.00

def test_discount_rate():
    assert discount_rate("SAVE10") == 0.10
    assert discount_rate("VIP") == 0.30
    assert discount_rate("BOGUS") == 0.0
    assert discount_rate("NONE") == 0.0

def test_discount_amount():
    assert discount_amount(100.0, "SAVE10") == 10.0
    assert discount_amount(100.0, "NONE") == 0.0

def test_shipping_cost():
    light_items = [make_item(qty=1, weight=0.5)]
    heavy_items = [make_item(qty=100, weight=1.0)]
    assert shipping_cost(light_items, "standard") == 5.99
    assert shipping_cost(heavy_items, "standard") > 5.99

def test_order_total():
    order = make_order()
    total = order_total(order)
    assert total > 0
    sub = order_subtotal(order)
    tax = order_tax(order)
    ship = order_shipping(order)
    disc = order_discount(order)
    assert total == round_cents(sub - disc + tax + ship)


# --- Validation tests ---

def test_validate_item_ok():
    assert validate_item(make_item()) == []

def test_validate_item_bad_price():
    item = make_item(price=-5.0)
    errors = validate_item(item)
    assert len(errors) == 1
    assert "price" in errors[0]

def test_validate_item_bad_quantity():
    item = make_item(qty=0)
    errors = validate_item(item)
    assert len(errors) == 1
    assert "quantity" in errors[0]

def test_validate_empty_items():
    errors = validate_items([])
    assert len(errors) == 1
    assert "at least one" in errors[0]

def test_validate_discount_unknown():
    errors = validate_discount("FAKECODE")
    assert len(errors) == 1

def test_validate_order_ok():
    order = make_order()
    assert validate_order(order) == []

def test_validate_order_no_address():
    order = Order(id="ORD-002", items=[make_item()])
    errors = validate_order(order)
    assert any("address" in e.lower() for e in errors)


# --- Processing tests ---

def test_build_line_items():
    order = make_order()
    lines = build_line_items(order)
    assert len(lines) == 1
    assert lines[0]["sku"] == "SKU001"
    assert "subtotal" in lines[0]  # string display field

def test_build_summary():
    order = make_order()
    s = build_summary(order)
    assert "subtotal" in s
    assert "total" in s
    assert s["total"] > 0

def test_process_order_ok():
    order = make_order()
    result = process_order(order)
    assert result["status"] == "ok"
    assert "receipt" in result

def test_process_order_invalid():
    order = Order(id="ORD-003", items=[])
    result = process_order(order)
    assert result["status"] == "error"

def test_process_batch():
    orders = [make_order(), make_order()]
    result = process_batch(orders)
    assert result["total"] == 2
    assert result["succeeded"] == 2


# --- Reporting tests ---

def test_order_margin():
    order = make_order(items=[make_item(price=100.0, cost=30.0, qty=1)])
    margin = order_margin(order)
    assert 0 < margin < 1

def test_high_value_items():
    items = [make_item(qty=1, price=50.0), make_item(qty=10, price=50.0)]
    high = high_value_items(items, 100.0)
    assert len(high) == 1

def test_region_breakdown():
    orders = [make_order(region="US-CA"), make_order(region="US-NY")]
    breakdown = region_breakdown(orders)
    assert "US-CA" in breakdown
    assert "US-NY" in breakdown

def test_daily_revenue():
    orders = [make_order(), make_order()]
    rev = daily_revenue(orders)
    assert rev > 0

def test_full_report():
    orders = [make_order()]
    report = full_report(orders)
    assert "daily_total" in report
    assert "high_value_item_count" in report
    assert "avg_margin" in report


# --- Runner ---

def run_tests():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            passed += 1
            print(f"  PASS {test.__name__}")
        except Exception as e:
            failed += 1
            print(f"  FAIL {test.__name__}: {e}")
    print(f"\n{passed} passed, {failed} failed, {passed + failed} total")
    return failed == 0


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)

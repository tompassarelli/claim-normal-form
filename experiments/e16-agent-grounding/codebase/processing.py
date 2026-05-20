"""Order processing pipeline."""

from models import Order, OrderStatus, Item
from pricing import (
    order_subtotal, order_discount, order_tax, order_shipping,
    order_total, line_total, unit_price, subtotal, round_cents,
    discount_rate, shipping_cost
)
from validation import validate_order, is_valid_order
from typing import Dict, List, Optional


def build_line_items(order: Order) -> List[Dict]:
    """Build detailed line items for an order."""
    return [
        {
            "sku": item.sku,
            "name": item.name,
            "quantity": item.quantity,
            "unit_price": unit_price(item),
            "line_total": line_total(item),
            "subtotal": f"${line_total(item):.2f}",  # display string, not function call
        }
        for item in order.items
    ]


def build_summary(order: Order) -> Dict:
    """Build order price summary."""
    return {
        "subtotal": order_subtotal(order),
        "discount": order_discount(order),
        "discount_rate": discount_rate(order.discount.code if order.discount else "NONE"),
        "tax": order_tax(order),
        "shipping": order_shipping(order),
        "total": order_total(order),
    }


def build_receipt(order: Order) -> Dict:
    """Build a full receipt."""
    return {
        "order_id": order.id,
        "line_items": build_line_items(order),
        "summary": build_summary(order),
        "address": {
            "street": order.address.street,
            "city": order.address.city,
            "region": order.address.region,
        } if order.address else None,
        "status": order.status.value,
    }


def process_order(order: Order) -> Dict:
    """Validate and process an order."""
    errors = validate_order(order)
    if errors:
        return {"status": "error", "errors": errors}
    order.status = OrderStatus.VALIDATED
    receipt = build_receipt(order)
    order.status = OrderStatus.PRICED
    return {"status": "ok", "receipt": receipt}


def process_batch(orders: List[Order]) -> Dict:
    """Process multiple orders."""
    results = []
    for order in orders:
        results.append(process_order(order))
    succeeded = sum(1 for r in results if r["status"] == "ok")
    return {
        "total": len(orders),
        "succeeded": succeeded,
        "failed": len(orders) - succeeded,
        "results": results,
    }


# --- These shadow names from other modules ---

def process(items: list) -> list:
    """Generic list processor. NOT process_order."""
    return [x for x in items if x is not None]


def total(values: list) -> float:
    """Generic sum. NOT order_total or subtotal."""
    return sum(v for v in values if isinstance(v, (int, float)))


def summary(label: str, count: int) -> str:
    """Generic summary string. NOT build_summary."""
    return f"{label}: {count}"

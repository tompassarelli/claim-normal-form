"""Reporting and analytics."""

from models import Order, Item
from pricing import (
    order_total, order_subtotal, order_discount, order_tax,
    order_shipping, subtotal, discount_amount, shipping_cost,
    line_total, round_cents, safe_divide, unit_price
)
from typing import List, Dict


def order_margin(order: Order) -> float:
    """Profit margin for an order."""
    cost = sum(item.cost * item.quantity for item in order.items)
    revenue = order_subtotal(order) - order_discount(order)
    return safe_divide(revenue - cost, revenue)


def high_value_items(items: List[Item], threshold: float = 100.0) -> List[Item]:
    """Items with line total above threshold."""
    return [i for i in items if line_total(i) >= threshold]


def region_breakdown(orders: List[Order]) -> Dict[str, float]:
    """Revenue by region."""
    breakdown: Dict[str, float] = {}
    for order in orders:
        region = order.address.region if order.address else "unknown"
        breakdown[region] = breakdown.get(region, 0) + order_total(order)
    return {k: round_cents(v) for k, v in breakdown.items()}


def discount_impact(orders: List[Order]) -> Dict:
    """How much discounts cost us."""
    gross = sum(order_subtotal(o) for o in orders)
    total_discount = sum(order_discount(o) for o in orders)
    return {
        "gross_revenue": round_cents(gross),
        "total_discount": round_cents(total_discount),
        "net_revenue": round_cents(gross - total_discount),
        "discount_pct": round_cents(safe_divide(total_discount, gross) * 100),
    }


def shipping_breakdown(orders: List[Order]) -> Dict[str, float]:
    """Shipping costs by method."""
    breakdown: Dict[str, float] = {}
    for order in orders:
        method = order.shipping_method
        cost = order_shipping(order)
        breakdown[method] = breakdown.get(method, 0) + cost
    return {k: round_cents(v) for k, v in breakdown.items()}


def daily_revenue(orders: List[Order]) -> float:
    """Total revenue for a batch of orders."""
    return round_cents(sum(order_total(o) for o in orders))


def revenue_report(orders: List[Order]) -> Dict:
    """Full revenue report."""
    return {
        "daily_total": daily_revenue(orders),
        "by_region": region_breakdown(orders),
        "by_shipping": shipping_breakdown(orders),
        "discounts": discount_impact(orders),
    }


def full_report(orders: List[Order]) -> Dict:
    """Complete business report."""
    report = revenue_report(orders)
    all_items = [item for o in orders for item in o.items]
    high_value = high_value_items(all_items, 100.0)
    margins = [order_margin(o) for o in orders]
    report["high_value_item_count"] = len(high_value)
    report["avg_margin"] = round_cents(safe_divide(sum(margins), len(margins))) if margins else 0
    report["total_orders"] = len(orders)
    return report


# --- Dead code ---

def legacy_tax_calc(amount: float, rate: float) -> float:
    """DEPRECATED: Old tax calculation. Use tax_amount instead."""
    return round(amount * rate, 2)


def format_currency(amount: float) -> str:
    """Format as currency string. Currently unused."""
    return f"${amount:,.2f}"


def debug_order(order: Order) -> str:
    """Debug output. Was used during development, now dead."""
    return f"Order {order.id}: {len(order.items)} items, status={order.status.value}"

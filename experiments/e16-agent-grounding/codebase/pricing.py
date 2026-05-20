"""Pricing calculations for orders."""

from models import Item, Order, Discount
from typing import List, Dict


# --- Primitives ---

def round_cents(amount: float) -> float:
    """Round to 2 decimal places."""
    return round(amount, 2)


def clamp(value: float, low: float, high: float) -> float:
    """Clamp value to [low, high]."""
    if value < low:
        return low
    if value > high:
        return high
    return value


def safe_divide(a: float, b: float) -> float:
    """Division that returns 0 for divide-by-zero."""
    if b == 0:
        return 0.0
    return a / b


# --- Tax ---

TAX_RATES = {
    "US-CA": 0.0725,
    "US-NY": 0.08,
    "US-TX": 0.0625,
    "US-OR": 0.0,
    "CA-ON": 0.13,
    "CA-BC": 0.12,
    "UK": 0.20,
    "EU": 0.21,
}


def tax_rate(region: str) -> float:
    """Look up tax rate for a region."""
    return TAX_RATES.get(region, 0.0)


def tax_amount(subtotal: float, region: str) -> float:
    """Calculate tax on a subtotal."""
    return round_cents(subtotal * tax_rate(region))


# --- Line items ---

def unit_price(item: Item) -> float:
    """Get the unit price of an item."""
    return item.price


def line_total(item: Item) -> float:
    """Calculate line total for an item."""
    return round_cents(unit_price(item) * item.quantity)


def subtotal(items: List[Item]) -> float:
    """Sum of all line totals."""
    return round_cents(sum(line_total(i) for i in items))


# --- Discounts ---

DISCOUNT_CODES = {
    "SAVE10": 0.10,
    "SAVE20": 0.20,
    "VIP": 0.30,
    "WELCOME": 0.15,
    "NONE": 0.0,
}


def discount_rate(code: str) -> float:
    """Look up discount rate, clamped to [0, 0.50]."""
    raw = DISCOUNT_CODES.get(code, 0.0)
    return clamp(raw, 0.0, 0.50)


def discount_amount(item_subtotal: float, code: str) -> float:
    """Calculate discount on a subtotal."""
    return round_cents(item_subtotal * discount_rate(code))


# --- Shipping ---

SHIPPING_RATES = {
    "standard": 5.99,
    "express": 14.99,
    "overnight": 29.99,
    "pickup": 0.0,
}


def shipping_base(method: str) -> float:
    """Base shipping cost for a method."""
    return SHIPPING_RATES.get(method, 5.99)


def shipping_weight_surcharge(items: List[Item]) -> float:
    """Extra cost based on total weight."""
    total_weight = sum(i.weight * i.quantity for i in items)
    if total_weight > 50:
        return round_cents(total_weight * 0.75)
    elif total_weight > 20:
        return round_cents(total_weight * 0.50)
    return 0.0


def shipping_cost(items: List[Item], method: str) -> float:
    """Total shipping cost."""
    return round_cents(shipping_base(method) + shipping_weight_surcharge(items))


# --- Order total ---

def order_subtotal(order: Order) -> float:
    """Subtotal for an order."""
    return subtotal(order.items)


def order_discount(order: Order) -> float:
    """Discount amount for an order."""
    code = order.discount.code if order.discount else "NONE"
    return discount_amount(order_subtotal(order), code)


def order_tax(order: Order) -> float:
    """Tax for an order."""
    region = order.address.region if order.address else "US-CA"
    taxable = order_subtotal(order) - order_discount(order)
    return tax_amount(taxable, region)


def order_shipping(order: Order) -> float:
    """Shipping for an order."""
    return shipping_cost(order.items, order.shipping_method)


def order_total(order: Order) -> float:
    """Final order total."""
    return round_cents(
        order_subtotal(order)
        - order_discount(order)
        + order_tax(order)
        + order_shipping(order)
    )

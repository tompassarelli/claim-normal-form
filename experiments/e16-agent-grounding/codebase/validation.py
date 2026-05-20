"""Order validation."""

from models import Item, Order, Address
from pricing import unit_price, discount_rate, tax_rate, subtotal
from typing import List


def validate_item(item: Item) -> List[str]:
    """Validate a single item."""
    errors = []
    if unit_price(item) <= 0:
        errors.append(f"Item {item.sku}: price must be positive")
    if item.quantity <= 0:
        errors.append(f"Item {item.sku}: quantity must be positive")
    if item.quantity > 1000:
        errors.append(f"Item {item.sku}: quantity exceeds limit")
    return errors


def validate_items(items: List[Item]) -> List[str]:
    """Validate all items in an order."""
    if not items:
        return ["Order must have at least one item"]
    errors = []
    for item in items:
        errors.extend(validate_item(item))
    return errors


def validate_address(address: Address) -> List[str]:
    """Validate a shipping address."""
    errors = []
    if not address.street:
        errors.append("Street is required")
    if not address.city:
        errors.append("City is required")
    if not address.region:
        errors.append("Region is required")
    if not address.country:
        errors.append("Country is required")
    return errors


def validate_discount(code: str) -> List[str]:
    """Validate a discount code."""
    rate = discount_rate(code)
    if rate == 0.0 and code not in ("NONE", ""):
        return [f"Unknown discount code: {code}"]
    return []


def validate_region(region: str) -> List[str]:
    """Validate that a region has a known tax rate."""
    if tax_rate(region) == 0.0 and region != "US-OR":
        return [f"Unknown tax region: {region}"]
    return []


def validate_order(order: Order) -> List[str]:
    """Full order validation."""
    errors = []
    errors.extend(validate_items(order.items))
    if order.address:
        errors.extend(validate_address(order.address))
        errors.extend(validate_region(order.address.region))
    else:
        errors.append("Shipping address is required")
    if order.discount:
        errors.extend(validate_discount(order.discount.code))
    # BUG: should validate subtotal > 0 after discount
    # Currently allows 100% discount orders through
    return errors


# --- Convenience ---

def validate(text: str) -> bool:
    """Validate a generic string is non-empty. NOT validate_order."""
    return len(text.strip()) > 0


def is_valid_order(order: Order) -> bool:
    """Check if order passes validation."""
    return len(validate_order(order)) == 0

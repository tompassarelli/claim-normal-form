"""E15 test codebase: order processing system.

50 functions across 5 layers. Designed so that structural questions
have non-obvious answers that grep gets wrong.
"""

# === Layer 0: Primitives ===

def clamp(value: float, low: float, high: float) -> float:
    if value < low:
        return low
    if value > high:
        return high
    return value

def round_cents(amount: float) -> float:
    return round(amount, 2)

def safe_divide(a: float, b: float) -> float:
    if b == 0:
        return 0.0
    return a / b

def merge_dicts(base: dict, override: dict) -> dict:
    result = dict(base)
    result.update(override)
    return result

def flatten(nested: list) -> list:
    result = []
    for item in nested:
        if isinstance(item, list):
            result.extend(flatten(item))
        else:
            result.append(item)
    return result

# === Layer 1: Domain calculations ===

def unit_price(item: dict) -> float:
    return item["price"]

def line_total(item: dict) -> float:
    return round_cents(unit_price(item) * item["quantity"])

def subtotal(items: list) -> float:
    return round_cents(sum(line_total(i) for i in items))

def tax_rate(region: str) -> float:
    rates = {"US": 0.08, "EU": 0.20, "UK": 0.20, "CA": 0.13, "JP": 0.10}
    return rates.get(region, 0.0)

def tax_amount(items: list, region: str) -> float:
    return round_cents(subtotal(items) * tax_rate(region))

def discount_rate(code: str) -> float:
    codes = {"SAVE10": 0.10, "SAVE20": 0.20, "VIP": 0.30, "NONE": 0.0}
    return clamp(codes.get(code, 0.0), 0.0, 0.50)

def discount_amount(items: list, code: str) -> float:
    return round_cents(subtotal(items) * discount_rate(code))

def shipping_cost(items: list, method: str) -> float:
    weight = sum(i.get("weight", 0.5) for i in items)
    base = {"standard": 5.0, "express": 15.0, "overnight": 30.0}
    return round_cents(base.get(method, 5.0) + weight * 0.5)

def order_total(items: list, region: str, code: str, method: str) -> float:
    sub = subtotal(items)
    disc = discount_amount(items, code)
    tx = tax_amount(items, region)
    ship = shipping_cost(items, method)
    return round_cents(sub - disc + tx + ship)

# === Layer 2: Validation ===

def validate_item(item: dict) -> list:
    errors = []
    if unit_price(item) <= 0:
        errors.append("price must be positive")
    if item.get("quantity", 0) <= 0:
        errors.append("quantity must be positive")
    return errors

def validate_items(items: list) -> list:
    return flatten([validate_item(i) for i in items])

def validate_discount(code: str) -> list:
    rate = discount_rate(code)
    if rate == 0.0 and code != "NONE":
        return [f"unknown discount code: {code}"]
    return []

def validate_region(region: str) -> list:
    if tax_rate(region) == 0.0 and region != "ZERO_TAX":
        return [f"unknown region: {region}"]
    return []

def validate_order(items: list, region: str, code: str) -> list:
    return flatten([
        validate_items(items),
        validate_discount(code),
        validate_region(region),
    ])

# === Layer 3: Order processing ===

def build_line_items(items: list) -> list:
    return [
        merge_dicts(item, {
            "line_total": line_total(item),
            "unit_price": unit_price(item),
        })
        for item in items
    ]

def build_summary(items: list, region: str, code: str, method: str) -> dict:
    return {
        "subtotal": subtotal(items),
        "discount": discount_amount(items, code),
        "discount_rate": discount_rate(code),
        "tax": tax_amount(items, region),
        "tax_rate": tax_rate(region),
        "shipping": shipping_cost(items, method),
        "total": order_total(items, region, code, method),
    }

def build_order(items: list, region: str, code: str, method: str) -> dict:
    return {
        "line_items": build_line_items(items),
        "summary": build_summary(items, region, code, method),
        "valid": len(validate_order(items, region, code)) == 0,
    }

def process_order(order_data: dict) -> dict:
    items = order_data["items"]
    region = order_data.get("region", "US")
    code = order_data.get("discount_code", "NONE")
    method = order_data.get("shipping", "standard")
    errors = validate_order(items, region, code)
    if errors:
        return {"status": "error", "errors": errors}
    return {"status": "ok", "order": build_order(items, region, code, method)}

# === Layer 4: Reporting ===

def order_margin(items: list, code: str) -> float:
    cost = sum(i.get("cost", 0) for i in items)
    revenue = subtotal(items) - discount_amount(items, code)
    return safe_divide(revenue - cost, revenue)

def high_value_items(items: list, threshold: float) -> list:
    return [i for i in items if line_total(i) >= threshold]

def region_breakdown(orders: list) -> dict:
    breakdown = {}
    for o in orders:
        region = o.get("region", "US")
        total = order_total(o["items"], region, o.get("discount_code", "NONE"), o.get("shipping", "standard"))
        breakdown[region] = breakdown.get(region, 0) + total
    return breakdown

def discount_impact(orders: list) -> dict:
    total_without = sum(subtotal(o["items"]) for o in orders)
    total_with = sum(
        subtotal(o["items"]) - discount_amount(o["items"], o.get("discount_code", "NONE"))
        for o in orders
    )
    return {
        "gross": round_cents(total_without),
        "net": round_cents(total_with),
        "discount_pct": round_cents(safe_divide(total_without - total_with, total_without) * 100),
    }

def shipping_breakdown(orders: list) -> dict:
    breakdown = {}
    for o in orders:
        method = o.get("shipping", "standard")
        cost = shipping_cost(o["items"], method)
        breakdown[method] = breakdown.get(method, 0) + cost
    return breakdown

def daily_revenue(orders: list) -> float:
    return round_cents(sum(
        order_total(o["items"], o.get("region", "US"), o.get("discount_code", "NONE"), o.get("shipping", "standard"))
        for o in orders
    ))

def revenue_report(orders: list) -> dict:
    return {
        "daily_total": daily_revenue(orders),
        "by_region": region_breakdown(orders),
        "shipping": shipping_breakdown(orders),
        "discounts": discount_impact(orders),
    }

def full_report(orders: list) -> dict:
    return merge_dicts(revenue_report(orders), {
        "high_value_count": len(flatten([high_value_items(o["items"], 100.0) for o in orders])),
        "avg_margin": round_cents(safe_divide(
            sum(order_margin(o["items"], o.get("discount_code", "NONE")) for o in orders),
            len(orders)
        )),
    })

# === Cross-cutting: functions that shadow names ===

def process(data: list) -> list:
    """Not process_order. A generic list processor."""
    return [x for x in data if x is not None]

def validate(thing: str) -> bool:
    """Not validate_order. A generic string validator."""
    return len(thing) > 0

def total(values: list) -> float:
    """Not subtotal or order_total. A generic sum."""
    return sum(values)

def rate(value: float, base: float) -> float:
    """Not tax_rate or discount_rate. A generic ratio."""
    return safe_divide(value, base)

def summary(items: list) -> str:
    """Not build_summary. A generic summary string."""
    return f"{len(items)} items"

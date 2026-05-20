def get_price(product_id):
    catalog = {"WIDGET": 25.00, "GADGET": 49.99, "GIZMO": 15.00}
    return catalog.get(product_id, 0.0)


def get_discount_rate(customer_type):
    rates = {"standard": 0.0, "premium": 0.10, "vip": 0.20}
    return rates.get(customer_type, 0.0)


def get_tax_rate(region):
    taxes = {"US-CA": 0.0725, "US-OR": 0.0, "US-NY": 0.08}
    return taxes.get(region, 0.05)


def line_total(product_id, quantity):
    return get_price(product_id) * quantity


def cart_total(items):
    return sum(line_total(pid, qty) for pid, qty in items)


def apply_discount(total, customer_type):
    rate = get_discount_rate(customer_type)
    return round(total * (1 - rate), 2)


def checkout(items, customer_type):
    total = cart_total(items)
    final = apply_discount(total, customer_type)
    return {"subtotal": total, "total": final, "saved": round(total - final, 2)}


def format_receipt(result):
    lines = []
    lines.append("Subtotal: $" + str(round(result["subtotal"], 2)))
    lines.append("Total:    $" + str(round(result["total"], 2)))
    lines.append("Saved:    $" + str(round(result["saved"], 2)))
    return "\n".join(lines)

"""Order pricing: line amounts, subtotal, bulk discount and total (KRW integers)."""

DISCOUNT_THRESHOLD = 50_000
DISCOUNT_PERCENT = 10


def price_order(lines: list[dict]) -> dict:
    """Price an order.

    Each line is {"sku": str, "unit_price": int, "qty": int}. Raises ValueError
    when qty < 1 or unit_price < 0. A subtotal of 50,000 or more gets 10% off,
    rounded down to whole won.
    """
    priced = []
    subtotal = 0
    for line in lines:
        unit_price = line["unit_price"]
        qty = line["qty"]
        if qty < 1:
            raise ValueError(f"qty must be at least 1: {qty}")
        if unit_price < 0:
            raise ValueError(f"unit_price must not be negative: {unit_price}")
        amount = unit_price * qty
        priced.append(
            {"sku": line["sku"], "unit_price": unit_price, "qty": qty, "amount": amount}
        )
        subtotal += amount
    discount = subtotal * DISCOUNT_PERCENT // 100 if subtotal >= DISCOUNT_THRESHOLD else 0
    return {
        "lines": priced,
        "subtotal": subtotal,
        "discount": discount,
        "total": subtotal - discount,
    }

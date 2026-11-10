"""Receipt rendering on top of a pluggable pricer."""

from orderdesk.pricing import price_order


def render_receipt(order: dict, pricer=price_order) -> str:
    """Render receipt text for ``order`` using ``pricer(order["lines"])``."""
    result = pricer(order["lines"])
    out = [f"ORDER {order['order_id']}"]
    for line in result["lines"]:
        out.append(f"{line['sku']} x{line['qty']} {line['amount']}")
    out.append(f"SUBTOTAL {result['subtotal']}")
    out.append(f"DISCOUNT {result['discount']}")
    out.append(f"TOTAL {result['total']}")
    return "\n".join(out)

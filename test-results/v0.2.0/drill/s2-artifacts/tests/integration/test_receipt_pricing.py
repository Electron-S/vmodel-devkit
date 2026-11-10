import pytest

from orderdesk.receipt import render_receipt


def test_TEST_013_receipt_uses_real_price_order():
    order = {
        "order_id": "O-9",
        "lines": [
            {"sku": "A", "unit_price": 25000, "qty": 2},
            {"sku": "B", "unit_price": 10, "qty": 1},
        ],
    }
    assert render_receipt(order) == (
        "ORDER O-9\nA x2 50000\nB x1 10\nSUBTOTAL 50010\nDISCOUNT 5001\nTOTAL 45009"
    )


def test_TEST_014_value_error_from_real_price_order():
    order = {"order_id": "O-10", "lines": [{"sku": "A", "unit_price": 1000, "qty": 0}]}
    with pytest.raises(ValueError):
        render_receipt(order)

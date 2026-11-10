import inspect

import pytest

from orderdesk.receipt import render_receipt


def test_TEST_009_receipt_with_fake_pricer():
    calls = []

    def fake(lines):
        calls.append(lines)
        return {
            "lines": [
                {"sku": "A", "unit_price": 1000, "qty": 2, "amount": 2000},
                {"sku": "B", "unit_price": 10, "qty": 1, "amount": 10},
            ],
            "subtotal": 2010,
            "discount": 0,
            "total": 2010,
        }

    raw = [{"sku": "A", "unit_price": 1000, "qty": 2}]
    text = render_receipt({"order_id": "O-1", "lines": raw}, pricer=fake)
    assert text == "ORDER O-1\nA x2 2000\nB x1 10\nSUBTOTAL 2010\nDISCOUNT 0\nTOTAL 2010"
    assert calls == [raw]


def test_TEST_010_pricer_value_error_propagates():
    def fake(lines):
        raise ValueError("bad")

    with pytest.raises(ValueError, match="bad"):
        render_receipt({"order_id": "O-2", "lines": []}, pricer=fake)


def test_TEST_011_empty_lines_four_line_receipt():
    def fake(lines):
        return {"lines": [], "subtotal": 0, "discount": 0, "total": 0}

    text = render_receipt({"order_id": "O-3", "lines": []}, pricer=fake)
    assert text == "ORDER O-3\nSUBTOTAL 0\nDISCOUNT 0\nTOTAL 0"


def test_TEST_012_default_pricer_is_price_order():
    default = inspect.signature(render_receipt).parameters["pricer"].default
    assert callable(default)
    assert default.__name__ == "price_order"
    assert default.__module__ == "orderdesk.pricing"

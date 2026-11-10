import pytest

from orderdesk.pricing import price_order


def _one(price, qty=1):
    return price_order([{"sku": "A", "unit_price": price, "qty": qty}])


def test_TEST_001_lines_and_subtotal():
    r = price_order(
        [
            {"sku": "A", "unit_price": 1000, "qty": 3},
            {"sku": "B", "unit_price": 500, "qty": 2},
        ]
    )
    assert r["lines"] == [
        {"sku": "A", "unit_price": 1000, "qty": 3, "amount": 3000},
        {"sku": "B", "unit_price": 500, "qty": 2, "amount": 1000},
    ]
    assert (r["subtotal"], r["discount"], r["total"]) == (4000, 0, 4000)


def test_TEST_002_qty_zero_rejected():
    with pytest.raises(ValueError):
        _one(1000, 0)


def test_TEST_003_negative_price_rejected():
    with pytest.raises(ValueError):
        _one(-1)


def test_TEST_004_empty_list():
    assert price_order([]) == {"lines": [], "subtotal": 0, "discount": 0, "total": 0}


def test_TEST_005_subtotal_49999_no_discount():
    r = _one(49999)
    assert (r["subtotal"], r["discount"], r["total"]) == (49999, 0, 49999)


def test_TEST_006_subtotal_50000_discount():
    r = _one(25000, 2)
    assert (r["subtotal"], r["discount"], r["total"]) == (50000, 5000, 45000)


def test_TEST_007_subtotal_50009_rounds_down():
    r = _one(50009)
    assert (r["subtotal"], r["discount"], r["total"]) == (50009, 5000, 45009)


def test_TEST_008_zero_price_allowed():
    r = _one(0)
    assert r["lines"][0]["amount"] == 0
    assert (r["subtotal"], r["discount"], r["total"]) == (0, 0, 0)

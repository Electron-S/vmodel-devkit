import pytest

from scorestats.percentile import percentile

SAMPLE = [15, 20, 35, 40, 50]


def test_TEST_001_p30_returns_20():
    assert percentile(SAMPLE, 30) == 20


@pytest.mark.parametrize(
    "p, expected",
    [(5, 15), (30, 20), (40, 20), (50, 35), (100, 50)],
)
def test_TEST_001_request_examples(p, expected):
    assert percentile(SAMPLE, p) == expected


def test_TEST_002_unsorted_float_list():
    assert percentile([3.5, 1.5, 2.5, 4.5], 50) == 2.5


def test_TEST_003_input_list_unchanged():
    scores = [50, 15, 40, 20, 35]
    assert percentile(scores, 50) == 35
    assert scores == [50, 15, 40, 20, 35]


def test_TEST_004_p_out_of_range_raises():
    for p in (0, 101, -5):
        with pytest.raises(ValueError):
            percentile([1, 2, 3], p)


def test_TEST_005_non_integer_p_raises():
    for p in (50.5, "50", True, 50.0):
        with pytest.raises(ValueError):
            percentile([1, 2, 3], p)


def test_TEST_006_empty_list_raises():
    with pytest.raises(ValueError):
        percentile([], 50)


def test_TEST_007_p1_returns_minimum():
    assert percentile([40, 15, 50, 20, 35], 1) == 15


def test_TEST_008_p100_returns_maximum():
    assert percentile([40, 15, 50, 20, 35], 100) == 50


def test_TEST_009_single_element_any_p():
    for p in (1, 50, 100):
        assert percentile([7], p) == 7


def test_TEST_010_rank_kept_when_product_multiple_of_100():
    assert percentile([15, 20, 35, 40, 50], 40) == 20


def test_TEST_011_p29_n100_integer_rank():
    assert percentile(list(range(1, 101)), 29) == 29


def test_TEST_012_duplicates_selected_by_rank():
    assert percentile([5, 5, 5, 9, 1], 80) == 5
    assert percentile([5, 5, 5, 9, 1], 100) == 9

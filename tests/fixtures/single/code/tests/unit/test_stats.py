import pytest

from meanstat.stats import mean


def test_TEST_001_mean_of_values():
    assert mean([1, 2, 3]) == 2


def test_TEST_002_mean_rejects_empty():
    with pytest.raises(ValueError):
        mean([])


def test_TEST_003_mean_single_value():
    assert mean([5]) == 5

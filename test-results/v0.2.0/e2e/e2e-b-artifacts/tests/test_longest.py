import pytest

from textstats.longest import longest_word


def test_TEST_001_longest_of_several():
    assert longest_word("a bbb cc") == "bbb"


def test_TEST_002_tie_returns_first():
    assert longest_word("aa bb c") == "aa"


def test_TEST_003_single_word():
    assert longest_word("hello") == "hello"


def test_TEST_004_extra_whitespace_ignored():
    assert longest_word("  hello   world  ") == "hello"


def test_TEST_005_empty_raises():
    with pytest.raises(ValueError):
        longest_word("")


def test_TEST_006_whitespace_only_raises():
    with pytest.raises(ValueError):
        longest_word("   \t\n")


def test_TEST_007_single_space_raises():
    with pytest.raises(ValueError):
        longest_word(" ")

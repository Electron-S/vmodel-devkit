import pytest

from textcli.__main__ import count_text


def test_TEST_001_counts_normal_text():
    assert count_text("hello world\nfoo\n") == (2, 3, 16)


def test_TEST_002_empty_text():
    assert count_text("") == (0, 0, 0)


def test_TEST_003_only_newline():
    assert count_text("\n") == (1, 0, 1)


def test_TEST_004_no_trailing_newline():
    assert count_text("a b\nc") == (2, 3, 5)


def test_TEST_005_korean_characters():
    assert count_text("안녕 세상\n") == (1, 2, 6)


def test_TEST_006_non_str_raises_type_error():
    with pytest.raises(TypeError):
        count_text(None)
    with pytest.raises(TypeError):
        count_text(b"abc")

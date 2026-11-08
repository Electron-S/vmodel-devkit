import pytest

from textstats.tokenizer import tokenize
from textstats.wordfreq import count_words, top_n


def test_TEST_001_tokenize_lowercases():
    assert tokenize("Hello, 세계 hello") == ["hello", "세계", "hello"]


def test_TEST_002_tokenize_empty():
    assert tokenize("") == []


def test_TEST_003_tokenize_rejects_non_str():
    with pytest.raises(TypeError):
        tokenize(None)


def test_TEST_004_count_words():
    assert count_words("a b A") == {"a": 2, "b": 1}


def test_TEST_005_count_words_empty():
    assert count_words("") == {}


def test_TEST_006_count_words_rejects_non_str():
    with pytest.raises(TypeError):
        count_words(42)


def test_TEST_007_top_n_order():
    assert top_n("b a b c a b", 2) == [("b", 3), ("a", 2)]


def test_TEST_008_top_n_more_than_distinct():
    assert top_n("x y", 5) == [("x", 1), ("y", 1)]


def test_TEST_009_top_n_rejects_non_positive():
    with pytest.raises(ValueError):
        top_n("x", 0)


def test_TEST_010_integration_punctuation():
    assert count_words("Hi! hi? HI.") == {"hi": 3}

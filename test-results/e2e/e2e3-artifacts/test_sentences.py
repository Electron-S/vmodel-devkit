import pytest

from textstats.sentences import sentence_stats


def test_TEST_001_normal_sentences_english_and_korean():
    for text, expected in [
        ("Hello world. How are you?", (2, 2.5)),
        ("One two three!", (1, 3.0)),
        ("안녕 하세요. 반갑 습니다 정말!", (2, 2.5)),
    ]:
        result = sentence_stats(text)
        assert result == expected
        assert isinstance(result[0], int)
        assert isinstance(result[1], float)


def test_TEST_002_non_str_input_raises_type_error():
    for value in (None, 123, b"a.", ["a."]):
        with pytest.raises(TypeError):
            sentence_stats(value)


def test_TEST_003_empty_whitespace_and_punctuation_only():
    for text in ("", "   \t\n ", "...", "?!"):
        result = sentence_stats(text)
        assert result == (0, 0.0)
        assert isinstance(result[1], float)


def test_TEST_004_terminators_tail_and_mid_sentence_period():
    assert sentence_stats("Wow!! Really?! Yes.") == (3, 1.0)
    assert sentence_stats("Hi there. unfinished words") == (1, 2.0)
    assert sentence_stats("hello world") == (0, 0.0)
    assert sentence_stats("Pi is 3.14 ok.") == (2, 2.5)

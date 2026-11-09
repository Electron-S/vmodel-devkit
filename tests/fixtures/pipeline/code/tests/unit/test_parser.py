import pytest

from pipeline.parser import parse


def test_TEST_001_parse_records():
    assert parse("kim,90\nlee,85\n") == [{"name": "kim", "score": 90}, {"name": "lee", "score": 85}]


def test_TEST_002_parse_rejects_malformed_line():
    with pytest.raises(ValueError):
        parse("kim;90")


def test_TEST_003_parse_empty_text():
    assert parse("") == []

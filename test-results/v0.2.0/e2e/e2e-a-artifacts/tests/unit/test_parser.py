import pytest

from scorepipe.parser import parse_scores


def test_header_and_blank_lines_are_skipped():
    assert parse_scores("name,score\n\nkim,90\n") == [{"name": "kim", "score": "90"}]


def test_zero_padding_is_kept():
    assert parse_scores("lee,07") == [{"name": "lee", "score": "07"}]


def test_malformed_line_reports_its_number():
    with pytest.raises(ValueError, match="line 3"):
        parse_scores("name,score\nkim,90\nlee\n")

import pytest

from scorepipe.report import summarize


def make_fake(records, calls=None):
    def fake(text):
        if calls is not None:
            calls.append(text)
        return records
    return fake


def rec(*pairs):
    return [{"name": n, "score": s} for n, s in pairs]


def test_TEST_001_basic_summary_with_fake_parser():
    calls = []
    fake = make_fake(rec(("kim", "90"), ("lee", "85")), calls)
    result = summarize("TXT", parser=fake)
    assert result == {"count": 2, "total": 175, "average": 87.5, "top": "kim"}
    assert list(result) == ["count", "total", "average", "top"]
    assert isinstance(result["average"], float)
    assert calls == ["TXT"]


def test_TEST_002_parser_value_error_propagates():
    def fake(text):
        raise ValueError("line 3: bad row")

    with pytest.raises(ValueError) as exc:
        summarize("x", parser=fake)
    assert str(exc.value) == "line 3: bad row"


def test_TEST_003_default_parser_rejects_non_str():
    with pytest.raises(TypeError):
        summarize(None)


def test_TEST_004_empty_records():
    result = summarize("", parser=make_fake([]))
    assert result == {"count": 0, "total": 0, "average": 0.0, "top": None}
    assert isinstance(result["average"], float)


def test_TEST_005_zero_padded_scores_are_ints():
    result = summarize("x", parser=make_fake(rec(("a", "07"), ("b", "100"), ("c", "0"))))
    assert result["total"] == 107 and isinstance(result["total"], int)
    assert result["count"] == 3
    assert result["average"] == 35.7


def test_TEST_006_half_up_average():
    assert summarize("x", parser=make_fake(rec(("a", "2"), ("b", "2"), ("c", "2"), ("d", "3"))))["average"] == 2.3
    assert summarize("x", parser=make_fake(rec(("a", "1"), ("b", "0"), ("c", "0"))))["average"] == 0.3


def test_TEST_007_ties_pick_first():
    assert summarize("x", parser=make_fake(rec(("a", "5"), ("b", "9"), ("c", "9"))))["top"] == "b"
    assert summarize("x", parser=make_fake(rec(("x", "4"), ("y", "4"), ("z", "4"))))["top"] == "x"


def test_TEST_008_single_person():
    result = summarize("x", parser=make_fake(rec(("solo", "7"))))
    assert result == {"count": 1, "total": 7, "average": 7.0, "top": "solo"}
    assert isinstance(result["average"], float)

import pytest

from gradecalc.grading import grade


def test_TEST_001_grade_letters():
    assert [grade(s) for s in (95, 85, 75, 50)] == ["A", "B", "C", "F"]


def test_TEST_002_grade_rejects_bad_scores():
    for bad in (101, -1):
        with pytest.raises(ValueError):
            grade(bad)
    for bad in ("9", True, 9.5):
        with pytest.raises(TypeError):
            grade(bad)


def test_TEST_003_grade_boundaries():
    assert [grade(s) for s in (90, 89, 80, 79, 70, 69, 0, 100)] == ["A", "B", "B", "C", "C", "F", "F", "A"]

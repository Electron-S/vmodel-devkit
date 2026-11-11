from gradecalc.server import handle


def test_TEST_007_handle_grade():
    assert handle("/grade?score=95") == (200, {"score": 95, "grade": "A"})


def test_TEST_008_handle_bad_request():
    assert handle("/grade?score=abc")[0] == 400
    assert handle("/grade")[0] == 400
    assert handle("/other")[0] == 404


def test_TEST_009_handle_boundaries():
    assert handle("/grade?score=0") == (200, {"score": 0, "grade": "F"})
    assert handle("/grade?score=100") == (200, {"score": 100, "grade": "A"})
    assert handle("/grade?score=101")[0] == 400

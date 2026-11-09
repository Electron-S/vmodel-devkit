import json

from pipeline.report import main, summarize


def test_TEST_004_summarize_records():
    assert summarize("a,1\nb,3\n") == {"count": 2, "total": 4, "top": "b"}


def test_TEST_005_summarize_empty():
    assert summarize("") == {"count": 0, "total": 0, "top": None}


def test_TEST_006_main_prints_summary(tmp_path, capsys):
    f = tmp_path / "scores.csv"
    f.write_text("a,1\nb,2\n", encoding="utf-8")
    assert main([str(f)]) == 0
    assert json.loads(capsys.readouterr().out)["count"] == 2


def test_TEST_007_main_empty_file(tmp_path, capsys):
    f = tmp_path / "empty.csv"
    f.write_text("", encoding="utf-8")
    assert main([str(f)]) == 0
    assert json.loads(capsys.readouterr().out)["count"] == 0

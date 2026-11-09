import json

import pytest

from pipeline.report import main, summarize


def test_TEST_010_report_uses_real_parser():
    assert summarize("kim,90\nlee,95\npark,70\n") == {"count": 3, "total": 255, "top": "lee"}


def test_TEST_011_parser_error_reaches_report():
    with pytest.raises(ValueError):
        summarize("kim,ninety")


def test_TEST_012_cli_main_reads_file(tmp_path, capsys):
    f = tmp_path / "scores.csv"
    f.write_text("a,1\nb,2\n", encoding="utf-8")
    assert main([str(f)]) == 0
    assert json.loads(capsys.readouterr().out) == {"count": 2, "total": 3, "top": "b"}

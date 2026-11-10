import json

from scorepipe.report import main


def write(tmp_path, content: bytes, name="in.csv"):
    p = tmp_path / name
    p.write_bytes(content)
    return str(p)


def test_TEST_009_main_success(tmp_path, capsys):
    path = write(tmp_path, "name,score\nkim,90\nlee,85\n".encode("utf-8"))
    assert main([path]) == 0
    out = capsys.readouterr()
    assert out.out.count("\n") == 1 and out.out.endswith("\n")
    data = json.loads(out.out)
    assert data == {"count": 2, "total": 175, "average": 87.5, "top": "kim"}
    assert list(data) == ["count", "total", "average", "top"]
    assert out.err == ""


def test_TEST_010_wrong_argument_count(capsys):
    for argv in ([], ["a.csv", "b.csv"]):
        assert main(argv) == 2
        out = capsys.readouterr()
        assert out.out == ""
        assert "usage: python -m scorepipe.report <file>" in out.err


def test_TEST_011_missing_file(tmp_path, capsys):
    path = str(tmp_path / "nope.csv")
    assert main([path]) == 2
    out = capsys.readouterr()
    assert out.out == ""
    assert out.err.startswith("error: cannot read ") and path in out.err


def test_TEST_012_bom_file(tmp_path, capsys):
    path = write(tmp_path, "﻿name,score\nkim,90\n".encode("utf-8"))
    assert main([path]) == 0
    assert json.loads(capsys.readouterr().out) == {"count": 1, "total": 90, "average": 90.0, "top": "kim"}


def test_TEST_013_korean_name_ascii_output(tmp_path, capsys):
    path = write(tmp_path, "name,score\n김철수,90\n".encode("utf-8"))
    assert main([path]) == 0
    out = capsys.readouterr().out
    assert out.isascii()
    assert "\\uae40" in out
    assert json.loads(out)["top"] == "김철수"


def test_TEST_014_empty_file(tmp_path, capsys):
    path = write(tmp_path, b"")
    assert main([path]) == 0
    out = capsys.readouterr()
    assert json.loads(out.out) == {"count": 0, "total": 0, "average": 0.0, "top": None}
    assert out.err == ""


def test_TEST_015_format_error_and_non_utf8(tmp_path, capsys):
    path = write(tmp_path, b"name,score\nkim,90\nlee\n", "a.csv")
    assert main([path]) == 2
    out = capsys.readouterr()
    assert out.out == "" and out.err.startswith("error: ") and "line 3" in out.err
    path = write(tmp_path, b"\xff\xfe\x80\x81", "b.csv")
    assert main([path]) == 2
    out = capsys.readouterr()
    assert out.out == "" and out.err.startswith("error: cannot read ")

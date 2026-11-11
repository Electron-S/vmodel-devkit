import pytest

from textcli.__main__ import main


def _write(tmp_path, data: bytes):
    f = tmp_path / "f.txt"
    f.write_bytes(data)
    return str(f)


def test_TEST_007_main_counts_existing_file(tmp_path, capsys):
    f = _write(tmp_path, b"hello world\nfoo\n")
    assert main(["count", f]) == 0
    out = capsys.readouterr()
    assert out.out == "2 3 16\n"
    assert out.err == ""


def test_TEST_008_main_empty_file(tmp_path, capsys):
    f = _write(tmp_path, b"")
    assert main(["count", f]) == 0
    assert capsys.readouterr().out == "0 0 0\n"


def test_TEST_009_main_no_trailing_newline(tmp_path, capsys):
    f = _write(tmp_path, b"a b\nc")
    assert main(["count", f]) == 0
    assert capsys.readouterr().out == "2 3 5\n"


def test_TEST_010_main_missing_korean_path(tmp_path, capsys):
    p = str(tmp_path / "없는파일.txt")
    assert main(["count", p]) == 2
    out = capsys.readouterr()
    assert out.out == ""
    assert out.err == "error: file not found: " + p + "\n"


def test_TEST_011_main_missing_file_returns_2(tmp_path, capsys):
    p = str(tmp_path / "missing.txt")
    assert main(["count", p]) == 2
    out = capsys.readouterr()
    assert out.out == ""
    assert out.err == "error: file not found: " + p + "\n"


def test_TEST_012_main_invalid_command_line_exits_2(capsys):
    with pytest.raises(SystemExit) as e1:
        main(["bogus"])
    assert e1.value.code == 2
    with pytest.raises(SystemExit) as e2:
        main(["count"])
    assert e2.value.code == 2
    assert capsys.readouterr().out == ""

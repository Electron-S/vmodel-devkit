"""System tests: drive `python -m textcli` from outside as a subprocess."""
import os
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"


def _run(*args):
    env = {**os.environ, "PYTHONPATH": str(SRC), "PYTHONIOENCODING": "utf-8"}
    return subprocess.run([sys.executable, "-m", "textcli", *args], env=env, capture_output=True,
                          text=True, encoding="utf-8", timeout=60)


def _file(tmp_path, data: bytes):
    f = tmp_path / "input.txt"
    f.write_bytes(data)
    return str(f)


def test_TEST_013_cli_counts_two_line_file(tmp_path):
    res = _run("count", _file(tmp_path, b"hello world\nfoo\n"))
    assert (res.returncode, res.stdout, res.stderr) == (0, "2 3 16\n", "")


def test_TEST_014_cli_no_trailing_newline(tmp_path):
    res = _run("count", _file(tmp_path, b"a b\nc"))
    assert (res.returncode, res.stdout) == (0, "2 3 5\n")


def test_TEST_015_cli_korean_file(tmp_path):
    res = _run("count", _file(tmp_path, "안녕 세상\n".encode("utf-8")))
    assert (res.returncode, res.stdout) == (0, "1 2 6\n")


def test_TEST_016_cli_only_newline(tmp_path):
    res = _run("count", _file(tmp_path, b"\n"))
    assert (res.returncode, res.stdout) == (0, "1 0 1\n")


def test_TEST_017_cli_empty_file(tmp_path):
    res = _run("count", _file(tmp_path, b""))
    assert (res.returncode, res.stdout) == (0, "0 0 0\n")


def test_TEST_018_cli_missing_file(tmp_path):
    p = str(tmp_path / "does-not-exist.txt")
    res = _run("count", p)
    assert res.returncode == 2
    assert res.stdout == ""
    assert res.stderr.strip() == "error: file not found: " + p

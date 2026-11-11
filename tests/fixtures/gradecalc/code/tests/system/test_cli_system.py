"""System tests through the command line interface (black box: a separate Python process)."""
import os
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"


def run_cli(*args: str) -> tuple[int, str, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC)
    env["PYTHONIOENCODING"] = "utf-8"
    res = subprocess.run([sys.executable, "-m", "gradecalc.cli", *args], capture_output=True, env=env, timeout=60)
    return res.returncode, res.stdout.decode("utf-8"), res.stderr.decode("utf-8")


def test_TEST_101_cli_prints_grade():
    code, out, err = run_cli("95")
    assert (code, out.strip(), err) == (0, "95 A", "")


def test_TEST_102_cli_boundary_scores():
    seen = {}
    for score in ("90", "89", "0", "100"):
        code, out, _err = run_cli(score)
        assert code == 0, (score, code)
        seen[score] = out.split()[-1]
    assert seen == {"90": "A", "89": "B", "0": "F", "100": "A"}


def test_TEST_103_cli_rejects_invalid_scores():
    for bad in ("abc", "101", "-1"):
        code, out, err = run_cli(bad)
        assert code == 2, (bad, code)
        assert out == ""
        assert "오류" in err


def test_TEST_106_cli_error_message_is_korean():
    code, _out, err = run_cli("101")
    assert code == 2
    assert "점수는 0에서 100 사이의 정수여야 합니다" in err

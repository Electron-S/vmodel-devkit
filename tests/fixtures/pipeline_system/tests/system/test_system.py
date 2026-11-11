"""System tests of the pipeline CLI (black box: python -m pipeline.report in a separate process)."""
import json
import os
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"


def run_report(path: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC)
    return subprocess.run([sys.executable, "-m", "pipeline.report", str(path)], capture_output=True, env=env,
                          timeout=60)


def test_TEST_020_cli_parses_records(tmp_path):
    good = tmp_path / "good.csv"
    good.write_text("kim,90\nlee,80\n", encoding="utf-8")
    res = run_report(good)
    assert res.returncode == 0
    assert json.loads(res.stdout)["count"] == 2
    bad = tmp_path / "bad.csv"
    bad.write_text("kim;90\n", encoding="utf-8")
    res = run_report(bad)
    assert res.returncode != 0
    assert b"ValueError" in res.stderr


def test_TEST_021_cli_prints_summary(tmp_path):
    f = tmp_path / "scores.csv"
    f.write_text("a,1\nb,2\n", encoding="utf-8")
    res = run_report(f)
    assert res.returncode == 0
    assert json.loads(res.stdout) == {"count": 2, "total": 3, "top": "b"}

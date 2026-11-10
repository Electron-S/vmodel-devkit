import json
import os
import subprocess
import sys
from pathlib import Path

from scorepipe import report


def test_TEST_016_main_uses_real_summarize_and_parser(tmp_path, capsys):
    f = tmp_path / "export.csv"
    f.write_text("name,score\nkim,90\nlee,85\n", encoding="utf-8")
    expected = {"count": 2, "total": 175, "average": 87.5, "top": "kim"}
    assert report.main([str(f)]) == 0
    assert json.loads(capsys.readouterr().out) == expected
    src = str(Path(report.__file__).resolve().parents[1])
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [src, env.get("PYTHONPATH")]))
    proc = subprocess.run([sys.executable, "-m", "scorepipe.report", str(f)],
                          capture_output=True, text=True, encoding="utf-8", env=env)
    assert proc.returncode == 0
    assert len(proc.stdout.splitlines()) == 1
    assert json.loads(proc.stdout) == expected


def test_TEST_017_real_parser_error_becomes_exit_2(tmp_path, capsys):
    f = tmp_path / "bad.csv"
    f.write_text("name,score\nkim,90\nlee\n", encoding="utf-8")
    assert report.main([str(f)]) == 2
    out = capsys.readouterr()
    assert out.out == ""
    assert out.err.startswith("error: ") and "line 3" in out.err

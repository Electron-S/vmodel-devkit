"""Package-level system smoke test: the package starts in a fresh interpreter (black box, subprocess)."""
import os
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"


def test_package_starts_in_a_fresh_interpreter():
    env = {**os.environ, "PYTHONPATH": str(SRC), "PYTHONIOENCODING": "utf-8"}
    res = subprocess.run([sys.executable, "-c", "import textcli; print(textcli.__doc__)"], env=env,
                         capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert res.returncode == 0, res.stderr
    assert "textcli" in res.stdout

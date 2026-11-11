"""System tests through the HTTP API (black box: the server runs as a separate process)."""
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src"


@pytest.fixture
def server_url():
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC)
    proc = subprocess.Popen([sys.executable, "-m", "gradecalc.server", "--port", "0"], stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, env=env)
    try:
        line = proc.stdout.readline().decode("ascii", "replace").split()
        assert line and line[0] == "PORT", line
        yield f"http://127.0.0.1:{line[1]}"
    finally:
        proc.terminate()
        proc.wait(timeout=30)
        proc.stdout.close()
        proc.stderr.close()


def get(url: str) -> tuple[int, dict]:
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = json.loads(exc.read().decode("utf-8"))
        exc.close()
        return exc.code, body


def test_TEST_104_api_returns_grade(server_url):
    assert get(f"{server_url}/grade?score=85") == (200, {"score": 85, "grade": "B"})


def test_TEST_105_api_rejects_invalid_score(server_url):
    status, body = get(f"{server_url}/grade?score=abc")
    assert status == 400
    assert "error" in body

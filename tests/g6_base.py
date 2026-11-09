"""Shared bases for the 0.2.0 G6 tests (docs/g6/WORKITEM.md section 5).

Each test class builds one sandbox in setUpClass (G1-G5 or less PASSED, at fixed absolute paths) and restores a byte
copy of it before every test, so a test starts from the same signed ledger without re-running G1-G5.
Red-class assertions that must fail on the immutable 0.1.5 release carry the marker RED-TARGET in their message;
helper assertions do not, so scripts/red_green.py --marker can tell a clean RED from a broken setup.
"""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from helpers import GATES, PIPELINE, Sandbox, has_pytest

RED = "RED-TARGET"
SUBPROCESS_TEST_012 = '''

def test_TEST_012_cli_subprocess(tmp_path):
    import os
    import subprocess
    import sys
    from pathlib import Path

    f = tmp_path / "scores.csv"
    f.write_text("a,1\\nb,2\\n", encoding="utf-8")
    env = dict(os.environ)
    src = str(Path(__file__).resolve().parents[2] / "src")
    env["PYTHONPATH"] = os.pathsep.join(p for p in (src, env.get("PYTHONPATH")) if p)
    res = subprocess.run([sys.executable, "-m", "pipeline.report", str(f)], capture_output=True, env=env, check=True)
    assert json.loads(res.stdout) == {"count": 2, "total": 3, "top": "b"}
'''
API_TEST_012 = '''

def test_TEST_012_report_over_http():
    import threading
    import urllib.request
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    from pipeline import report

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"])).decode("utf-8")
            out = json.dumps(report.summarize(body)).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Length", str(len(out)))
            self.end_headers()
            self.wfile.write(out)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{server.server_address[1]}/"
        with urllib.request.urlopen(url, data=b"a,1\\nb,2\\n", timeout=30) as resp:
            assert json.loads(resp.read()) == {"count": 2, "total": 3, "top": "b"}
    finally:
        server.shutdown()
'''


def check(tc: unittest.TestCase, res: dict, cid: str) -> dict:
    found = [c for c in res.get("checks") or [] if c["id"] == cid]
    # a check id missing from a gate result is the new-behaviour signal on 0.1.5 (new checks), hence the marker
    tc.assertTrue(found, f"{RED} (check missing) {cid} not in {json.dumps(res, indent=1, ensure_ascii=False)[:3000]}")
    return found[0]


def ledger_records(sb: Sandbox) -> list[dict]:
    lines = (sb.root / ".vmodel/state/ledger.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(ln)["record"] for ln in lines]


def ledger_record(sb: Sandbox, rid: str) -> dict:
    return [r for r in ledger_records(sb) if r.get("record_id") == rid][0]


def evidence_record(sb: Sandbox, res: dict) -> dict:
    return json.loads((sb.root / res["evidence"][0]["path"]).read_text(encoding="utf-8"))


def wi_status(sb: Sandbox) -> dict:
    return [w for w in sb.status()["work_items"] if w["id"] == sb.wi][0]


def gate_view(sb: Sandbox, gate: str) -> dict:
    return [g for g in wi_status(sb)["gates"] if g["gate"] == gate][0]


def replace_function(path: Path, name: str, new_source: str | None) -> None:
    """Replace (or with None remove) a top-level test function in a fixture test file."""
    text = path.read_text(encoding="utf-8")
    pat = re.compile(rf"\n\ndef {re.escape(name)}\(.*?(?=\n\n\ndef |\Z)", re.S)
    assert pat.search(text), f"{name} not in {path}"
    repl = "" if new_source is None else "\n\n" + new_source.strip("\n") + "\n"
    text = pat.sub(lambda _m: repl, text, count=1)  # a function: re.sub must not interpret backslashes in the source
    path.write_text(text.rstrip("\n") + "\n", encoding="utf-8")


def file_sha256(path: Path) -> str:
    import hashlib
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def applicability(endpoints: list[str], reason: str = "single component; no interface to integrate") -> dict:
    return {"integration_applicability": {"decision": "not_required", "reason": reason,
                                          "endpoints_reviewed": endpoints}}


SINGLE_ENDPOINTS = ["사용자 입력", "결과 출력"]


@unittest.skipUnless(has_pytest(), "pytest not installed")
class SandboxClass(unittest.TestCase):
    """One sandbox per class, restored before each test."""
    fixture: Path = PIPELINE
    split = True  # user configured separate unit / integration commands
    upto: str | None = "G5"
    na_reviews = False  # G2/G3 reviews confirm "integration not required" (N/A path)

    @classmethod
    def setUpClass(cls):
        cls.sb = Sandbox(fixture=cls.fixture)
        try:
            cls.build(cls.sb)
            cls.sb.snapshot()
        except BaseException:
            cls.sb.cleanup()
            raise

    @classmethod
    def build(cls, sb: Sandbox) -> None:
        sb.init()
        assert sb.new_wi("G6 기능", "통합 검증 대상 기능을 개발해줘") == "WI-001"
        if cls.split:
            sb.split_tests()
        if cls.upto:
            advance(sb, cls.upto, na=cls.na_reviews)

    @classmethod
    def tearDownClass(cls):
        cls.sb.cleanup()

    def setUp(self):
        self.sb.restore()

    # ------------------------------------------------------------ shortcuts
    def check(self, res: dict, cid: str) -> dict:
        return check(self, res, cid)

    def regate(self, *gates: str, expect: str = "PASSED") -> dict:
        """Re-review (G1-G4) and re-run the given gates; each must reach `expect` (helper, not a RED target)."""
        res: dict = {}
        for g in gates:
            if g in ("G1", "G2", "G3", "G4"):
                extra = applicability(SINGLE_ENDPOINTS) if (self.na_reviews and g in ("G2", "G3")) else None
                self.sb.review(g, extra=extra)
            res = self.sb.gate(g)[1]
            assert res["status"] == expect, json.dumps(res, indent=1, ensure_ascii=False)[:4000]
        return res

    def g6(self) -> dict:
        return self.sb.gate("G6")[1]


def advance(sb: Sandbox, upto: str, na: bool = False) -> None:
    for g in GATES[: GATES.index(upto) + 1]:
        sb.prepare(g)
        if g != "G5":
            sb.review(g, extra=applicability(SINGLE_ENDPOINTS) if (na and g in ("G2", "G3")) else None)
        res = sb.gate(g)[1]
        assert res["status"] == "PASSED", json.dumps(res, indent=2, ensure_ascii=False)[:4000]

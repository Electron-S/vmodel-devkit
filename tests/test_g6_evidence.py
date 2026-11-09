"""G6 evidence attribution, cases A-F of the final verification request (2026-11-09, decision D44).

Each integration test of an interface gets an evidence level, and only test-level evidence covers the interface:
- test_level ("Test-level Verified"): the test's own function ran and passed, it has a static call path (path A) or a
  declared runtime path (path B), and in that test's own execution the connection was observed: for an IF with an
  architecture consumer, a provider function ran with a consumer function on its call stack (path A; also across a
  thread or pool work item started by the consumer) or the provider ran in another process / server thread during the
  test call while the consumer ran in it (path B); for an EXTERNAL consumer, a provider function ran in the test.
- suite_level ("Suite-level Evidence Only"): the provider ran somewhere in the run, but not attributably to this test.
- insufficient ("Insufficient Evidence"): no trace, the provider never ran, or the connection was not observed.
An interface without a test-level test is not covered: BLOCKED (integration_evidence_insufficient) unless a test has
no call path at all (FAILED). RED target: git archive 14b34af plugins/vmodel (the D43 rule: run-wide provider
execution plus an advisory per-test warning), on which these assertions fail at RED-TARGET.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from g6_base import (RED, SUBPROCESS_TEST_012, SandboxClass, file_sha256, justify_test_change, ledger_record,
                     replace_function)
from helpers import PLUGIN

INTEGRATION = "tests/integration/test_pipeline.py"
MOCKED = {
    "test_TEST_010_report_uses_real_parser":
        "def test_TEST_010_report_uses_real_parser(monkeypatch):\n"
        "    monkeypatch.setattr('pipeline.report.parse', lambda text: [{'name': 'x', 'score': 1}])\n"
        "    assert summarize('ignored')['top'] == 'x'\n",
    "test_TEST_011_parser_error_reaches_report":
        "def test_TEST_011_parser_error_reaches_report(monkeypatch):\n"
        "    def boom(text):\n        raise ValueError('x')\n"
        "    monkeypatch.setattr('pipeline.report.parse', boom)\n"
        "    with pytest.raises(ValueError):\n        summarize('kim,ninety')\n",
}
# Case D: the test itself runs the real provider, and the consumer runs too, but the consumer's call into the provider
# is replaced: both functions executed in the test, no connection between them.
UNCONNECTED = {
    "test_TEST_010_report_uses_real_parser":
        "def test_TEST_010_report_uses_real_parser(monkeypatch):\n"
        "    from pipeline.parser import parse as real_parse\n"
        "    rows = real_parse('kim,90\\nlee,95\\n')\n"
        "    monkeypatch.setattr('pipeline.report.parse', lambda text: rows)\n"
        "    assert summarize('ignored')['top'] == 'lee'\n",
    "test_TEST_011_parser_error_reaches_report":
        "def test_TEST_011_parser_error_reaches_report(monkeypatch):\n"
        "    from pipeline.parser import parse as real_parse\n"
        "    with pytest.raises(ValueError):\n        real_parse('kim,ninety')\n"
        "    def boom(text):\n        raise ValueError('line 1: score must be an integer')\n"
        "    monkeypatch.setattr('pipeline.report.parse', boom)\n"
        "    with pytest.raises(ValueError):\n        summarize('kim,ninety')\n",
}
FIXTURE_SERVER_012 = (
    "@pytest.fixture\ndef server():\n"
    "    import threading\n    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer\n"
    "    from pipeline import report\n\n"
    "    class Handler(BaseHTTPRequestHandler):\n"
    "        def do_POST(self):\n"
    "            body = self.rfile.read(int(self.headers['Content-Length'])).decode('utf-8')\n"
    "            out = json.dumps(report.summarize(body)).encode('utf-8')\n"
    "            self.send_response(200)\n            self.send_header('Content-Length', str(len(out)))\n"
    "            self.end_headers()\n            self.wfile.write(out)\n\n"
    "        def log_message(self, *args):\n            pass\n\n"
    "    srv = ThreadingHTTPServer(('127.0.0.1', 0), Handler)\n"
    "    threading.Thread(target=srv.serve_forever, daemon=True).start()\n"
    "    yield srv\n    srv.shutdown()\n\n\n"
    "def test_TEST_012_cli_main_reads_file(server):\n"
    "    import urllib.request\n"
    "    url = f'http://127.0.0.1:{server.server_address[1]}/'\n"
    "    with urllib.request.urlopen(url, data=b'a,1\\nb,2\\n', timeout=30) as resp:\n"
    "        assert json.loads(resp.read()) == {'count': 2, 'total': 3, 'top': 'b'}\n")
UNTRACED_SUBPROCESS_012 = (
    "def test_TEST_012_cli_isolated_subprocess(tmp_path):\n"
    "    import subprocess\n    import sys\n    from pathlib import Path\n"
    "    f = tmp_path / 'scores.csv'\n    f.write_text('a,1\\nb,2\\n', encoding='utf-8')\n"
    "    src = str(Path(__file__).resolve().parents[2] / 'src')\n"
    "    code = ('import sys; sys.path.insert(0, sys.argv[1]); from pipeline.report import main; '\n"
    "            'raise SystemExit(main([sys.argv[2]]))')\n"
    "    res = subprocess.run([sys.executable, '-I', '-c', code, src, str(f)], capture_output=True, check=True)\n"
    "    assert json.loads(res.stdout) == {'count': 2, 'total': 3, 'top': 'b'}\n")


def levels(rec: dict) -> dict:
    """IF -> (verification, {TEST: evidence_level}, covered_by) from a G6 ledger record (None where absent)."""
    out = {}
    for i in rec.get("interfaces") or []:
        tests = {t: (v or {}).get("evidence_level") for t, v in (i.get("tests") or {}).items()}
        out[i.get("id")] = (i.get("verification"), tests, i.get("covered_by"))
    return out


class EvidenceBase(SandboxClass):
    """pipeline (IF-001 parse: ARCH-001 -> ARCH-002, IF-002 report CLI: ARCH-002 -> EXTERNAL), split commands,
    G1-G5 PASSED."""

    @property
    def itest(self):
        return self.sb.root / INTEGRATION

    def replace(self, sources: dict) -> None:
        for name, src in sources.items():
            replace_function(self.itest, name, src)

    def to_g6(self, interfaces: list | None = None) -> tuple[dict, dict, dict]:
        """Re-review G4 (test file changed), re-run G4/G5 (helper: both must pass), then G6 (the judged result)."""
        justify_test_change(self.sb, INTEGRATION)
        self.sb.review("G4", interfaces=interfaces)
        r4 = self.sb.gate("G4")[1]
        assert r4["status"] == "PASSED", json.dumps(r4, indent=1, ensure_ascii=False)[:3000]
        r5 = self.sb.gate("G5")[1]
        assert r5["status"] == "PASSED", json.dumps(r5, indent=1, ensure_ascii=False)[:3000]
        return r4, r5, self.g6()

    def declare_012(self, kind: str) -> list[dict]:
        entries = self.sb.interface_review_entries()
        for e in entries:
            if e["id"] == "IF-002":
                e["runtime_paths"] = [{"test": "TEST-012", "kind": kind, "test_file_sha256": file_sha256(self.itest)}]
        return entries

    def coverage(self, res: dict) -> dict:
        return [c for c in res["checks"] if c["id"] == "G6.IF_COVERAGE"][0]

    def gate_text(self) -> str:
        code, out = self.sb.vm("gate", "WI-001", "G6")
        return out


class EvidenceCaseRed(EvidenceBase):
    # Case A ------------------------------------------------------------------------------------------------------
    def test_case_A_real_connection_is_test_level_verified(self):
        res = self.g6()
        self.assertEqual(res["status"], "PASSED", res)
        lv = levels(ledger_record(self.sb, res["record_id"]))
        self.assertEqual(lv.get("IF-001"), ("test_level", {"TEST-010": "test_level", "TEST-011": "test_level"},
                                            ["TEST-010", "TEST-011"]), f"{RED} {lv}")
        self.assertEqual(lv.get("IF-002"), ("test_level", {"TEST-012": "test_level"}, ["TEST-012"]), f"{RED} {lv}")
        self.assertIn("2/2 interface(s) test-level verified", self.coverage(res)["detail"], f"{RED} {res}")
        st = self.sb.vm("status")[1]
        self.assertIn("IF 2/2 test-level verified", st, f"{RED} {st}")

    # Case B ------------------------------------------------------------------------------------------------------
    def test_case_B_mock_only_tests_do_not_verify_the_interface(self):
        """Both IF-001 tests mock the parser; the parser runs only in TEST-012 (main -> summarize -> parse, IF-002)."""
        self.replace(MOCKED)
        _r4, _r5, r6 = self.to_g6()
        self.assertEqual((r6["status"], r6.get("blocked_reason")), ("BLOCKED", "integration_evidence_insufficient"),
                         f"{RED} mocked tests alone must not verify IF-001: {r6}")
        lv = levels(ledger_record(self.sb, r6["record_id"]))
        self.assertEqual(lv["IF-001"][0], "suite_level", f"{RED} {lv}")
        self.assertEqual(lv["IF-001"][1], {"TEST-010": "suite_level", "TEST-011": "suite_level"}, f"{RED} {lv}")
        self.assertEqual(lv["IF-001"][2], [], f"{RED} {lv}")
        self.assertEqual(lv["IF-002"][0], "test_level", f"{RED} {lv}")
        text = self.gate_text()
        self.assertIn("Suite-level Evidence Only", text, f"{RED} {text}")
        self.assertNotIn("2/2 interface(s)", text, f"{RED} {text}")

    # Case C ------------------------------------------------------------------------------------------------------
    def test_case_C_another_tests_provider_run_is_not_attributed(self):
        """TEST-010 mocks the parser, TEST-011 runs the real one: IF-001 is verified by TEST-011 only."""
        self.replace({k: v for k, v in MOCKED.items() if "TEST_010" in k})
        _r4, _r5, r6 = self.to_g6()
        self.assertEqual(r6["status"], "PASSED", r6)
        lv = levels(ledger_record(self.sb, r6["record_id"]))
        self.assertEqual(lv["IF-001"][2], ["TEST-011"], f"{RED} TEST-010 must not be counted: {lv}")
        self.assertEqual(lv["IF-001"][1].get("TEST-010"), "suite_level", f"{RED} {lv}")
        self.assertEqual(lv["IF-001"][1].get("TEST-011"), "test_level", f"{RED} {lv}")
        cov = self.coverage(r6)
        self.assertTrue(any("TEST-010" in i and "Suite-level Evidence Only" in i and "not counted" in i
                            for i in cov["items"]), f"{RED} {cov}")

    # Case D ------------------------------------------------------------------------------------------------------
    def test_case_D_provider_and_consumer_running_unconnected_is_not_a_connection(self):
        self.replace(UNCONNECTED)
        _r4, _r5, r6 = self.to_g6()
        self.assertEqual((r6["status"], r6.get("blocked_reason")), ("BLOCKED", "integration_evidence_insufficient"),
                         f"{RED} the parser was never called by the report in TEST-010/011: {r6}")
        lv = levels(ledger_record(self.sb, r6["record_id"]))
        self.assertEqual(lv["IF-001"], ("insufficient", {"TEST-010": "insufficient", "TEST-011": "insufficient"}, []),
                         f"{RED} {lv}")
        cov = self.coverage(r6)
        self.assertTrue(any("TEST-010" in i and "not called from the consumer" in i for i in cov["items"]),
                        f"{RED} {cov}")

    # Case E ------------------------------------------------------------------------------------------------------
    def test_case_E_subprocess_runtime_path(self):
        replace_function(self.itest, "test_TEST_012_cli_main_reads_file", SUBPROCESS_TEST_012)
        _r4, _r5, r6 = self.to_g6(self.declare_012("subprocess"))
        self.assertEqual(r6["status"], "PASSED", r6)
        lv = levels(ledger_record(self.sb, r6["record_id"]))
        self.assertEqual(lv["IF-002"], ("test_level", {"TEST-012": "test_level"}, ["TEST-012"]), f"{RED} {lv}")

    def test_case_E_api_server_in_a_function_fixture(self):
        replace_function(self.itest, "test_TEST_012_cli_main_reads_file", FIXTURE_SERVER_012)
        _r4, _r5, r6 = self.to_g6(self.declare_012("api"))
        self.assertEqual(r6["status"], "PASSED", r6)
        lv = levels(ledger_record(self.sb, r6["record_id"]))
        self.assertEqual(lv["IF-002"], ("test_level", {"TEST-012": "test_level"}, ["TEST-012"]), f"{RED} {lv}")

    def test_case_E_consumer_using_a_shared_thread_pool(self):
        """The report runs parse in a module-level pool whose worker the first test (TEST-012) created: the work items
        submitted by TEST-010/011 are theirs (submission context), with the report on the submitting stack."""
        rp = self.sb.root / "src/pipeline/report.py"
        rp.write_text(rp.read_text(encoding="utf-8").replace(
            "from pipeline.parser import parse\n",
            "from concurrent.futures import ThreadPoolExecutor\n\nfrom pipeline.parser import parse\n\n"
            "_POOL = ThreadPoolExecutor(max_workers=1)\n").replace(
            "    records = parse(text)\n", "    records = _POOL.submit(parse, text).result()\n"), encoding="utf-8")
        body = self.itest.read_text(encoding="utf-8")  # TEST-012 first: it creates the pool worker
        start = body.index("\n\ndef test_TEST_012")
        t12, body = body[start:], body[:start]
        first = body.index("\n\ndef test_TEST_010")
        self.itest.write_text(body[:first] + t12.rstrip("\n") + "\n" + body[first:], encoding="utf-8")
        _r4, _r5, r6 = self.to_g6()
        self.assertEqual(r6["status"], "PASSED", r6)
        lv = levels(ledger_record(self.sb, r6["record_id"]))
        self.assertEqual(lv["IF-001"], ("test_level", {"TEST-010": "test_level", "TEST-011": "test_level"},
                                        ["TEST-010", "TEST-011"]), f"{RED} {lv}")
        self.assertEqual(self.coverage(r6)["status"], "pass", f"{RED} {self.coverage(r6)}")

    # Case F ------------------------------------------------------------------------------------------------------
    def test_case_F_untraced_subprocess_is_insufficient_and_shown(self):
        """The child runs with -I (PYTHONPATH ignored, so no tracer): the declared subprocess path cannot be shown."""
        replace_function(self.itest, "test_TEST_012_cli_main_reads_file", UNTRACED_SUBPROCESS_012)
        _r4, _r5, r6 = self.to_g6(self.declare_012("subprocess"))
        self.assertEqual((r6["status"], r6.get("blocked_reason")), ("BLOCKED", "integration_evidence_insufficient"), r6)
        lv = levels(ledger_record(self.sb, r6["record_id"]))
        # report.py (the IF-002 provider) ran in the pytest process for TEST-010/011, never in a TEST-012 child
        self.assertEqual(lv.get("IF-002"), ("suite_level", {"TEST-012": "suite_level"}, []), f"{RED} {lv}")
        self.assertEqual(lv.get("IF-001", (None,))[0], "test_level", f"{RED} {lv}")
        text = self.gate_text()
        self.assertIn("IF-002", text, text)
        self.assertIn("Suite-level Evidence Only", text, f"{RED} {text}")
        self.assertIn("1/2 interface(s) test-level verified", text, f"{RED} {text}")

    def test_case_F_provider_that_never_runs_is_insufficient(self):
        (self.sb.root / "tests/integration/conftest.py").write_text(
            "import pytest\n\n\n@pytest.fixture(autouse=True)\ndef _no_parser(monkeypatch):\n"
            "    monkeypatch.setattr('pipeline.report.parse', lambda text: [{'name': 'b', 'score': 2}] if text else [])\n",
            encoding="utf-8")
        for name in ("test_TEST_010_report_uses_real_parser", "test_TEST_011_parser_error_reaches_report"):
            replace_function(self.itest, name, f"def {name}():\n    assert summarize('x')['count'] == 1\n")
        replace_function(self.itest, "test_TEST_012_cli_main_reads_file",  # passes with the parser replaced too
                         "def test_TEST_012_cli_main_reads_file(tmp_path, capsys):\n"
                         "    f = tmp_path / 'scores.csv'\n    f.write_text('a,1\\n', encoding='utf-8')\n"
                         "    assert main([str(f)]) == 0\n")
        _r4, _r5, r6 = self.to_g6()
        self.assertEqual((r6["status"], r6.get("blocked_reason")), ("BLOCKED", "integration_evidence_insufficient"), r6)
        lv = levels(ledger_record(self.sb, r6["record_id"]))
        self.assertEqual(lv.get("IF-001"), ("insufficient", {"TEST-010": "insufficient", "TEST-011": "insufficient"},
                                            []), f"{RED} {lv}")
        self.assertEqual(lv.get("IF-002", (None,))[0], "test_level", f"{RED} {lv}")
        self.assertIn("Insufficient Evidence", self.gate_text(), RED)


class EvidenceCaseChar(EvidenceBase):
    """Behaviour the D43 build and this one share."""

    def test_case_D_provider_only_test_has_no_consumer_path(self):
        """A test that calls only the provider does not reach the consumer: G4 already fails (no G6 run)."""
        replace_function(self.itest, "test_TEST_010_report_uses_real_parser",
                         "def test_TEST_010_report_uses_real_parser():\n"
                         "    from pipeline.parser import parse\n"
                         "    assert parse('kim,90\\n') == [{'name': 'kim', 'score': 90}]\n")
        justify_test_change(self.sb, INTEGRATION)
        self.sb.review("G4")
        r4 = self.sb.gate("G4")[1]
        self.assertEqual(r4["status"], "FAILED", r4)
        wiring = [c for c in r4["checks"] if c["id"] == "G4.INTEGRATION_WIRING"][0]
        self.assertEqual(wiring["status"], "fail", wiring)
        self.assertTrue(any("TEST-010" in i for i in wiring["items"]), wiring)


TRACER = PLUGIN / "validator" / "vmodel_validator" / "tracer"
PROV = "def f(x=1):\n    if x == 'boom':\n        raise ValueError('boom')\n    return x\n"
CONS = ("import threading\nfrom concurrent.futures import ThreadPoolExecutor\n\nimport prov\n\n"
        "_POOL = ThreadPoolExecutor(max_workers=1)\n\n\n"
        "def use(x=1):\n    return prov.f(x)\n\n\n"
        "def spawn():\n    t = threading.Thread(target=prov.f, args=(2,))\n    t.start()\n    t.join()\n\n\n"
        "def pooled(x=1):\n    return _POOL.submit(prov.f, x).result()\n\n\n"
        "def unrelated():\n    return 0\n")


class TracerBase(unittest.TestCase):
    """The tracer on its own (D44 connection records), in both recording methods."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="vmodel-edge-")) / "연결 추적"
        self.tmp.mkdir()
        (self.tmp / "prov.py").write_text(PROV, encoding="utf-8")
        (self.tmp / "cons.py").write_text(CONS, encoding="utf-8")
        (self.tmp / "consimport.py").write_text("import prov\n\nDEFAULT = prov.f(9)\n", encoding="utf-8")
        self.out = self.tmp / "trace"
        self.out.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp.parent, ignore_errors=True)

    def run_py(self, code: str, setprofile: bool = False, **extra) -> subprocess.CompletedProcess:
        for f in self.out.glob("*.jsonl"):
            f.unlink()
        spec = self.tmp / "spec.json"
        spec.write_text(json.dumps({"out": str(self.out), "watch": {str(self.tmp / "prov.py"): "prov",
                                                                   str(self.tmp / "cons.py"): "cons",
                                                                   str(self.tmp / "consimport.py"): "consimport"},
                                    "edges": {"prov": ["cons", "consimport"]}, "force_setprofile": setprofile,
                                    **extra}),
                        encoding="utf-8")
        env = {k: v for k, v in os.environ.items() if not k.startswith(("PYTHON", "PYTEST", "VMODEL"))}
        env.update({"PYTHONPATH": str(TRACER), "VMODEL_TRACE_SPEC": str(spec),
                    "PYTEST_CURRENT_TEST": "t.py::test_TEST_001_a (call)"})
        return subprocess.run([sys.executable, "-c", code], cwd=str(self.tmp), env=env, capture_output=True,
                              timeout=120, text=True)

    def records(self) -> list[dict]:
        out = []
        for f in sorted(self.out.glob("*.jsonl")):
            out += [json.loads(x) for x in f.read_text(encoding="utf-8").splitlines()[1:]]
        return out

    def edges(self) -> list[tuple]:
        return [(r["t"], r["p"], r["e"], r["c"]) for r in self.records() if "e" in r and "c" in r]


SWITCH = "import os\nos.environ['PYTEST_CURRENT_TEST'] = 't.py::test_TEST_002_b (call)'\n"


class EvidenceTracerRed(TracerBase):
    """Each case runs in both recording methods (sys.monitoring on 3.12+, and the setprofile fallback)."""

    def _consumer_calling_the_provider_is_recorded_once(self, sp):
        res = self.run_py("import cons\nfor i in range(5):\n    cons.use(i)\n", sp)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(self.edges(), [("t.py::test_TEST_001_a", "call", "prov", "cons")], f"{RED} {sp}")

    def _direct_provider_call_is_not_a_connection(self, sp):
        res = self.run_py("import cons, prov\nprov.f(); cons.unrelated()\n" + SWITCH + "cons.use()\n", sp)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn({"t": "t.py::test_TEST_001_a", "p": "call", "m": "prov", "f": "f"}, self.records())
        self.assertEqual(self.edges(), [("t.py::test_TEST_002_b", "call", "prov", "cons")], f"{RED} {sp}")

    def _thread_started_by_the_consumer_carries_the_connection(self, sp):
        res = self.run_py("import cons\ncons.spawn()\n", sp)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(self.edges(), [("t.py::test_TEST_001_a", "call", "prov", "cons")], f"{RED} {sp}")

    def _pool_work_item_belongs_to_the_submitting_test(self, sp):
        """The worker is created by test 1; test 2's work item is test 2's, with the consumer on its submitting stack."""
        res = self.run_py("import cons\nassert cons.pooled(1) == 1\n" + SWITCH + "assert cons.pooled(2) == 2\n", sp)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn({"t": "t.py::test_TEST_002_b", "p": "call", "m": "prov", "f": "f"}, self.records(),
                      f"{RED} {sp}")
        self.assertEqual(sorted(self.edges()), [("t.py::test_TEST_001_a", "call", "prov", "cons"),
                                                ("t.py::test_TEST_002_b", "call", "prov", "cons")], f"{RED} {sp}")

    def test_stack_scan_cap_is_recorded(self):
        res = self.run_py("import cons, prov\nfor i in range(5):\n    prov.f(i)\ncons.use()\n", edge_scan_limit=3)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn({"edge_scan_capped": True, "t": "t.py::test_TEST_001_a", "p": "call", "e": "prov"},
                      self.records(), RED)
        self.assertEqual(self.edges(), [])  # capped: absence is recorded as uncertain, never as proof


class EvidenceTracerChar(TracerBase):
    def _import_time_consumer_call_is_not_a_connection(self, sp):
        """A consumer module body calling the provider while it is imported is not a consumer function call."""
        res = self.run_py("import consimport\n", sp)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn({"t": "t.py::test_TEST_001_a", "p": "call", "m": "prov", "f": "f"}, self.records())
        self.assertEqual(self.edges(), [])

    def _traced_program_behaves_the_same(self, sp):
        """Pool results, exceptions through futures, thread joins and return values are unchanged by the tracer."""
        code = ("import cons\nassert cons.pooled(7) == 7\n"
                "try:\n    cons.pooled('boom')\nexcept ValueError as e:\n    assert str(e) == 'boom'\n"
                "else:\n    raise SystemExit(3)\ncons.spawn()\nassert cons.use(5) == 5\nprint('done')\n")
        res = self.run_py(code, sp)
        self.assertEqual((res.returncode, res.stdout.strip()), (0, "done"), res.stderr)


def _per_method(cls):
    """test_<case>_monitoring / test_<case>_setprofile for every _<case> (red_green counts methods, not subtests)."""
    for name in [n for n, v in vars(cls).items() if n.startswith("_") and not n.startswith("__") and callable(v)
                 and getattr(v, "__qualname__", "").startswith(cls.__name__ + "._")]:
        for sp, tag in ((False, "monitoring"), (True, "setprofile")):
            setattr(cls, f"test{name}_{tag}", lambda self, _f=getattr(cls, name), _sp=sp: _f(self, _sp))
    return cls


_per_method(EvidenceTracerRed)
_per_method(EvidenceTracerChar)

if __name__ == "__main__":
    unittest.main()

"""Third independent review (08469ae, docs/g6/WORKITEM.md section 7.3): accepted findings as tests first.

RED target: git archive 08469ae plugins/vmodel. Numbers R1..R14 follow the review report. Decision D43 (reliable
runtime facts only) changes what some of the earlier review tests expect; see the notes there.
"""
from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from g6_base import RED, SandboxClass, file_sha256, justify_test_change, replace_function
from helpers import PLUGIN

INTEGRATION = "tests/integration/test_pipeline.py"


class R3WiringBase(SandboxClass):
    """pipeline, split commands, G1-G3 PASSED, code in place (G4 not evaluated)."""
    upto = "G3"

    @classmethod
    def build(cls, sb):
        super().build(sb)
        sb.put_code()

    @property
    def itest(self):
        return self.sb.root / INTEGRATION

    def path(self, iid: str, tid: str) -> str:
        code, out = self.sb.vm("wiring", "WI-001", "--json")
        self.assertNotEqual(code, 2, f"{RED} wiring crashed: {out[-400:]}")
        return json.loads(out)["interfaces"][iid]["tests"][tid]["path"]

    def prepend_to_test_module(self, text: str) -> None:
        body = self.itest.read_text(encoding="utf-8")
        self.itest.write_text(body.replace("from pipeline.report import main, summarize\n",
                                           "from pipeline.report import main, summarize\n" + text, 1),
                              encoding="utf-8")


class R3WiringRed(R3WiringBase):
    def test_R4_attribute_assignment_does_not_unbind_a_module(self):
        self.prepend_to_test_module("from pipeline import report\n\nreport.DEBUG = True\n")
        replace_function(self.itest, "test_TEST_010_report_uses_real_parser",
                         "def test_TEST_010_report_uses_real_parser():\n"
                         "    assert report.summarize('kim,90\\nlee,95\\n')['top'] == 'lee'\n")
        self.assertEqual(self.path("IF-001", "TEST-010"), "static", f"{RED} report.DEBUG = True binds nothing")

    def test_R5_try_import_with_fallback_keeps_the_import(self):
        body = self.itest.read_text(encoding="utf-8")
        self.itest.write_text(body.replace(
            "from pipeline.report import main, summarize\n",
            "try:\n    from pipeline.report import main, summarize\nexcept ImportError:  # pragma: no cover\n"
            "    main = summarize = None\n", 1), encoding="utf-8")
        self.assertEqual(self.path("IF-001", "TEST-010"), "static", f"{RED} the except branch is only a fallback")

    def test_R5_try_import_then_later_def_is_shadowed(self):
        body = self.itest.read_text(encoding="utf-8")
        self.itest.write_text(body.replace(
            "from pipeline.report import main, summarize\n",
            "try:\n    from pipeline.report import main, summarize\nexcept ImportError:  # pragma: no cover\n"
            "    pass\n\n\ndef summarize(text):  # noqa: F811\n    return {'count': 3, 'total': 255, 'top': 'lee'}\n", 1),
            encoding="utf-8")
        self.assertNotEqual(self.path("IF-001", "TEST-010"), "static", f"{RED} the later top-level def wins")

    def test_R6_src_package_init_with_pythonpath_src(self):
        (self.sb.root / "src/__init__.py").write_text("", encoding="utf-8")
        self.assertEqual(self.path("IF-001", "TEST-010"), "static", f"{RED} pythonpath=['src'] makes it pipeline.report")

    def test_R7_cyclic_star_alias_is_not_a_crash(self):
        (self.sb.root / "src/pipeline/a.py").write_text("from .b import *  # noqa: F403\n\nX = Y()  # noqa: F405\n",
                                                        encoding="utf-8")
        (self.sb.root / "src/pipeline/b.py").write_text("from .a import *  # noqa: F403\n\nY = X()  # noqa: F405\n",
                                                        encoding="utf-8")
        replace_function(self.itest, "test_TEST_012_cli_main_reads_file",
                         "def test_TEST_012_cli_main_reads_file():\n    from pipeline.a import X\n    X.run()\n")
        self.assertIn(self.path("IF-002", "TEST-012"), ("none", "runtime_candidate"))
        code, out = self.sb.vm("gate", "WI-001", "G4", "--json")
        self.assertNotEqual(code, 2, f"{RED} {out[-400:]}")

    def test_R9_non_list_consumers_is_not_a_crash(self):
        arch = self.sb.load("architecture.json")
        arch["interfaces"][0]["consumers"] = 5
        self.sb.save("architecture.json", arch)
        for cmd in (("trace", "WI-001"), ("report", "WI-001"), ("wiring", "WI-001"), ("status",), ("impact", "WI-001")):
            code, out = self.sb.vm(*cmd)
            self.assertNotEqual(code, 2, f"{RED} {cmd}: {out[-300:]}")

    def test_R11_only_the_callable_argument_of_pytest_raises_is_called(self):
        replace_function(self.itest, "test_TEST_012_cli_main_reads_file",
                         "def test_TEST_012_cli_main_reads_file():\n"
                         "    assert pytest.raises(ValueError, int, 'x') is not None\n"
                         "    assert pytest.raises(main) is not None\n")
        self.assertNotEqual(self.path("IF-002", "TEST-012"), "static", f"{RED} main is the expected exception here")


class R3G6Red(SandboxClass):
    """pipeline, split commands, G1-G5 PASSED."""

    @property
    def itest(self):
        return self.sb.root / INTEGRATION

    def to_g6(self, interfaces: list | None = None) -> tuple[dict, dict, int | None, dict]:
        justify_test_change(self.sb, INTEGRATION)
        self.sb.review("G4", interfaces=interfaces)
        r4 = self.sb.gate("G4")[1]
        r5 = self.sb.gate("G5")[1] if r4["status"] == "PASSED" else {}
        if r5.get("status") != "PASSED":
            return r4, r5, None, {}
        code, out = self.sb.vm("gate", "WI-001", "G6", "--json")
        try:
            return r4, r5, code, json.loads(out)
        except json.JSONDecodeError:
            return r4, r5, code, {"raw": out[-800:]}

    def declare_012(self, kind: str) -> list[dict]:
        entries = self.sb.interface_review_entries()
        for e in entries:
            if e["id"] == "IF-002":
                e["runtime_paths"] = [{"test": "TEST-012", "kind": kind, "test_file_sha256": file_sha256(self.itest)}]
        return entries

    def test_R2_api_server_started_in_a_function_fixture(self):
        replace_function(self.itest, "test_TEST_012_cli_main_reads_file",
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
        r4, r5, code, r6 = self.to_g6(self.declare_012("api"))
        self.assertEqual((r4["status"], r5.get("status")), ("PASSED", "PASSED"), r4)
        self.assertEqual(r6.get("status"), "PASSED", f"{RED} handler threads belong to the test, in its call phase: {r6}")

    def test_R2_consumer_using_a_shared_thread_pool(self):
        rp = self.sb.root / "src/pipeline/report.py"
        rp.write_text(rp.read_text(encoding="utf-8").replace(
            "from pipeline.parser import parse\n",
            "from concurrent.futures import ThreadPoolExecutor\n\nfrom pipeline.parser import parse\n\n"
            "_POOL = ThreadPoolExecutor(max_workers=1)\n").replace(
            "    records = parse(text)\n", "    records = _POOL.submit(parse, text).result()\n"), encoding="utf-8")
        body = self.itest.read_text(encoding="utf-8")  # TEST-012 first: it creates the pool worker
        t12_start = body.index("\n\ndef test_TEST_012")
        t12 = body[t12_start:]
        body = body[:t12_start]
        first = body.index("\n\ndef test_TEST_010")
        self.itest.write_text(body[:first] + t12.rstrip("\n") + "\n" + body[first:], encoding="utf-8")
        r4, r5, code, r6 = self.to_g6()
        self.assertEqual((r4["status"], r5.get("status")), ("PASSED", "PASSED"), r4)
        self.assertEqual(r6.get("status"), "PASSED", f"{RED} the provider runs in a pool thread: {r6}")

    def test_R12_parametrize_ids_with_double_colons(self):
        replace_function(self.itest, "test_TEST_010_report_uses_real_parser",
                         "@pytest.mark.parametrize('host', ['::1', 'fe80::1'])\n"
                         "def test_TEST_010_report_uses_real_parser(host):\n"
                         "    assert summarize('kim,90\\nlee,95\\n')['top'] == 'lee'\n")
        r4, r5, code, r6 = self.to_g6()
        self.assertEqual((r4["status"], r5.get("status")), ("PASSED", "PASSED"), r4)
        self.assertEqual(r6.get("status"), "PASSED", f"{RED} '::1' in the id: {r6}")



class R3G6Accept(SandboxClass):
    """New rule D43 (new core only): the provider must have run somewhere in the integration run."""
    itest = R3G6Red.itest
    to_g6 = R3G6Red.to_g6

    def test_D43_provider_that_never_runs_in_the_whole_run_blocks(self):
        (self.sb.root / "tests/integration/conftest.py").write_text(
            "import pytest\n\n\n@pytest.fixture(autouse=True)\ndef _no_parser(monkeypatch):\n"
            "    monkeypatch.setattr('pipeline.report.parse', lambda text: [{'name': 'b', 'score': 2}] if text else [])\n",
            encoding="utf-8")
        for name in ("test_TEST_010_report_uses_real_parser", "test_TEST_011_parser_error_reaches_report"):
            replace_function(self.itest, name, f"def {name}():\n    assert summarize('x')['count'] == 1\n")
        replace_function(self.itest, "test_TEST_012_cli_main_reads_file",
                         "def test_TEST_012_cli_main_reads_file(tmp_path, capsys):\n"
                         "    f = tmp_path / 'scores.csv'\n    f.write_text('a,1\\n', encoding='utf-8')\n"
                         "    assert main([str(f)]) == 0\n")
        r4, r5, code, r6 = self.to_g6()
        self.assertEqual((r4["status"], r5.get("status")), ("PASSED", "PASSED"), r4)
        self.assertEqual((r6.get("status"), r6.get("blocked_reason")), ("BLOCKED", "integration_evidence_insufficient"),
                         f"{RED} pipeline/parser.py never ran in the integration run: {r6}")
        cov = [c for c in r6["checks"] if c["id"] == "G6.IF_COVERAGE"][0]
        self.assertTrue(any("IF-001" in i and "never ran" in i for i in cov["items"]), cov)


class R3UnitRed(unittest.TestCase):
    """Validator internals driven directly (the conditions are hard to stage through a whole project)."""

    def gates(self):
        sys.path.insert(0, str(PLUGIN / "validator"))
        try:
            for m in [m for m in sys.modules if m == "vmodel_validator" or m.startswith("vmodel_validator.")]:
                del sys.modules[m]
            return importlib.import_module("vmodel_validator.gates")
        finally:
            sys.path.remove(str(PLUGIN / "validator"))

    def test_R8_oversized_trace_file_counts_as_truncated(self):
        gates = self.gates()
        d = Path(tempfile.mkdtemp(prefix="vmodel-trace-"))
        try:
            f = d / "1-x.jsonl"
            with open(f, "w", encoding="utf-8") as fh:
                fh.write(json.dumps({"v": 1, "pid": 1, "method": "x"}) + "\n")
                fh.truncate(getattr(gates, "TRACE_FILE_LIMIT", 32 * 1024 * 1024) + 10)
            rt = gates.read_runtime_trace(d)
            self.assertTrue(rt.get("truncated"), f"{RED} an oversized trace must not read as 'no trace': {rt}")
        finally:
            import shutil
            shutil.rmtree(d, ignore_errors=True)

    def test_R13_tracer_creates_no_dummy_threads(self):
        tracer = PLUGIN / "validator" / "vmodel_validator" / "tracer"
        d = Path(tempfile.mkdtemp(prefix="vmodel-tracer-"))
        try:
            (d / "mod.py").write_text("def f():\n    return 1\n", encoding="utf-8")
            (d / "trace").mkdir()
            spec = d / "spec.json"
            spec.write_text(json.dumps({"out": str(d / "trace"), "watch": {str(d / "mod.py"): "mod"}}), encoding="utf-8")
            code = ("import _thread, threading, time, mod\n_thread.start_new_thread(mod.f, ())\ntime.sleep(0.3)\n"
                    "print(len(threading.enumerate()))\n")
            env = {k: v for k, v in os.environ.items() if not k.startswith(("PYTHON", "PYTEST", "VMODEL"))}
            env.update(PYTHONPATH=str(tracer), VMODEL_TRACE_SPEC=str(spec))
            out = subprocess.run([sys.executable, "-c", code], cwd=str(d), env=env, capture_output=True, text=True,
                                 timeout=60)
            self.assertEqual(out.stdout.strip(), "1", f"{RED} a _DummyThread was created: {out.stdout} {out.stderr}")
        finally:
            import shutil
            shutil.rmtree(d, ignore_errors=True)


class R3PreexistingRed(SandboxClass):
    upto = "G1"

    def test_R10_huge_seq_in_the_ledger_is_an_integrity_failure_not_a_crash(self):
        ledger = self.sb.root / ".vmodel/state/ledger.jsonl"
        lines = ledger.read_text(encoding="utf-8").splitlines()
        lines.append('{"seq": 1' + "0" * 5000 + ', "prev": "x", "record": {}, "sig": "x"}')
        ledger.write_text("\n".join(lines) + "\n", encoding="utf-8")
        for cmd in (("status",), ("audit",), ("gate", "WI-001", "G1")):
            code, out = self.sb.vm(*cmd)
            self.assertNotEqual(code, 2, f"{RED} {cmd}: {out[-300:]}")


if __name__ == "__main__":
    unittest.main()

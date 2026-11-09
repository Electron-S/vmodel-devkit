"""Fourth independent review (c83df4b = code 14b34af, 2026-11-09 final verification): findings as tests first.

RED target: git archive 14b34af plugins/vmodel. Scenario numbers S1..S12 follow the review report (H1-H4 HIGH,
M1-M6 MEDIUM, L1-L4 LOW). Each was re-run here before being accepted (global rule: verify a reviewer's claim).
S1-S3 are closed by D44 (test-level evidence only); the others by the fixes listed in DECISIONS D44.
"""
from __future__ import annotations

import importlib
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path

from g6_base import RED, SandboxClass, file_sha256, justify_test_change, ledger_record, replace_function
from helpers import PLUGIN

INTEGRATION = "tests/integration/test_pipeline.py"


def chk(res: dict, cid: str) -> dict:
    return ([c for c in res.get("checks") or [] if c["id"] == cid] or [{}])[0]


def iface(rec: dict, iid: str) -> dict:
    return ([i for i in rec.get("interfaces") or [] if i.get("id") == iid] or [{}])[0]


class R4Base(SandboxClass):
    """pipeline fixture, split commands, G1-G5 PASSED (restored before every test)."""

    @property
    def itest(self):
        return self.sb.root / INTEGRATION

    def to_g6(self, interfaces: list | None = None, rels: tuple = (INTEGRATION,)) -> tuple[dict, dict, dict]:
        for rel in rels:
            justify_test_change(self.sb, rel)
        self.sb.review("G4", interfaces=interfaces)
        r4 = self.sb.gate("G4")[1]
        assert r4["status"] == "PASSED", json.dumps(r4, indent=1, ensure_ascii=False)[:3000]
        r5 = self.sb.gate("G5")[1]
        assert r5["status"] == "PASSED", json.dumps(r5, indent=1, ensure_ascii=False)[:3000]
        return r4, r5, self.sb.gate("G6")[1]

    def declare(self, iid: str, tests: tuple, kind: str, symbols: list | None = None) -> list[dict]:
        entries = self.sb.interface_review_entries()
        for e in entries:
            if e["id"] == iid:
                e["runtime_paths"] = [{"test": t, "kind": kind, "test_file_sha256": file_sha256(self.itest)}
                                      for t in tests]
                if symbols:
                    e["provider_symbols"] = symbols
        return entries

    def add_header(self) -> None:
        rp = self.sb.root / "src/pipeline/report.py"
        rp.write_text(rp.read_text(encoding="utf-8").replace(
            "def summarize(", "def header() -> str:\n    return 'count,total,top'\n\n\ndef summarize(", 1),
            encoding="utf-8")


SERVER_SUMMARIZE = (
    "import sys, json\n"
    "for line in sys.stdin:\n"
    "    line = line.strip()\n"
    "    if line == 'ping':\n"
    "        print('pong', flush=True)\n"
    "        continue\n"
    "    from pipeline.report import summarize\n"
    "    print(json.dumps(summarize(line.replace(';', chr(10)))), flush=True)\n")
SERVER_MAIN = (  # the IF-002 entry itself: one file path per line, main() prints the JSON summary
    "import sys\n"
    "from pipeline.report import main\n"
    "for line in sys.stdin:\n"
    "    main([line.strip()])\n"
    "    sys.stdout.flush()\n")
CHILD_ENV = (
    "    import os\n    import subprocess\n    import sys\n    from pathlib import Path\n"
    "    env = dict(os.environ)\n"
    "    src = str(Path(__file__).resolve().parents[2] / 'src')\n"
    "    env['PYTHONPATH'] = os.pathsep.join(p for p in (src, env.get('PYTHONPATH')) if p)\n")


class R4AttributionRed(R4Base):
    def test_S1_H1_mocked_tests_are_not_credited_by_another_interfaces_test(self):
        replace_function(self.itest, "test_TEST_010_report_uses_real_parser",
                         "def test_TEST_010_report_uses_real_parser(monkeypatch):\n"
                         "    monkeypatch.setattr('pipeline.report.parse', lambda text: [{'name': 'lee', 'score': 95}])\n"
                         "    assert summarize('anything') == {'count': 1, 'total': 95, 'top': 'lee'}\n")
        replace_function(self.itest, "test_TEST_011_parser_error_reaches_report",
                         "def test_TEST_011_parser_error_reaches_report():\n"
                         "    from pipeline import report\n    real = report.parse\n"
                         "    report.parse = lambda text: (_ for _ in ()).throw(ValueError('line 1'))\n"
                         "    try:\n        with pytest.raises(ValueError):\n            summarize('kim,ninety')\n"
                         "    finally:\n        report.parse = real\n")
        _r4, _r5, r6 = self.to_g6()
        self.assertEqual(r6.get("status"), "BLOCKED", f"{RED} only TEST-012 (IF-002) ran the real parser: {r6}")
        self.assertEqual(iface(ledger_record(self.sb, r6["record_id"]), "IF-001").get("covered_by"), [])

    def test_S2_H4_provider_and_an_unrelated_consumer_function_are_not_a_connection(self):
        self.add_header()
        self.itest.write_text(self.itest.read_text(encoding="utf-8").replace(
            "from pipeline.report import main, summarize\n",
            "from pipeline.parser import parse\nfrom pipeline.report import header, main, summarize\n", 1),
            encoding="utf-8")
        replace_function(self.itest, "test_TEST_010_report_uses_real_parser",
                         "def test_TEST_010_report_uses_real_parser():\n"
                         "    assert parse('kim,90') == [{'name': 'kim', 'score': 90}]\n"
                         "    assert header() == 'count,total,top'\n")
        replace_function(self.itest, "test_TEST_011_parser_error_reaches_report",
                         "def test_TEST_011_parser_error_reaches_report():\n"
                         "    with pytest.raises(ValueError):\n        parse('kim,ninety')\n"
                         "    assert header()\n")
        _r4, _r5, r6 = self.to_g6()
        self.assertEqual(r6.get("status"), "BLOCKED", f"{RED} report never called parse in TEST-010/011: {r6}")

    def test_S3_H2_import_time_helper_is_not_provider_evidence(self):
        pp = self.sb.root / "src/pipeline/parser.py"
        pp.write_text(pp.read_text(encoding="utf-8") + "\n\ndef _strip(s: str) -> str:\n    return s.strip()\n\n\n"
                      "_SEPARATOR = _strip(' , ')\n", encoding="utf-8")
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
        _r4, _r5, r6 = self.to_g6()
        self.assertEqual(r6.get("status"), "BLOCKED", f"{RED} parse() never ran; only _strip at import: {r6}")
        self.assertEqual(iface(ledger_record(self.sb, r6["record_id"]), "IF-001").get("verification"), "insufficient",
                         RED)

    def test_S7_H4_unrelated_provider_function_in_a_child_is_not_the_interface(self):
        self.add_header()
        replace_function(self.itest, "test_TEST_012_cli_main_reads_file",
                         "def test_TEST_012_cli_main_reads_file():\n" + CHILD_ENV +
                         "    res = subprocess.run([sys.executable, '-c', 'import pipeline.report as r; print(r.header())'],\n"
                         "                         capture_output=True, env=env, check=True)\n"
                         "    assert res.stdout\n")
        _r4, _r5, r6 = self.to_g6(self.declare("IF-002", ("TEST-012",), "subprocess"))
        self.assertEqual(r6.get("status"), "BLOCKED", f"{RED} IF-002's main() never ran, only header(): {r6}")
        self.assertEqual(iface(ledger_record(self.sb, r6["record_id"]), "IF-002").get("covered_by"), [], RED)


class R4ProcessRed(R4Base):
    def test_S8_H3_long_lived_child_is_not_credited_to_the_test_that_started_it(self):
        """TEST-010 starts a cached helper process and only pings it; TEST-011 sends the real data to it."""
        helper = ("SERVER_CODE = " + json.dumps(SERVER_SUMMARIZE) + "\n_SRV = []\n\n\n"
                  "def _server():\n"
                  "    import os\n    import subprocess\n    import sys\n    from pathlib import Path\n"
                  "    if not _SRV:\n"
                  "        env = dict(os.environ)\n"
                  "        src = str(Path(__file__).resolve().parents[2] / 'src')\n"
                  "        env['PYTHONPATH'] = os.pathsep.join(p for p in (src, env.get('PYTHONPATH')) if p)\n"
                  "        _SRV.append(subprocess.Popen([sys.executable, '-u', '-c', SERVER_CODE], stdin=subprocess.PIPE,\n"
                  "                                     stdout=subprocess.PIPE, env=env, text=True))\n"
                  "    return _SRV[0]\n")
        self.itest.write_text(self.itest.read_text(encoding="utf-8").replace(
            "from pipeline.report import main, summarize\n", "from pipeline.report import main, summarize\n\n" + helper,
            1), encoding="utf-8")
        replace_function(self.itest, "test_TEST_010_report_uses_real_parser",
                         "def test_TEST_010_report_uses_real_parser():\n    srv = _server()\n"
                         "    srv.stdin.write('ping\\n')\n    srv.stdin.flush()\n"
                         "    assert srv.stdout.readline().strip() == 'pong'\n")
        replace_function(self.itest, "test_TEST_011_parser_error_reaches_report",
                         "def test_TEST_011_parser_error_reaches_report():\n    srv = _server()\n"
                         "    srv.stdin.write('kim,90;lee,95\\n')\n    srv.stdin.flush()\n"
                         "    assert json.loads(srv.stdout.readline())['top'] == 'lee'\n")
        _r4, _r5, r6 = self.to_g6(self.declare("IF-001", ("TEST-010", "TEST-011"), "subprocess"))
        cov = iface(ledger_record(self.sb, r6["record_id"]), "IF-001").get("covered_by")
        self.assertNotIn("TEST-010", cov or [], f"{RED} TEST-010 only pinged; the parse ran for TEST-011: {r6}")
        self.assertEqual(r6.get("status"), "BLOCKED", f"{RED} {r6}")

    def test_S10_M1_server_process_started_by_a_function_fixture(self):
        """Case E: a function-scoped fixture starts the IF-002 entry as a server process, the test talks to it."""
        body = self.itest.read_text(encoding="utf-8").replace(
            "from pipeline.report import main, summarize\n",
            "from pipeline.report import main, summarize\n\n"
            "SERVER_CODE = " + json.dumps(SERVER_MAIN) + "\n\n\n"
            "@pytest.fixture\ndef server():\n" + CHILD_ENV +
            "    proc = subprocess.Popen([sys.executable, '-u', '-c', SERVER_CODE], stdin=subprocess.PIPE,\n"
            "                            stdout=subprocess.PIPE, env=env, text=True)\n"
            "    yield proc\n    proc.stdin.close()\n    proc.wait(timeout=30)\n", 1)
        self.itest.write_text(body, encoding="utf-8")
        replace_function(self.itest, "test_TEST_012_cli_main_reads_file",
                         "def test_TEST_012_cli_main_reads_file(server, tmp_path):\n"
                         "    f = tmp_path / 'scores.csv'\n    f.write_text('a,1\\nb,2\\n', encoding='utf-8')\n"
                         "    server.stdin.write(str(f) + '\\n')\n    server.stdin.flush()\n"
                         "    assert json.loads(server.stdout.readline()) == {'count': 2, 'total': 3, 'top': 'b'}\n")
        _r4, _r5, r6 = self.to_g6(self.declare("IF-002", ("TEST-012",), "subprocess"))
        self.assertEqual(r6.get("status"), "PASSED", f"{RED} legitimate subprocess integration test: {r6}")
        self.assertEqual(iface(ledger_record(self.sb, r6["record_id"]), "IF-002").get("covered_by"), ["TEST-012"])


class R4EvidenceRed(R4Base):
    def test_S6_M5_leaked_child_cannot_change_the_signed_trace(self):
        replace_function(self.itest, "test_TEST_012_cli_main_reads_file",
                         "def test_TEST_012_cli_main_reads_file(tmp_path, capsys):\n" + CHILD_ENV +
                         "    subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(2); "
                         "from pipeline.parser import parse; parse(\"a,1\")'], env=env, start_new_session=True,\n"
                         "                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, "
                         "stderr=subprocess.DEVNULL)\n"
                         "    f = tmp_path / 'scores.csv'\n    f.write_text('a,1\\nb,2\\n', encoding='utf-8')\n"
                         "    assert main([str(f)]) == 0\n"
                         "    assert json.loads(capsys.readouterr().out) == {'count': 2, 'total': 3, 'top': 'b'}\n")
        _r4, _r5, r6 = self.to_g6()
        ev = r6["evidence"][0]["path"]
        time.sleep(6)
        code, out = self.sb.vm("verify-evidence", ev)
        self.assertEqual(code, 0, f"{RED} the signed evidence changed after the run: {out[-600:]}")
        code, out = self.sb.vm("audit")
        self.assertEqual(code, 0, f"{RED} {out[-600:]}")

    def test_S12_M3_bracket_in_the_test_directory_name(self):
        new_rel = "tests/integration/[slow]/test_pipeline.py"
        (self.sb.root / new_rel).parent.mkdir()
        shutil.move(str(self.itest), str(self.sb.root / new_rel))
        _r4, _r5, r6 = self.to_g6(rels=(INTEGRATION, new_rel))
        self.assertEqual(r6.get("status"), "PASSED", f"{RED} '[' in the path is not a parameter: {r6}")

    @unittest.skipIf(sys.platform.startswith("win") or (hasattr(os, "geteuid") and os.geteuid() == 0),
                     "POSIX permissions (not root)")
    def test_S11_M4_unreadable_top_level_directory_is_not_a_crash(self):
        d = self.sb.root / "pgdata"
        d.mkdir()
        (d / "PG_VERSION").write_text("16", encoding="utf-8")
        os.chmod(d, 0o000)
        try:
            codes = {cmd: self.sb.vm(*cmd)[0] for cmd in (("wiring", "WI-001"), ("gate", "WI-001", "G4"),
                                                         ("gate", "WI-001", "G6"))}
        finally:
            os.chmod(d, 0o755)
        self.assertTrue(all(c != 2 for c in codes.values()), f"{RED} internal error: {codes}")


class R4StaticRed(R4Base):
    """Static analysis only (vmodel wiring, read-only)."""

    def wiring(self) -> dict:
        code, out = self.sb.vm("wiring", "WI-001", "--json")
        assert code != 2, out[-400:]
        return json.loads(out)

    def test_S4_M6_mocker_setattr_and_assignment_are_provider_patches(self):
        replace_function(self.itest, "test_TEST_010_report_uses_real_parser",
                         "def test_TEST_010_report_uses_real_parser(mocker):\n"
                         "    mocker.patch('pipeline.report.parse', return_value=[{'name': 'lee', 'score': 95}])\n"
                         "    assert summarize('x')['top'] == 'lee'\n")
        replace_function(self.itest, "test_TEST_011_parser_error_reaches_report",
                         "def test_TEST_011_parser_error_reaches_report():\n"
                         "    from pipeline import report\n    real = report.parse\n"
                         "    setattr(report, 'parse', lambda t: [])\n"
                         "    report.parse = lambda t: []\n"
                         "    try:\n        assert summarize('x')['count'] == 0\n"
                         "    finally:\n        setattr(report, 'parse', real)\n")
        w = self.wiring()["interfaces"]["IF-001"]["tests"]
        out = {t: v["best"]["patched_provider"] for t, v in w.items()}
        self.assertTrue(all(out.values()), f"{RED} mocking not reported as a provider patch: {out}")

    def test_S5_L1_pytest_ini_pythonpath_with_src_package(self):
        (self.sb.root / "src/__init__.py").write_text("", encoding="utf-8")
        pj = self.sb.root / "pyproject.toml"
        pj.write_text(pj.read_text(encoding="utf-8").split("[tool.pytest.ini_options]")[0], encoding="utf-8")
        (self.sb.root / "pytest.ini").write_text("[pytest]\npythonpath = src\ntestpaths = tests\n", encoding="utf-8")
        w = self.wiring()["interfaces"]["IF-001"]["tests"]
        self.assertEqual(w["TEST-010"]["path"], "static", f"{RED} pytest.ini pythonpath ignored: {w['TEST-010']}")

    def test_S9_L2_plain_value_in_one_if_branch_keeps_the_import(self):
        self.itest.write_text(self.itest.read_text(encoding="utf-8").replace(
            "from pipeline.report import main, summarize\n",
            "import sys\nfrom pipeline.report import main, summarize\n\nif sys.version_info < (3, 0):  # never true\n"
            "    summarize = None\n", 1), encoding="utf-8")
        w = self.wiring()["interfaces"]["IF-001"]["tests"]
        self.assertEqual(w["TEST-010"]["path"], "static", f"{RED} {w['TEST-010']}")


class R4WindowAccept(unittest.TestCase):
    """Child-process lines re-read against the pytest process's test boundaries (new core only; found while fixing
    H3: when those boundaries may be missing, a child's lines are not attributed at all)."""

    def gates(self):
        sys.path.insert(0, str(PLUGIN / "validator"))
        try:
            for m in [m for m in sys.modules if m == "vmodel_validator" or m.startswith("vmodel_validator.")]:
                del sys.modules[m]
            return importlib.import_module("vmodel_validator.gates")
        finally:
            sys.path.remove(str(PLUGIN / "validator"))

    def setUp(self):
        self.d = Path(tempfile.mkdtemp(prefix="vmodel-window-"))

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def write(self, name: str, head: dict, lines: list[dict]) -> None:
        (self.d / name).write_text("\n".join(json.dumps(x) for x in [head, *lines]) + "\n", encoding="utf-8")

    X, Y = "t/test_i.py::test_TEST_010_a", "t/test_i.py::test_TEST_011_b"

    def child(self) -> None:
        self.write("2-c.jsonl", {"v": 2, "pid": 2, "method": "m", "spawned_in": [self.X, "setup"]},
                   [{"t": self.X, "p": "setup", "m": "src/p.py", "f": "parse", "ts": 15.0},
                    {"t": self.X, "p": "setup", "m": "src/p.py", "f": "later", "ts": 25.0}])

    def phases(self, rt: dict) -> dict:
        return {func: ph for _t, ph, _f, _m, func in rt["_events"] if _f == "2-c.jsonl"}

    def test_child_lines_follow_the_test_window(self):
        self.write("1-p.jsonl", {"v": 2, "pid": 1, "method": "m", "spawned_in": None},
                   [{"b": self.X, "p": "call", "ts": 10.0}, {"b": self.Y, "p": "call", "ts": 20.0}])
        self.child()
        self.assertEqual(self.phases(self.gates().read_runtime_trace(self.d)), {"parse": "call", "later": "detached"})

    def test_truncated_pytest_process_file_detaches_child_lines(self):
        self.write("1-p.jsonl", {"v": 2, "pid": 1, "method": "m", "spawned_in": None},
                   [{"b": self.X, "p": "call", "ts": 10.0}, {"truncated": True}])
        self.child()
        self.assertEqual(self.phases(self.gates().read_runtime_trace(self.d)), {"parse": "detached", "later": "detached"})

    def test_no_pytest_process_file_detaches_child_lines(self):
        self.child()
        self.assertEqual(self.phases(self.gates().read_runtime_trace(self.d)), {"parse": "detached", "later": "detached"})


if __name__ == "__main__":
    unittest.main()

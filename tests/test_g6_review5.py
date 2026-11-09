"""Fifth independent review (464d01b, 2026-11-09 final verification): findings as tests first.

RED target: git archive 464d01b plugins/vmodel. Scenarios N1..N8 follow the review report; each was re-run here before
being accepted (the reviewer's reproduction file, adapted: RED markers, no prints). N4/N5 (asyncio.gather, a consumer
handing out the provider's generator) are not fixed: they stay BLOCKED (conservative) and are characterised. N8 is
decided the conservative way: a line in the same clock tick as a boundary is never credited.
"""
from __future__ import annotations

import json
import time
import unittest

from g6_base import RED, SandboxClass, file_sha256, justify_test_change, ledger_record, replace_function

INTEGRATION = "tests/integration/test_pipeline.py"
SERVER_CODE = (
    "import sys, json\n"
    "for line in sys.stdin:\n"
    "    line = line.strip()\n"
    "    if line == 'ping':\n"
    "        print('pong', flush=True)\n"
    "        continue\n"
    "    from pipeline.report import summarize\n"
    "    print(json.dumps(summarize(line.replace(';', chr(10)))), flush=True)\n")
SERVER_HELPER = (
    "SERVER_CODE = " + json.dumps(SERVER_CODE) + "\n"
    "_SRV = []\n\n\n"
    "def _server():\n"
    "    import os\n    import subprocess\n    import sys\n    from pathlib import Path\n"
    "    if not _SRV:\n"
    "        env = dict(os.environ)\n"
    "        src = str(Path(__file__).resolve().parents[2] / 'src')\n"
    "        env['PYTHONPATH'] = os.pathsep.join(p for p in (src, env.get('PYTHONPATH')) if p)\n"
    "        _SRV.append(subprocess.Popen([sys.executable, '-u', '-c', SERVER_CODE], stdin=subprocess.PIPE,\n"
    "                                     stdout=subprocess.PIPE, env=env, text=True))\n"
    "    return _SRV[0]\n")
MOCKED_011 = ("def test_TEST_011_parser_error_reaches_report(monkeypatch):\n"
              "    monkeypatch.setattr('pipeline.report.parse', lambda text: [{'name': 'x', 'score': 1}])\n"
              "    assert summarize('kim,ninety')['count'] == 1\n")
PING_010 = ("def test_TEST_010_report_uses_real_parser():\n"
            "    srv = _server()\n"
            "    srv.stdin.write('ping\\n')\n    srv.stdin.flush()\n"
            "    assert srv.stdout.readline().strip() == 'pong'\n")


def chk(res: dict, cid: str) -> dict:
    return ([c for c in res.get("checks") or [] if c["id"] == cid] or [{}])[0]


class R5Base(SandboxClass):
    @property
    def itest(self):
        return self.sb.root / INTEGRATION

    def to_g6(self, interfaces: list | None = None, changed: tuple = (INTEGRATION,)):
        for rel in changed:
            justify_test_change(self.sb, rel)
        self.sb.review("G4", interfaces=interfaces)
        r4 = self.sb.gate("G4")[1]
        r5 = self.sb.gate("G5")[1] if r4["status"] == "PASSED" else {}
        if r5.get("status") != "PASSED":
            return r4, r5, {}
        return r4, r5, self.sb.gate("G6")[1]

    def declare(self, entries_for: dict) -> list[dict]:
        entries = self.sb.interface_review_entries()
        for e in entries:
            if e["id"] in entries_for:
                e["runtime_paths"] = [{"test": t, "kind": k, "test_file_sha256": file_sha256(self.sb.root / f)}
                                      for t, k, f in entries_for[e["id"]]]
        return entries

    def prepend(self, text: str, path=None) -> None:
        p = path or self.itest
        body = p.read_text(encoding="utf-8")
        p.write_text(body.replace("from pipeline.report import main, summarize\n",
                                  "from pipeline.report import main, summarize\n\n" + text, 1), encoding="utf-8")


class R5WindowRed(R5Base):
    def test_N1_child_work_in_the_spawning_tests_teardown_counts_as_call(self):
        """TEST-010's call only pings a helper process it starts; an autouse fixture sends the real data in teardown.
        REQ-G6-32: path B proof must come from the test's call phase."""
        self.prepend(SERVER_HELPER)
        replace_function(self.itest, "test_TEST_010_report_uses_real_parser", PING_010)
        replace_function(self.itest, "test_TEST_011_parser_error_reaches_report", MOCKED_011)
        (self.sb.root / "tests/integration/conftest.py").write_text(
            "import json\n\nimport pytest\n\n\n@pytest.fixture(autouse=True)\ndef _drain(request):\n    yield\n"
            "    mod = request.module\n"
            "    if getattr(mod, '_SRV', None) and not getattr(mod, '_DRAINED', False):\n"
            "        mod._DRAINED = True\n"
            "        mod._SRV[0].stdin.write('kim,90;lee,95\\n')\n        mod._SRV[0].stdin.flush()\n"
            "        json.loads(mod._SRV[0].stdout.readline())\n", encoding="utf-8")
        r4, r5, r6 = self.to_g6(self.declare({"IF-001": [("TEST-010", "subprocess", INTEGRATION)]}),
                                changed=(INTEGRATION, "tests/integration/conftest.py"))
        rec = ledger_record(self.sb, r6["record_id"]) if r6.get("record_id") else {}
        if1 = [i for i in rec.get("interfaces") or [] if i["id"] == "IF-001"]
        self.assertFalse(if1 and "TEST-010" in if1[0]["covered_by"], f"{RED} teardown work credited as TEST-010's call")
        self.assertEqual(r6.get("status"), "BLOCKED", r6)

    def test_N1b_unwatched_test_between_extends_the_window(self):
        """TEST-010 (its own file) starts the helper and pings; an unmapped test in an unwatched file sends the real data
        through the same process; TEST-011 is mocked. No boundary is written by the unwatched test."""
        a = self.sb.root / "tests/integration/test_a_first.py"
        a.write_text("import json\n\n" + SERVER_HELPER + "\n\n" + PING_010, encoding="utf-8")
        (self.sb.root / "tests/integration/test_b_misc.py").write_text(
            "import json\n\n\ndef test_roundtrip_through_the_shared_helper_process():\n"
            "    from test_a_first import _SRV\n"
            "    _SRV[0].stdin.write('kim,90;lee,95\\n')\n    _SRV[0].stdin.flush()\n"
            "    assert json.loads(_SRV[0].stdout.readline())['top'] == 'lee'\n", encoding="utf-8")
        replace_function(self.itest, "test_TEST_010_report_uses_real_parser", None)
        replace_function(self.itest, "test_TEST_011_parser_error_reaches_report", MOCKED_011)
        r4, r5, r6 = self.to_g6(self.declare({"IF-001": [("TEST-010", "subprocess", "tests/integration/test_a_first.py")]}),
                                changed=(INTEGRATION, "tests/integration/test_a_first.py",
                                         "tests/integration/test_b_misc.py"))
        rec = ledger_record(self.sb, r6["record_id"]) if r6.get("record_id") else {}
        if1 = [i for i in rec.get("interfaces") or [] if i["id"] == "IF-001"]
        self.assertFalse(if1 and "TEST-010" in if1[0]["covered_by"],
                         f"{RED} another test's work credited to TEST-010 (ping only)")
        self.assertEqual(r6.get("status"), "BLOCKED", r6)


class R5FixtureRed(R5Base):
    def test_N7_autouse_fixture_connection_makes_mocked_tests_test_level(self):
        """Owner case B: both IF-001 test bodies mock the parser; a conftest autouse fixture calls the consumer once
        in setup (the review-1 F6 / review-3 R1 shape)."""
        (self.sb.root / "tests/integration/conftest.py").write_text(
            "import pytest\n\nfrom pipeline import report\n\n\n@pytest.fixture(autouse=True)\ndef warm_up():\n"
            "    report.summarize('a,1')\n    yield\n", encoding="utf-8")
        replace_function(self.itest, "test_TEST_010_report_uses_real_parser",
                         "def test_TEST_010_report_uses_real_parser(monkeypatch):\n"
                         "    monkeypatch.setattr('pipeline.report.parse', lambda text: [{'name': 'x', 'score': 1}])\n"
                         "    assert summarize('ignored')['top'] == 'x'\n")
        replace_function(self.itest, "test_TEST_011_parser_error_reaches_report", MOCKED_011)
        r4, r5, r6 = self.to_g6(changed=(INTEGRATION, "tests/integration/conftest.py"))
        self.assertEqual(r6.get("status"), "BLOCKED", f"{RED} every IF-001 test body mocks the provider: {r6}")


class R5AsyncGenChar(R5Base):
    """Not fixed (documented limitation, DECISIONS D44): the consumer's call is not on the provider's stack when the
    provider runs as a gathered asyncio task or as a generator the test iterates, so these legitimate tests are
    BLOCKED (insufficient evidence), never PASSED by mistake. Same result on 464d01b."""
    PARSER_ADD = ("\n\nasync def parse_async(text: str) -> list[dict]:\n    return parse(text)\n\n\n"
                  "def iter_records(text: str):\n    yield from parse(text)\n")

    def add_code(self, report_add: str) -> None:
        pp = self.sb.root / "src/pipeline/parser.py"
        pp.write_text(pp.read_text(encoding="utf-8") + self.PARSER_ADD, encoding="utf-8")
        rp = self.sb.root / "src/pipeline/report.py"
        rp.write_text(rp.read_text(encoding="utf-8").replace(
            "from pipeline.parser import parse\n",
            "from pipeline.parser import iter_records, parse, parse_async\n", 1).replace(
            "\n\ndef main(", report_add + "\n\ndef main(", 1), encoding="utf-8")

    def test_N4_asyncio_gather_consumer(self):
        self.add_code("\n\nasync def summarize_async(text: str) -> dict:\n"
                      "    import asyncio\n"
                      "    records = (await asyncio.gather(parse_async(text)))[0]\n"
                      "    top = max(records, key=lambda r: (r['score'], r['name']))\n"
                      "    return {'count': len(records), 'top': top['name']}\n")
        self.prepend("import asyncio\n\nfrom pipeline.report import summarize_async\n")
        replace_function(self.itest, "test_TEST_010_report_uses_real_parser",
                         "def test_TEST_010_report_uses_real_parser():\n"
                         "    assert asyncio.run(summarize_async('kim,90\\nlee,95\\n'))['top'] == 'lee'\n")
        replace_function(self.itest, "test_TEST_011_parser_error_reaches_report",
                         "def test_TEST_011_parser_error_reaches_report():\n"
                         "    with pytest.raises(ValueError):\n        asyncio.run(summarize_async('kim,ninety'))\n")
        r4, r5, r6 = self.to_g6()
        self.assertEqual((r6.get("status"), r6.get("blocked_reason")), ("BLOCKED", "integration_evidence_insufficient"), r6)

    def test_N5_consumer_returning_a_provider_generator(self):
        self.add_code("\n\ndef records(text: str):\n    return iter_records(text)\n")
        self.prepend("from pipeline.report import records\n")
        replace_function(self.itest, "test_TEST_010_report_uses_real_parser",
                         "def test_TEST_010_report_uses_real_parser():\n"
                         "    assert [r['name'] for r in records('kim,90\\nlee,95\\n')] == ['kim', 'lee']\n")
        replace_function(self.itest, "test_TEST_011_parser_error_reaches_report",
                         "def test_TEST_011_parser_error_reaches_report():\n"
                         "    with pytest.raises(ValueError):\n        list(records('kim,ninety'))\n")
        r4, r5, r6 = self.to_g6()
        self.assertEqual((r6.get("status"), r6.get("blocked_reason")), ("BLOCKED", "integration_evidence_insufficient"), r6)


PARSER_CLASS = '''"""Score record parser (DESIGN-001, provider of IF-001), class form."""


class Parser:
    def __init__(self, sep: str = ","):
        self.sep = sep

    def parse(self, text: str) -> list[dict]:
        if not isinstance(text, str):
            raise TypeError("text must be str")
        records = []
        for no, line in enumerate(text.splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            name, sep, score = line.partition(self.sep)
            if not sep or not name.strip():
                raise ValueError(f"line {no}: expected 'name,score'")
            try:
                value = int(score)
            except ValueError:
                raise ValueError(f"line {no}: score must be an integer") from None
            records.append({"name": name.strip(), "score": value})
        return records
'''
UNIT_PARSER_CLASS = '''import pytest

from pipeline.parser import Parser


def test_TEST_001_parse_records():
    assert Parser().parse("kim,90\\nlee,85\\n") == [{"name": "kim", "score": 90}, {"name": "lee", "score": 85}]


def test_TEST_002_parse_rejects_malformed_line():
    with pytest.raises(ValueError):
        Parser().parse("kim;90")


def test_TEST_003_parse_empty_text():
    assert Parser().parse("") == []
'''


class ClassProviderBase(R5Base):
    """Class-based provider: IF-001's signature is set by the subclass; G1-G5 PASSED with that architecture."""
    upto = "G1"
    signature = ""

    @classmethod
    def build(cls, sb):
        super().build(sb)
        sb.prepare("G2")
        arch = sb.load("architecture.json")
        arch["interfaces"][0]["signature"] = cls.signature
        sb.save("architecture.json", arch)
        sb.review("G2")
        assert sb.gate("G2")[1]["status"] == "PASSED"
        sb.prepare("G3")
        design = sb.load("design.json")
        for u in design["units"]:
            if u["id"] == "DESIGN-001":
                u.update(name="Parser", kind="class", signature="class Parser")
        sb.save("design.json", design)
        sb.review("G3")
        r3 = sb.gate("G3")[1]
        assert r3["status"] == "PASSED", json.dumps(r3, ensure_ascii=False)[:3000]
        sb.prepare("G4")
        (sb.root / "src/pipeline/parser.py").write_text(PARSER_CLASS, encoding="utf-8")
        rp = sb.root / "src/pipeline/report.py"
        rp.write_text(rp.read_text(encoding="utf-8").replace(
            "from pipeline.parser import parse\n", "from pipeline.parser import Parser\n").replace(
            "    records = parse(text)\n", "    records = Parser().parse(text)\n"), encoding="utf-8")
        (sb.root / "tests/unit/test_parser.py").write_text(UNIT_PARSER_CLASS, encoding="utf-8")
        sb.review("G4")
        r4 = sb.gate("G4")[1]
        assert r4["status"] == "PASSED", json.dumps(r4, ensure_ascii=False)[:3000]
        r5 = sb.gate("G5")[1]
        assert r5["status"] == "PASSED", json.dumps(r5, ensure_ascii=False)[:3000]


class R5MethodSignatureRed(ClassProviderBase):
    signature = "def parse(self, text: str) -> list[dict]"

    def test_N2_method_signature_accepted_by_g4_never_matches_at_g6(self):
        r6 = self.sb.gate("G6")[1]
        self.assertEqual(r6.get("status"), "PASSED", f"{RED} unchanged real integration tests, class-based provider: {r6}")


class R5ClassSignatureRed(ClassProviderBase):
    signature = "class Parser"

    def test_N3_constructor_call_is_taken_as_the_interface_while_parse_is_mocked(self):
        for name in ("test_TEST_010_report_uses_real_parser", "test_TEST_011_parser_error_reaches_report"):
            replace_function(self.itest, name,
                             f"def {name}(monkeypatch):\n"
                             "    from pipeline.parser import Parser\n"
                             "    monkeypatch.setattr(Parser, 'parse', lambda self, text: [{'name': 'z', 'score': 1}])\n"
                             "    assert summarize('kim,90')['top'] == 'z'\n")
        r4, r5, r6 = self.to_g6()
        self.assertEqual(r6.get("status"), "BLOCKED", f"{RED} Parser.parse is mocked in every IF-001 test: {r6}")


class R5UnitRed(unittest.TestCase):
    """Validator internals driven directly."""

    def gates(self):
        import importlib
        import sys
        from helpers import PLUGIN
        sys.path.insert(0, str(PLUGIN / "validator"))
        try:
            for m in [m for m in sys.modules if m == "vmodel_validator" or m.startswith("vmodel_validator.")]:
                del sys.modules[m]
            return importlib.import_module("vmodel_validator.gates")
        finally:
            sys.path.remove(str(PLUGIN / "validator"))

    def test_N8_equal_timestamps_with_a_coarse_clock(self):
        """Windows CPython <= 3.12: time.time() ticks every ~15.6 ms, so a child's line and the pytest process's next
        boundary often carry the same ts. Same tick as the next test's boundary -> detached (work lost); same tick as
        the call boundary while still in setup -> call (setup work credited)."""
        import tempfile
        from pathlib import Path
        gates = self.gates()
        d = Path(tempfile.mkdtemp())
        a, b = "tests/integration/test_pipeline.py::test_TEST_012_x", "tests/integration/test_pipeline.py::test_zz"
        tick = 1000.0
        (d / "1-p.jsonl").write_text("\n".join(json.dumps(x) for x in [
            {"v": 2, "method": "sys.monitoring", "spawned_in": None},
            {"b": a, "p": "setup", "ts": tick}, {"b": a, "p": "call", "ts": tick + 0.015625},
            {"b": b, "p": "call", "ts": tick + 0.03125}]) + "\n", encoding="utf-8")
        (d / "2-c.jsonl").write_text("\n".join(json.dumps(x) for x in [
            {"v": 2, "method": "sys.monitoring", "spawned_in": [a, "setup"]},
            {"t": a, "p": "setup", "m": "src/pipeline/report.py", "f": "warm_up", "ts": tick + 0.015625},
            {"t": a, "p": "setup", "m": "src/pipeline/report.py", "f": "main", "ts": tick + 0.03125}]) + "\n",
            encoding="utf-8")
        rt = gates.read_runtime_trace(d)
        # conservative: same tick as the call start is not yet the call, same tick as the next test is not this test
        self.assertEqual([(e[4], e[1]) for e in rt["_events"]], [("warm_up", "setup"), ("main", "detached")], RED)



class R5PerfChar(R5UnitRed):
    """Review 5 measured _test_windows at 1.4 s for 8000 tests: acceptable, kept as a guard."""

    def test_N8_equal_timestamps_with_a_coarse_clock(self):  # not repeated here
        pass

    def test_N6_test_windows_is_quadratic(self):
        gates = self.gates()
        out = {}
        for n in (2000, 4000, 8000):
            seq = []
            ts = 1.0
            for i in range(n):
                for ph in ("setup", "call", "teardown"):
                    seq.append((ts, f"tests/integration/test_x.py::test_{i}", ph))
                    ts += 0.001
            t0 = time.perf_counter()
            gates._test_windows({"p.jsonl": seq})
            out[n] = round(time.perf_counter() - t0, 2)
        self.assertLess(out[8000], 5.0, out)


class R5TracerAccept(unittest.TestCase):
    """The tracer's anchors and the pytest plugin's boundaries on their own (new core only)."""

    def setUp(self):
        import tempfile
        from pathlib import Path
        from helpers import PLUGIN
        self.tracer = PLUGIN / "validator" / "vmodel_validator" / "tracer"
        self.tmp = Path(tempfile.mkdtemp(prefix="vmodel-anchor-")) / "앵커 추적"
        self.tmp.mkdir()
        (self.tmp / "prov.py").write_text("def f(x=1):\n    return x\n", encoding="utf-8")
        (self.tmp / "cons.py").write_text("import threading\n\nimport prov\n\n\ndef use():\n    return prov.f()\n\n\n"
                                          "def spawn():\n    t = threading.Thread(target=use)\n    t.start()\n    t.join()\n",
                                          encoding="utf-8")
        (self.tmp / "test_file.py").write_text(
            "import cons\n\n\ndef warm_up():\n    cons.use()\n\n\ndef test_TEST_001_a():\n    cons.use()\n\n\n"
            "def test_TEST_002_b():\n    cons.spawn()\n", encoding="utf-8")
        self.out = self.tmp / "trace"
        self.out.mkdir()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp.parent, ignore_errors=True)

    def run_py(self, argv: list[str], test_id: str | None, plugins: bool = False):
        import os
        import subprocess
        import sys
        spec = self.tmp / "spec.json"
        spec.write_text(json.dumps({"out": str(self.out), "watch": {str(self.tmp / n): n for n in
                                                                   ("prov.py", "cons.py", "test_file.py")},
                                    "providers": {"prov.py": ["cons.py"]}, "tests": ["test_file.py"]}),
                        encoding="utf-8")
        env = {k: v for k, v in os.environ.items() if not k.startswith(("PYTHON", "PYTEST", "VMODEL"))}
        env.update({"PYTHONPATH": os.pathsep.join([str(self.tracer), str(self.tmp)]), "VMODEL_TRACE_SPEC": str(spec)})
        if test_id:
            env["PYTEST_CURRENT_TEST"] = test_id
        if plugins:
            env.update({"PYTEST_PLUGINS": "vmodel_trace_plugin", "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"})
        return subprocess.run([sys.executable, *argv], cwd=str(self.tmp), env=env, capture_output=True, text=True,
                              timeout=120)

    def lines(self) -> list[dict]:
        out = []
        for f in sorted(self.out.glob("*.jsonl")):
            out += [json.loads(x) for x in f.read_text(encoding="utf-8").splitlines()[1:]]
        for r in out:
            r.pop("ts", None)
        return out

    def test_anchor_is_the_outermost_test_file_function(self):
        res = self.run_py(["-c", "import os, test_file\ntest_file.warm_up()\ntest_file.test_TEST_001_a()\n"
                                 "os.environ['PYTEST_CURRENT_TEST'] = 'test_file.py::test_TEST_002_b (call)'\n"
                                 "test_file.test_TEST_002_b()\n"], "test_file.py::test_TEST_001_a (call)")
        self.assertEqual(res.returncode, 0, res.stderr)
        edges = sorted((r["a"], r["c"]) for r in self.lines() if "c" in r)
        # the thread started inside test_TEST_002_b inherits that anchor (its own stack has no test-file frame)
        self.assertEqual(edges, [("test_TEST_001_a", "cons.py"), ("test_TEST_002_b", "cons.py"),
                                 ("warm_up", "cons.py")], RED)

    def test_pytest_plugin_writes_phase_boundaries(self):
        res = self.run_py(["-m", "pytest", "-q", "-p", "no:cacheprovider", "test_file.py"], None, plugins=True)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        b = [(r["b"].split("::")[-1], r["p"]) for r in self.lines() if "b" in r]
        self.assertEqual(b, [(t, p) for t in ("test_TEST_001_a", "test_TEST_002_b")
                             for p in ("setup", "call", "teardown", "end")], RED)
        # inside pytest the anchor is the test function itself
        self.assertIn(("test_file.py::test_TEST_001_a", "call", "test_TEST_001_a"),
                      [(r["t"], r["p"], r["a"]) for r in self.lines() if "c" in r])


if __name__ == "__main__":
    unittest.main()

"""Sixth independent review (e8a5a7e, 2026-11-10 final verification): findings as tests first.

RED target: git archive e8a5a7e plugins/vmodel. M1..M7 follow the review report (adapted from the reviewer's
reproduction file: RED markers, no prints). M3 (a conftest pytest_pyfunc_call hook) is not a finding: G4.TEST_INTEGRITY
already rejects such a conftest. M5/M6 (a coarse wall clock) are covered by a unit test on the monotonic clock.
"""
from __future__ import annotations

import importlib
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from g6_base import RED, replace_function
from helpers import PLUGIN
from test_g6_review5 import INTEGRATION, UNIT_PARSER_CLASS, R5Base

PARSER_CLASS_COMPILE = '''"""Score record parser (DESIGN-001, provider of IF-001), class form; the constructor prepares itself."""


class Parser:
    def __init__(self, sep: str = ","):
        self.sep = sep
        self._compile()

    def _compile(self) -> None:
        self.width = len(self.sep)

    def parse(self, text: str) -> list[dict]:
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



class R6ClassCtorHelperRed(R5Base):
    """IF-001 signature 'class Parser'; Parser.__init__ calls a plain helper method (self._compile())."""
    upto = "G1"

    @classmethod
    def build(cls, sb):
        super().build(sb)
        sb.prepare("G2")
        arch = sb.load("architecture.json")
        arch["interfaces"][0]["signature"] = "class Parser"
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
        assert sb.gate("G3")[1]["status"] == "PASSED"
        sb.prepare("G4")
        (sb.root / "src/pipeline/parser.py").write_text(PARSER_CLASS_COMPILE, encoding="utf-8")
        rp = sb.root / "src/pipeline/report.py"
        rp.write_text(rp.read_text(encoding="utf-8").replace(
            "from pipeline.parser import parse\n", "from pipeline.parser import Parser\n").replace(
            "    records = parse(text)\n", "    records = Parser().parse(text)\n"), encoding="utf-8")
        (sb.root / "tests/unit/test_parser.py").write_text(UNIT_PARSER_CLASS, encoding="utf-8")
        sb.review("G4")
        assert sb.gate("G4")[1]["status"] == "PASSED"
        assert sb.gate("G5")[1]["status"] == "PASSED"

    def test_M1_constructor_helper_counts_while_parse_is_mocked(self):
        for name in ("test_TEST_010_report_uses_real_parser", "test_TEST_011_parser_error_reaches_report"):
            replace_function(self.itest, name,
                             f"def {name}(monkeypatch):\n"
                             "    from pipeline.parser import Parser\n"
                             "    monkeypatch.setattr(Parser, 'parse', lambda self, text: [{'name': 'z', 'score': 1}])\n"
                             "    assert summarize('kim,90')['top'] == 'z'\n")
        r4, r5, r6 = self.to_g6()
        self.assertEqual(r6.get("status"), "BLOCKED", f"{RED} Parser.parse is mocked in every IF-001 test: {r6}")



DECORATOR = ("import functools\n\n\ndef _logged(fn):\n    @functools.wraps(fn)\n    def wrapper(*args, **kwargs):\n"
             "        return fn(*args, **kwargs)\n    return wrapper\n")



class R6AnchorRed(R5Base):
    def test_M2_decorator_defined_in_the_test_file(self):
        self.prepend(DECORATOR)
        body = self.itest.read_text(encoding="utf-8")
        for name in ("test_TEST_010", "test_TEST_011", "test_TEST_012"):
            body = body.replace(f"\ndef {name}", f"\n@_logged\ndef {name}", 1)
        self.itest.write_text(body, encoding="utf-8")
        r4, r5, r6 = self.to_g6()
        self.assertEqual(r6.get("status"), "PASSED", f"{RED} unchanged real tests behind a pass-through decorator: {r6}")


class R6PluginRed(R5Base):
    def test_M4_nested_pytest_with_its_own_pythonpath_breaks_under_g6(self):
        """TEST-012 also runs pytest in a subprocess with PYTHONPATH set to src only (testing a CLI / plugin)."""
        replace_function(self.itest, "test_TEST_012_cli_main_reads_file",
                         "def test_TEST_012_cli_main_reads_file(tmp_path, capsys):\n"
                         "    import os, subprocess, sys\n    from pathlib import Path\n"
                         "    f = tmp_path / 'scores.csv'\n    f.write_text('a,1\\nb,2\\n', encoding='utf-8')\n"
                         "    assert main([str(f)]) == 0\n"
                         "    assert json.loads(capsys.readouterr().out) == {'count': 2, 'total': 3, 'top': 'b'}\n"
                         "    inner = tmp_path / 'test_inner.py'\n"
                         "    inner.write_text('def test_ok():\\n    assert True\\n', encoding='utf-8')\n"
                         "    env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[2] / 'src'))\n"
                         "    r = subprocess.run([sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider', str(inner)],\n"
                         "                       cwd=str(tmp_path), env=env, capture_output=True, text=True)\n"
                         "    assert r.returncode == 0, r.stdout[-600:] + r.stderr[-600:]\n")
        r4, r5, r6 = self.to_g6()
        self.assertEqual(r6.get("status"), "PASSED", f"{RED} the tracer's PYTEST_PLUGINS leaks into a nested pytest: {r6}")




class R6RequestedFixtureRed(R5Base):
    def test_M7_requested_fixture_runs_the_connection_body_mocks_it(self):
        (self.sb.root / "tests/integration/conftest.py").write_text(
            "import pytest\n\nfrom pipeline import report\n\n\n@pytest.fixture\ndef seeded():\n"
            "    return report.summarize('a,1')\n", encoding="utf-8")
        replace_function(self.itest, "test_TEST_010_report_uses_real_parser",
                         "def test_TEST_010_report_uses_real_parser(seeded, monkeypatch):\n"
                         "    monkeypatch.setattr('pipeline.report.parse', lambda text: [{'name': 'x', 'score': 1}])\n"
                         "    assert summarize('ignored')['top'] == 'x'\n")
        replace_function(self.itest, "test_TEST_011_parser_error_reaches_report",
                         "def test_TEST_011_parser_error_reaches_report(seeded, monkeypatch):\n"
                         "    monkeypatch.setattr('pipeline.report.parse', lambda text: [{'name': 'x', 'score': 1}])\n"
                         "    assert summarize('kim,ninety')['count'] == 1\n")
        r4, r5, r6 = self.to_g6(changed=(INTEGRATION, "tests/integration/conftest.py"))
        # decision (D44, review 6 M5): a connection run only by a requested fixture does not count when the test
        # function itself patches the provider (G4 found the patch)
        self.assertEqual(r6.get("status"), "BLOCKED", f"{RED} both test bodies mock the provider: {r6}")


class R6ClockRed(unittest.TestCase):
    """Review 6 M5/M6: with a coarse wall clock (Windows CPython <= 3.12 ticks every ~15.6 ms) child lines fall on the
    same tick as the boundaries and are never credited; the monotonic high-resolution clock ("tc") decides instead."""

    def gates(self):
        sys.path.insert(0, str(PLUGIN / "validator"))
        try:
            for m in [m for m in sys.modules if m == "vmodel_validator" or m.startswith("vmodel_validator.")]:
                del sys.modules[m]
            return importlib.import_module("vmodel_validator.gates")
        finally:
            sys.path.remove(str(PLUGIN / "validator"))

    def test_monotonic_clock_decides_when_the_wall_clock_ties(self):
        gates = self.gates()
        d = Path(tempfile.mkdtemp(prefix="vmodel-clock-"))
        try:
            a = "tests/integration/test_pipeline.py::test_TEST_012_x"
            tick = 1000.0
            (d / "1-p.jsonl").write_text("\n".join(json.dumps(x) for x in [
                {"v": 2, "method": "sys.monitoring", "spawned_in": None},
                {"b": a, "p": "setup", "ts": tick, "tc": 100}, {"b": a, "p": "call", "ts": tick, "tc": 200},
                {"b": a, "p": "teardown", "ts": tick, "tc": 400}, {"b": a, "p": "end", "ts": tick, "tc": 500}]) + "\n",
                encoding="utf-8")
            (d / "2-c.jsonl").write_text("\n".join(json.dumps(x) for x in [
                {"v": 2, "method": "sys.monitoring", "spawned_in": [a, "setup"]},
                {"t": a, "p": "setup", "m": "src/pipeline/report.py", "f": "main", "ts": tick, "tc": 300}]) + "\n",
                encoding="utf-8")
            rt = gates.read_runtime_trace(d)
            self.assertEqual([(e[4], e[1]) for e in rt["_events"]], [("main", "call")], RED)
        finally:
            shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()

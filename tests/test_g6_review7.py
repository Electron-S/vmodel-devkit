"""Seventh independent review (ce59c33, 2026-11-10 final verification): findings as tests first.

RED target: git archive ce59c33 plugins/vmodel. R1..R4 follow the review report (adapted from the reviewer's file).
R2 (a fixture server warmed up in setup) is not fixed: the child's first line per function carries the spawn phase,
later calls are not re-recorded, so the test stays BLOCKED (conservative, documented); characterised here.
R3 needs a Python with pytest-xdist: VMODEL_R7_XDIST_PYTHON=<python> (skipped otherwise).
R4 is decided the conservative way (Case B): a test function that patches the provider is not test-level evidence.
"""
from __future__ import annotations

import json
import os
import unittest

from g6_base import RED, file_sha256, replace_function
from test_g6_review5 import UNIT_PARSER_CLASS, R5Base

SERVER_MAIN = ("import sys\nfrom pipeline.report import main\nfor line in sys.stdin:\n    main([line.strip()])\n"
               "    sys.stdout.flush()\n")


def server_fixture(warm_up: bool) -> str:
    return ("SERVER_CODE = " + json.dumps(SERVER_MAIN) + "\n\n\n"
            "@pytest.fixture\ndef server(tmp_path):\n"
            "    import os\n    import subprocess\n    import sys\n    from pathlib import Path\n"
            "    env = dict(os.environ)\n"
            "    src = str(Path(__file__).resolve().parents[2] / 'src')\n"
            "    env['PYTHONPATH'] = os.pathsep.join(p for p in (src, env.get('PYTHONPATH')) if p)\n"
            "    proc = subprocess.Popen([sys.executable, '-u', '-c', SERVER_CODE], stdin=subprocess.PIPE,\n"
            "                            stdout=subprocess.PIPE, env=env, text=True)\n"
            + ("    w = tmp_path / 'warm.csv'\n    w.write_text('w,1\\n', encoding='utf-8')\n"
               "    proc.stdin.write(str(w) + '\\n')\n    proc.stdin.flush()\n"
               "    assert json.loads(proc.stdout.readline())['count'] == 1  # server ready\n" if warm_up else "")
            + "    yield proc\n    proc.stdin.close()\n    proc.wait(timeout=30)\n")


TEST_012_SERVER = ("def test_TEST_012_cli_main_reads_file(server, tmp_path):\n"
                   "    f = tmp_path / 'scores.csv'\n    f.write_text('a,1\\nb,2\\n', encoding='utf-8')\n"
                   "    server.stdin.write(str(f) + '\\n')\n    server.stdin.flush()\n"
                   "    assert json.loads(server.stdout.readline()) == {'count': 2, 'total': 3, 'top': 'b'}\n")


class Base(R5Base):
    def declare_012(self) -> list[dict]:
        entries = self.sb.interface_review_entries()
        for e in entries:
            if e["id"] == "IF-002":
                e["runtime_paths"] = [{"test": "TEST-012", "kind": "subprocess",
                                       "test_file_sha256": file_sha256(self.itest)}]
        return entries

    def server_scenario(self, warm_up: bool) -> None:
        self.prepend(server_fixture(warm_up))
        replace_function(self.itest, "test_TEST_012_cli_main_reads_file", TEST_012_SERVER)


class R7ProviderDecoratorRed(Base):
    def test_R1_decorator_defined_in_the_provider_module(self):
        pp = self.sb.root / "src/pipeline/parser.py"
        pp.write_text(pp.read_text(encoding="utf-8").replace(
            '"""Score record parser (DESIGN-001, provider of IF-001)."""\n',
            '"""Score record parser (DESIGN-001, provider of IF-001)."""\nimport functools\n\n\n'
            "def _checked(fn):\n    @functools.wraps(fn)\n    def wrapper(text):\n"
            "        if not isinstance(text, str):\n            raise TypeError('text must be str')\n"
            "        return fn(text)\n    return wrapper\n\n\n@_checked", 1), encoding="utf-8")
        r4, r5, r6 = self.to_g6()
        self.assertEqual(r6.get("status"), "PASSED", f"{RED} unchanged real tests; parse is wrapped by a module decorator: {r6}")


class R7WarmUpChar(Base):
    """R2 not fixed (documented limitation): same result on ce59c33."""
    def test_R2_fixture_server_warmed_up_in_setup(self):
        """The project's S10 shape plus one readiness request in the fixture before yield."""
        self.server_scenario(warm_up=True)
        r4, r5, r6 = self.to_g6(self.declare_012())
        self.assertEqual((r6.get("status"), r6.get("blocked_reason")), ("BLOCKED", "integration_evidence_insufficient"), r6)

    def test_R2_control_without_warm_up(self):
        self.server_scenario(warm_up=False)
        r4, r5, r6 = self.to_g6(self.declare_012())
        self.assertEqual(r6.get("status"), "PASSED")


@unittest.skipUnless(os.environ.get("VMODEL_R7_XDIST_PYTHON"), "needs VMODEL_R7_XDIST_PYTHON with pytest-xdist")
class R7XdistRed(Base):
    def test_R3_xdist_workers_get_no_boundaries(self):
        cfg = self.sb.config()
        cfg["integration_test"] = {"argv": [os.environ["VMODEL_R7_XDIST_PYTHON"], "-m", "pytest", "-q", "-p",
                                            "no:cacheprovider", "-n", "2", "tests/integration", "--junitxml={junit}"],
                                   "timeout_s": 300, "plugin_autoload": True}
        self.sb.set_config(cfg)
        self.server_scenario(warm_up=False)
        r4, r5, r6 = self.to_g6(self.declare_012())
        self.assertEqual(r6.get("status"), "PASSED", f"{RED} same tests pass without -n: {r6}")


from test_g6_review6 import PARSER_CLASS_COMPILE  # noqa: E402

PARSER_FACTORY = PARSER_CLASS_COMPILE.replace(
    "    def _compile(self) -> None:", "    @classmethod\n    def create(cls) -> \"Parser\":\n        return cls()\n\n    def _compile(self) -> None:")


class R7FactoryRed(Base):
    """IF-001 signature 'class Parser'; the consumer builds it through a factory classmethod."""
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
        (sb.root / "src/pipeline/parser.py").write_text(PARSER_FACTORY, encoding="utf-8")
        rp = sb.root / "src/pipeline/report.py"
        rp.write_text(rp.read_text(encoding="utf-8").replace(
            "from pipeline.parser import parse\n", "from pipeline.parser import Parser\n").replace(
            "    records = parse(text)\n", "    records = Parser.create().parse(text)\n"), encoding="utf-8")
        (sb.root / "tests/unit/test_parser.py").write_text(UNIT_PARSER_CLASS, encoding="utf-8")
        sb.review("G4")
        assert sb.gate("G4")[1]["status"] == "PASSED"
        assert sb.gate("G5")[1]["status"] == "PASSED"

    def test_R4_factory_classmethod_counts_while_parse_is_mocked(self):
        for name in ("test_TEST_010_report_uses_real_parser", "test_TEST_011_parser_error_reaches_report"):
            replace_function(self.itest, name,
                             f"def {name}(monkeypatch):\n"
                             "    from pipeline.parser import Parser\n"
                             "    monkeypatch.setattr(Parser, 'parse', lambda self, text: [{'name': 'z', 'score': 1}])\n"
                             "    assert summarize('kim,90')['top'] == 'z'\n")
        r4, r5, r6 = self.to_g6()
        # decision (D44, review 7 R4, Case B): a test function that patches the provider is not test-level evidence
        self.assertEqual(r6.get("status"), "BLOCKED", f"{RED} Parser.parse is mocked in every IF-001 test: {r6}")


if __name__ == "__main__":
    unittest.main()

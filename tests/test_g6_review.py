"""Independent review of 3239eba (docs/g6/WORKITEM.md section 7): every accepted finding as a test first.

RED target: the reviewed build (git archive 3239eba plugins/vmodel), not the 0.1.5 release.
Finding numbers (F1..F12) follow the review report.
"""
from __future__ import annotations

import json
import unittest

from g6_base import (RED, SandboxClass, file_sha256, justify_test_change, ledger_record, replace_function)
from helpers import PIPELINE, SINGLE, Sandbox, has_pytest

INTEGRATION = "tests/integration/test_pipeline.py"
PRINT_ONLY_SUBPROCESS = ("def test_TEST_012_cli_main_reads_file():\n"
                         "    import subprocess\n"
                         "    import sys\n"
                         "    res = subprocess.run([sys.executable, '-c', 'print(1)'], capture_output=True, check=True)\n"
                         "    assert res.stdout.strip() == b'1'\n")


class ReviewWiringBase(SandboxClass):
    """pipeline, split commands, G1-G3 PASSED, code in place (G4 not evaluated)."""
    upto = "G3"

    @classmethod
    def build(cls, sb):
        super().build(sb)
        sb.put_code()

    @property
    def itest(self):
        return self.sb.root / INTEGRATION

    def wiring(self) -> dict:
        code, out = self.sb.vm("wiring", "WI-001", "--json")
        self.assertEqual(code, 0, out)
        return json.loads(out)

    def path(self, iid: str, tid: str) -> str:
        return self.wiring()["interfaces"][iid]["tests"][tid]["path"]

    def g4(self, **review) -> dict:
        self.sb.review("G4", **review)
        return self.sb.gate("G4")[1]


class ReviewWiringRed(ReviewWiringBase):
    # F2: reference-only and shadowed names are not calls into the interface
    def test_F2_module_attribute_reference_is_not_a_call(self):
        replace_function(self.itest, "test_TEST_010_report_uses_real_parser",
                         "def test_TEST_010_report_uses_real_parser():\n"
                         "    from pipeline import report\n"
                         "    assert report.__name__.endswith('report')\n")
        self.assertNotEqual(self.path("IF-001", "TEST-010"), "static", f"{RED} __name__.endswith is not a call path")
        self.assertEqual(self.g4()["status"], "FAILED")

    def test_F2_nested_def_shadowing_the_import_is_not_the_consumer(self):
        replace_function(self.itest, "test_TEST_010_report_uses_real_parser",
                         "def test_TEST_010_report_uses_real_parser():\n"
                         "    def summarize(text):\n"
                         "        return {'count': 3}\n"
                         "    assert summarize('anything') == {'count': 3}\n")
        self.assertNotEqual(self.path("IF-001", "TEST-010"), "static", f"{RED} a local summarize shadows the import")

    def test_F2_parameter_default_shadowing_the_import(self):
        replace_function(self.itest, "test_TEST_010_report_uses_real_parser",
                         "def test_TEST_010_report_uses_real_parser(summarize=lambda t: {'count': 3}):\n"
                         "    assert summarize('x') == {'count': 3}\n")
        self.assertNotEqual(self.path("IF-001", "TEST-010"), "static", f"{RED} a parameter shadows the import")

    # F3: malformed review entries never crash the validator
    def test_F3_unhashable_interface_id_in_review_is_review_required_not_a_crash(self):
        entries = self.sb.interface_review_entries()
        entries[0]["id"] = ["IF-001"]
        self.sb.review("G4", interfaces=entries)
        code, out = self.sb.vm("gate", "WI-001", "G4", "--json")
        self.assertNotEqual(code, 2, f"{RED} internal error instead of a gate result: {out[-600:]}")
        self.assertEqual(json.loads(out)["status"], "REVIEW_REQUIRED")

    # F7: ordinary test styles reach the interface
    def test_F7_class_based_tests_with_a_helper_method(self):
        self.itest.write_text(
            "import json\n\nimport pytest\n\nfrom pipeline.report import main, summarize\n\n\n"
            "class TestPipeline:\n"
            "    def _summary(self, text):\n        return summarize(text)\n\n"
            "    def test_TEST_010_report_uses_real_parser(self):\n"
            "        assert self._summary('kim,90\\nlee,95\\n')['top'] == 'lee'\n\n"
            "    def test_TEST_011_parser_error_reaches_report(self):\n"
            "        with pytest.raises(ValueError):\n            self._summary('kim,ninety')\n\n"
            "    def test_TEST_012_cli_main_reads_file(self, tmp_path, capsys):\n"
            "        f = tmp_path / 'scores.csv'\n        f.write_text('a,1\\nb,2\\n', encoding='utf-8')\n"
            "        assert main([str(f)]) == 0\n", encoding="utf-8")
        self.assertEqual(self.path("IF-001", "TEST-010"), "static", f"{RED} self._summary calls summarize")
        self.assertEqual(self.g4()["status"], "PASSED")

    def test_F7_unittest_setup_alias_lambda_argument_and_star_import(self):
        self.itest.write_text(
            "import json\nimport unittest\n\nimport pytest\n\nfrom pipeline import report\n"
            "from pipeline.report import *  # noqa: F403\n\n\n"
            "class TestPipeline(unittest.TestCase):\n"
            "    def setUp(self):\n        self.summarize = report.summarize\n\n"
            "    def test_TEST_010_report_uses_real_parser(self):\n"
            "        self.assertEqual(self.summarize('kim,90\\nlee,95\\n')['top'], 'lee')\n\n\n"
            "def test_TEST_011_parser_error_reaches_report():\n"
            "    pytest.raises(ValueError, lambda: report.summarize('kim,ninety'))\n\n\n"
            "def test_TEST_012_cli_main_reads_file(tmp_path, capsys):\n"
            "    f = tmp_path / 'scores.csv'\n    f.write_text('a,1\\nb,2\\n', encoding='utf-8')\n"
            "    assert main([str(f)]) == 0  # noqa: F405\n", encoding="utf-8")
        w = self.wiring()["interfaces"]
        paths = (w["IF-001"]["tests"]["TEST-010"]["path"], w["IF-001"]["tests"]["TEST-011"]["path"],
                 w["IF-002"]["tests"]["TEST-012"]["path"])
        self.assertEqual(paths, ("static", "static", "static"), f"{RED} setUp alias, lambda argument, star import")

    # F8: module names that do not follow the __init__.py rule
    def test_F8_namespace_package_without_init(self):
        (self.sb.root / "src/pipeline/__init__.py").unlink()
        self.assertEqual(self.path("IF-001", "TEST-010"), "static", f"{RED} pipeline.report in a namespace package")
        self.assertEqual(self.g4()["status"], "PASSED")

    # F9: dependency injection: the test hands the provider to the consumer
    def test_F9_provider_passed_into_the_consumer(self):
        (self.sb.root / "src/pipeline/report.py").write_text(
            '"""DI variant: the consumer does not import the provider."""\nimport json\nimport sys\n\n\n'
            "def summarize(text, parse_fn):\n    records = parse_fn(text)\n"
            "    return {'count': len(records), 'total': sum(r['score'] for r in records), 'top': None}\n\n\n"
            "def main(argv=None, parse_fn=None):\n    print(json.dumps(summarize(sys.stdin.read(), parse_fn)))\n"
            "    return 0\n", encoding="utf-8")
        replace_function(self.itest, "test_TEST_010_report_uses_real_parser",
                         "def test_TEST_010_report_uses_real_parser():\n"
                         "    from pipeline.parser import parse\n"
                         "    assert summarize('kim,90\\n', parse_fn=parse)['count'] == 1\n")
        self.assertEqual(self.path("IF-001", "TEST-010"), "static", f"{RED} parse injected into summarize")

    # F10: malformed tests.json does not crash the read-only views
    def test_F10_trace_and_wiring_survive_malformed_verifies(self):
        t = self.sb.load("tests.json")
        for x in t["tests"]:
            if x["id"] == "TEST-010":
                x["verifies"] = 5
        self.sb.save("tests.json", t)
        for cmd in (("trace", "WI-001"), ("wiring", "WI-001"), ("status",)):
            code, out = self.sb.vm(*cmd)
            self.assertNotEqual(code, 2, f"{RED} {cmd}: {out[-400:]}")


class ReviewG6Red(SandboxClass):
    """pipeline, split commands, G1-G5 PASSED."""

    @property
    def itest(self):
        return self.sb.root / INTEGRATION

    def declare_012(self, kind: str = "subprocess") -> list[dict]:
        entries = self.sb.interface_review_entries()
        for e in entries:
            if e["id"] == "IF-002":
                e["runtime_paths"] = [{"test": "TEST-012", "kind": kind, "test_file_sha256": file_sha256(self.itest)}]
        return entries

    def to_g6(self, interfaces: list | None = None) -> tuple[dict, dict, int | None, dict | None]:
        justify_test_change(self.sb, INTEGRATION)
        self.sb.review("G4", interfaces=interfaces)
        r4 = self.sb.gate("G4")[1]
        r5 = self.sb.gate("G5")[1] if r4["status"] == "PASSED" else {}
        if r5.get("status") != "PASSED":
            return r4, r5, None, None
        code, out = self.sb.vm("gate", "WI-001", "G6", "--json")
        try:
            return r4, r5, code, json.loads(out)
        except json.JSONDecodeError:
            return r4, r5, code, {"raw": out[-800:]}

    # F1: credit only from an analysed test function that actually ran
    def test_F1_uncollected_static_function_does_not_cover_the_interface(self):
        (self.sb.root / "tests/integration/flows.py").write_text(
            "from pipeline.report import main\n\n\n"
            "def test_TEST_012_cli_main_reads_file_flow(tmp_path):\n"
            "    f = tmp_path / 's.csv'\n    f.write_text('a,1\\n', encoding='utf-8')\n"
            "    assert main([str(f)]) == 0\n", encoding="utf-8")
        replace_function(self.itest, "test_TEST_012_cli_main_reads_file", PRINT_ONLY_SUBPROCESS)
        r4, r5, code, r6 = self.to_g6(self.declare_012())
        self.assertEqual((r4["status"], r5.get("status")), ("PASSED", "PASSED"), r4)
        self.assertNotEqual(r6["status"], "PASSED", f"{RED} flows.py never runs and the collected test proves nothing")

    def test_F1_collected_function_without_a_call_path_fails_g4(self):
        (self.sb.root / "tests/integration/flows.py").write_text(
            "from pipeline.report import main\n\n\n"
            "def test_TEST_012_cli_main_reads_file_flow(tmp_path):\n"
            "    f = tmp_path / 's.csv'\n    f.write_text('a,1\\n', encoding='utf-8')\n"
            "    assert main([str(f)]) == 0\n", encoding="utf-8")
        replace_function(self.itest, "test_TEST_012_cli_main_reads_file",
                         "def test_TEST_012_cli_main_reads_file():\n    assert len('x') == 1\n")
        r4, r5, code, r6 = self.to_g6()
        self.assertEqual(r4["status"], "FAILED", f"{RED} every function carrying TEST-012 must reach IF-002: {r4}")

    def test_F1_dunder_test_false_and_smoke_function(self):
        replace_function(self.itest, "test_TEST_012_cli_main_reads_file",
                         "def test_TEST_012_cli_main_reads_file(tmp_path, capsys):\n"
                         "    f = tmp_path / 'scores.csv'\n    f.write_text('a,1\\nb,2\\n', encoding='utf-8')\n"
                         "    assert main([str(f)]) == 0\n\n\n"
                         "test_TEST_012_cli_main_reads_file.__test__ = False\n\n\n"
                         "def test_TEST_012_smoke():\n    assert len('x') == 1\n")
        r4, r5, code, r6 = self.to_g6()
        self.assertEqual(r4["status"], "FAILED", f"{RED} test_TEST_012_smoke has no call path: {r4}")

    # F4: entries the tests plant in the trace or junit location never crash G6
    def test_F4_directory_in_the_trace_folder_is_a_recorded_result(self):
        replace_function(self.itest, "test_TEST_012_cli_main_reads_file",
                         "def test_TEST_012_cli_main_reads_file(tmp_path, capsys):\n"
                         "    import json as j\n    import os\n"
                         "    spec = [v for k, v in os.environ.items() if k.startswith('VMODEL') and k.endswith('_SPEC')][0]\n"
                         "    os.makedirs(os.path.join(j.load(open(spec, encoding='utf-8'))['out'], 'x.jsonl'))\n"
                         "    f = tmp_path / 'scores.csv'\n    f.write_text('a,1\\nb,2\\n', encoding='utf-8')\n"
                         "    assert main([str(f)]) == 0\n")
        r4, r5, code, r6 = self.to_g6()
        self.assertNotEqual(code, 2, f"{RED} internal error instead of a gate result: {r6}")
        self.assertTrue(r6.get("recorded"), r6)

    def test_F4_directory_at_the_junit_path_is_a_recorded_failure(self):
        replace_function(self.itest, "test_TEST_012_cli_main_reads_file",
                         "def test_TEST_012_cli_main_reads_file(tmp_path, capsys):\n"
                         "    import os\n    import sys\n"
                         "    junit = [a.split('=', 1)[1] for a in sys.argv if a.startswith('--junit' + 'xml=')][0]\n"
                         "    os.makedirs(junit)\n"
                         "    f = tmp_path / 'scores.csv'\n    f.write_text('a,1\\nb,2\\n', encoding='utf-8')\n"
                         "    assert main([str(f)]) == 0\n")
        r4, r5, code, r6 = self.to_g6()
        self.assertNotEqual(code, 2, f"{RED} internal error instead of a gate result: {r6}")
        self.assertEqual(r6.get("status"), "FAILED", r6)

    def test_F4_g5_survives_a_directory_at_the_junit_path_too(self):
        """Same shared runner path (pre-existing since 0.1.x, found while fixing F4): a recorded FAILED, not exit 2."""
        unit = self.sb.root / "tests/unit/test_report.py"
        replace_function(unit, "test_TEST_007_main_empty_file",
                         "def test_TEST_007_main_empty_file(tmp_path, capsys):\n"
                         "    import os\n    import sys\n"
                         "    os.makedirs([a.split('=', 1)[1] for a in sys.argv if a.startswith('--junit' + 'xml=')][0])\n"
                         "    f = tmp_path / 'empty.csv'\n    f.write_text('', encoding='utf-8')\n"
                         "    assert main([str(f)]) == 0\n")
        justify_test_change(self.sb, "tests/unit/test_report.py", affected="TEST-007")
        self.sb.review("G4")
        self.assertEqual(self.sb.gate("G4")[1]["status"], "PASSED")
        code, out = self.sb.vm("gate", "WI-001", "G5", "--json")
        self.assertNotEqual(code, 2, f"{RED} internal error instead of a gate result: {out[-600:]}")
        self.assertEqual(json.loads(out)["status"], "FAILED")

    # F6: runtime proof must come from the declared mechanism during the test call
    def test_F6_autouse_fixture_running_the_provider_is_not_subprocess_proof(self):
        (self.sb.root / "tests/integration/conftest.py").write_text(
            "import pytest\n\nfrom pipeline import report\n\n\n"
            "@pytest.fixture(autouse=True)\ndef warm_up():\n    report.summarize('a,1')\n    yield\n", encoding="utf-8")
        replace_function(self.itest, "test_TEST_012_cli_main_reads_file", PRINT_ONLY_SUBPROCESS)
        r4, r5, code, r6 = self.to_g6(self.declare_012())
        self.assertEqual((r4["status"], r5.get("status")), ("PASSED", "PASSED"), r4)
        self.assertEqual((r6["status"], r6.get("blocked_reason")), ("BLOCKED", "integration_evidence_insufficient"),
                         f"{RED} the provider ran in fixture setup of the pytest process, not in the subprocess: {r6}")
        rec = ledger_record(self.sb, r6["record_id"])
        self.assertFalse([i for i in rec["interfaces"] if i["id"] == "IF-002"][0]["covered"])


class ReviewG6Char(SandboxClass):
    """D43: behaviour the reviewed build and this one share (pipeline, split commands, G1-G5 PASSED)."""
    itest = ReviewG6Red.itest
    to_g6 = ReviewG6Red.to_g6

    # F2 (G6 side): moved. D43 made it "PASSED with a warning per mocked test" (the parser ran in TEST-012); D44 (final
    # verification, 2026-11-09) does not count suite-level evidence, so both mocked IF-001 tests leave IF-001 unverified
    # (BLOCKED). That expectation fails on this module's RED target 3239eba too, so it is no longer a characterisation:
    # it lives in test_g6_evidence.EvidenceCaseRed.test_case_B_mock_only_tests_do_not_verify_the_interface.


class ReviewDisplayRed(SandboxClass):
    """single (N/A path), G1-G5 PASSED with confirming reviews."""
    fixture = SINGLE
    split = False
    na_reviews = True

    def test_F12_gate_output_says_na_not_passed(self):
        code, out = self.sb.vm("gate", "WI-001", "G6")
        self.assertEqual(code, 0, out)
        self.assertIn("WI-001 G6 N/A", out.splitlines()[0], f"{RED} {out.splitlines()[0]}")


@unittest.skipUnless(has_pytest(), "pytest not installed")
class ReviewInitRed(unittest.TestCase):
    def test_F11_unnormalised_paths_are_refused(self):
        for given in ("tests/integration/..", "tests/."):
            sb = Sandbox(fixture=PIPELINE)
            try:
                sb.put_code()
                code, out = sb.vm("init", "--project", str(sb.root), "--lint", "none", "--allow-syntax-only",
                                  "--integration-tests", given)
                self.assertNotEqual(code, 0, f"{RED} {given!r} is the unit scope: {out}")
                self.assertFalse((sb.root / ".vmodel").exists())
            finally:
                sb.cleanup()


if __name__ == "__main__":
    unittest.main()

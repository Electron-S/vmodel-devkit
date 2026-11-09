"""G6 execution and judgement on a real provider/consumer project (T01, T02, T04, T07, T18; REQ-G6-08, 18-20)."""
from __future__ import annotations

import json
import unittest

from g6_base import (RED, SandboxClass, evidence_record, gate_view, justify_test_change, ledger_record,
                     replace_function)
from helpers import PLUGIN


class GateRed(SandboxClass):
    """pipeline, split commands, G1-G5 PASSED."""

    def set_integration_argv(self, argv: list[str], timeout_s: int = 300) -> None:
        cfg = self.sb.config()
        cfg["integration_test"] = {"argv": argv, "timeout_s": timeout_s}
        self.sb.set_config(cfg)
        self.regate("G4", "G5")  # config.json is part of the G4/G5 manifest

    def test_T01_real_provider_consumer_integration_passes(self):
        code, res = self.sb.gate("G6")
        self.assertEqual(res["status"], "PASSED", f"{RED} G6 must pass on real integration tests: {res}")
        self.assertEqual(code, 0)
        self.assertEqual(res.get("applicability"), "required")
        self.assertEqual(len(res["evidence"]), 1)
        ev = evidence_record(self.sb, res)
        self.assertEqual((ev["kind"], ev["gate"], ev["exit_code"], ev["command_source"]),
                         ("integration_test", "G6", 0, "integration_test"))
        self.assertIn("tests/integration", ev["command"])
        self.assertTrue(ev["files"]["junit.xml"]["sha256"])
        rec = ledger_record(self.sb, res["record_id"])
        self.assertEqual(rec["executed_tests"], {"TEST-010": "passed", "TEST-011": "passed", "TEST-012": "passed"})
        ifs = {i["id"]: i for i in rec["interfaces"]}
        self.assertEqual(set(ifs), {"IF-001", "IF-002"})
        self.assertTrue(all(i["covered"] for i in ifs.values()))
        self.assertEqual(ifs["IF-001"]["tests"]["TEST-010"]["path"], "static")
        self.assertTrue(ifs["IF-001"]["tests"]["TEST-010"]["reaches_provider"])
        self.assertTrue(ifs["IF-001"]["tests"]["TEST-010"]["reaches_consumer"])
        self.assertEqual(self.check(res, "G6.IF_COVERAGE")["status"], "pass")
        self.assertEqual(self.sb.vm("verify-evidence", str(self.sb.root / res["evidence"][0]["path"]))[0], 0)
        self.assertEqual(self.sb.vm("audit")[0], 0)
        self.assertEqual(gate_view(self.sb, "G6")["status"], "PASSED")

    def test_T02_integration_failure_fails_g6(self):
        rp = self.sb.root / "src/pipeline/report.py"
        rp.write_text(rp.read_text(encoding="utf-8").replace(
            "    records = parse(text)\n",
            "    try:\n        records = parse(text)\n    except ValueError:\n        records = []\n"), encoding="utf-8")
        self.regate("G4", "G5")  # the unit tests still pass: only the IF-001 error contract is broken
        code, res = self.sb.gate("G6")
        self.assertEqual(res["status"], "FAILED", f"{RED} a failing integration test must fail G6: {res}")
        self.assertEqual(code, 1)
        self.assertTrue(res["record_id"])
        rec = ledger_record(self.sb, res["record_id"])
        self.assertTrue(rec["failure_signature"])
        self.assertIn("TEST-011", rec["executed_tests"])
        self.assertEqual(rec["executed_tests"]["TEST-011"], "failed")
        self.assertTrue(any("TEST_011" in c for c in rec["failed_cases"]))
        self.assertEqual(self.check(res, "G6.RESULTS")["status"], "fail")
        self.assertIn("TEST-011: failed", self.check(res, "G6.TEST_MAPPING")["items"])

    def test_T04_unit_command_reused_as_integration_command_is_rejected(self):
        unit = self.sb.config()["unit_test"]["argv"]
        self.set_integration_argv(list(unit))
        res = self.g6()
        self.assertEqual(res["status"], "FAILED", f"{RED} running the unit tests must not pass G6: {res}")
        scope = self.check(res, "G6.SCOPE")
        self.assertEqual(scope["status"], "fail")
        self.assertTrue(any(i.startswith("TEST-001") for i in scope["items"]), scope)
        mapping = self.check(res, "G6.TEST_MAPPING")
        self.assertIn("TEST-010: not executed", mapping["items"])

    def test_T04b_whole_test_tree_as_integration_command_is_rejected(self):
        self.set_integration_argv(["{python}", "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests",
                                   "--junitxml={junit}"])
        res = self.g6()
        self.assertEqual(res["status"], "FAILED", f"{RED} unit tests inside the G6 run fail G6.SCOPE: {res}")
        self.assertEqual(self.check(res, "G6.SCOPE")["status"], "fail")

    def test_T07_integration_command_that_skips_an_interface_test(self):
        self.set_integration_argv(["{python}", "-m", "pytest", "-q", "-p", "no:cacheprovider",
                                   "tests/integration/test_pipeline.py::test_TEST_010_report_uses_real_parser",
                                   "tests/integration/test_pipeline.py::test_TEST_011_parser_error_reaches_report",
                                   "--junitxml={junit}"])
        res = self.g6()
        self.assertEqual(res["status"], "FAILED", f"{RED} IF-002 is not verified by this run: {res}")
        self.assertIn("TEST-012: not executed", self.check(res, "G6.TEST_MAPPING")["items"])
        cov = self.check(res, "G6.IF_COVERAGE")
        self.assertEqual(cov["status"], "fail")
        self.assertTrue(any(i.startswith("IF-002") for i in cov["items"]), cov)

    def test_T07b_skipped_integration_test_fails(self):
        path = self.sb.root / "tests/integration/test_pipeline.py"
        replace_function(path, "test_TEST_012_cli_main_reads_file",
                         "@pytest.mark.skip(reason='later')\n"
                         "def test_TEST_012_cli_main_reads_file(tmp_path, capsys):\n"
                         "    f = tmp_path / 'scores.csv'\n"
                         "    f.write_text('a,1\\n', encoding='utf-8')\n"
                         "    assert main([str(f)]) == 0\n")
        justify_test_change(self.sb, "tests/integration/test_pipeline.py")
        self.regate("G4", "G5")
        res = self.g6()
        self.assertEqual(res["status"], "FAILED", f"{RED} a skipped integration test verifies nothing: {res}")
        self.assertIn("TEST-012: skipped", self.check(res, "G6.TEST_MAPPING")["items"])

    def test_T18_zero_tests_with_exit_0_is_not_a_pass(self):
        self.set_integration_argv(["{python}", "-c",
                                   "import sys; open(sys.argv[1], 'w').write('<testsuite tests=\"0\"></testsuite>')",
                                   "{junit}"])
        res = self.g6()
        self.assertEqual(res["status"], "FAILED", f"{RED} 0 tests must fail G6: {res}")
        self.assertEqual(self.check(res, "G6.EXECUTION")["status"], "pass")
        self.assertEqual(self.check(res, "G6.RESULTS")["detail"], "0 tests executed")

    def test_T18_exit_0_without_junit_is_not_a_pass(self):
        self.set_integration_argv(["{python}", "-c", "pass", "{junit}"])
        res = self.g6()
        self.assertEqual(res["status"], "FAILED", f"{RED} no runner evidence, no PASS: {res}")
        self.assertIn("junit.xml was not produced", self.check(res, "G6.EXECUTION")["detail"])

    def test_T18_timeout_fails_and_start_failure_blocks(self):
        self.set_integration_argv(["{python}", "-c", "import time; time.sleep(30)", "{junit}"], timeout_s=1)
        res = self.g6()
        self.assertEqual(res["status"], "FAILED", f"{RED} timeout: {res}")
        self.assertIn("timed out", self.check(res, "G6.EXECUTION")["detail"])
        self.add_defect_for(res)
        self.set_integration_argv(["vmodel-no-such-test-runner", "{junit}"])
        res = self.g6()
        self.assertEqual((res["status"], res.get("blocked_reason")), ("BLOCKED", "tool_unavailable"), res)

    def add_defect_for(self, res: dict) -> None:
        self.sb.add_defect(res["record_id"], "G6", phase="P6", fix_scope=[".vmodel/config.json"])

    def test_T18_forged_results_are_not_evidence(self):
        fake = self.sb.root / ".vmodel/evidence/WI-001/G6/20260101T000000000000Z-integration-fake"
        fake.mkdir(parents=True)
        (fake / "record.json").write_text(json.dumps({
            "schema": "vmodel.evidence/1", "work_item": "WI-001", "gate": "G6", "kind": "integration_test",
            "exit_code": 0, "junit_summary": {"tests": 3, "failures": 0}, "sig": "hmac-sha256:" + "0" * 64}),
            encoding="utf-8")
        (self.sb.wi_dir / "test-results.json").write_text('{"G6": "PASSED", "tests": 3}', encoding="utf-8")
        (self.sb.wi_dir / "reviews" / "G6.json").write_text('{"gate": "G6", "verdict": "approve"}', encoding="utf-8")
        view = gate_view(self.sb, "G6")
        self.assertEqual(view["status"], "IN_PROGRESS", f"{RED} forged files never make G6 PASSED: {view}")
        self.assertTrue(view.get("not_evaluated"))
        code, out = self.sb.vm("verify-evidence", str(fake / "record.json"))
        self.assertEqual(code, 1)
        self.assertIn("not referenced by the signed ledger", out)

    def test_B10_inputs_changed_during_run(self):
        self.set_integration_argv(["{python}", "-c",
                                   "import sys; open('src/pipeline/parser.py', 'a').write('\\n# touched\\n'); "
                                   "open(sys.argv[1], 'w').write('<testsuite tests=\"0\"></testsuite>')",
                                   "{junit}"])
        res = self.g6()
        self.assertEqual(self.check(res, "G6.INPUTS_UNCHANGED")["status"], "fail", f"{RED} {res}")
        self.assertIn("changed: src/pipeline/parser.py", self.check(res, "G6.INPUTS_UNCHANGED")["items"])

    def test_B11_g5_stale_blocks_without_record(self):
        p = self.sb.root / "src/pipeline/parser.py"
        p.write_bytes(p.read_bytes() + b"\n")
        code, res = self.sb.gate("G6")
        self.assertEqual((code, res["status"], res["recorded"]), (3, "BLOCKED", False))
        self.assertTrue(any("G5 must be PASSED" in r for r in res["reasons"]), f"{RED} {res['reasons']}")

    def test_B13_agent_environment_is_scrubbed(self):
        env = {**self.sb.env, "PYTEST_ADDOPTS": "--collect-only", "PYTHONPATH": "/nonexistent-agent-path"}
        code, out = self.sb.vm("gate", "WI-001", "G6", "--json", env=env)
        res = json.loads(out)
        self.assertEqual(res["status"], "PASSED", f"{RED} agent PYTEST_ADDOPTS must not steer G6: {res}")
        dropped = evidence_record(self.sb, res)["environment"]["scrubbed"]
        self.assertIn("PYTEST_ADDOPTS", dropped)
        self.assertIn("PYTHONPATH", dropped)


class GateDefinitionRed(unittest.TestCase):
    def test_B14_g6_is_mechanical_without_ai_review(self):
        gates = json.loads((PLUGIN / "validator/vmodel_validator/data/gates.json").read_text(encoding="utf-8"))
        g6 = [g for g in gates["gates"] if g["id"] == "G6"][0]
        self.assertTrue(g6["implemented"], f"{RED} G6 is implemented in 0.2.0")
        self.assertTrue(g6["agents"]["reviewer"].startswith("none (mechanical)"))
        self.assertFalse([c for c in g6["checks"] if c["kind"] == "ai_review"])
        self.assertEqual([c["id"] for c in g6["checks"]],
                         ["G6.PREREQ", "G6.APPLICABILITY", "G6.CONFIG", "G6.EXECUTION", "G6.RESULTS", "G6.SCOPE",
                          "G6.TEST_MAPPING", "G6.IF_COVERAGE", "G6.NO_WEAKENING", "G6.INPUTS_UNCHANGED"])
        for name in ("reviews/G2.json", "reviews/G3.json", "reviews/G4.json"):
            self.assertIn(name, g6["manifest"]["artifacts"])


if __name__ == "__main__":
    unittest.main()

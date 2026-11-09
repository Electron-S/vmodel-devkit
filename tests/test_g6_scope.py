"""G5/G6 separation (T05; REQ-G6-03-08)."""
from __future__ import annotations

import unittest

from g6_base import RED, SandboxClass, ledger_record, ledger_records, replace_function, wi_status
from helpers import PLUGIN, Sandbox, fail_g5, has_pytest, old_release


class ScopeRed(SandboxClass):
    """pipeline, split commands, G1-G5 PASSED."""

    def test_T05_unit_command_running_integration_tests_fails_g5(self):
        cfg = self.sb.config()
        cfg["unit_test"]["argv"] = ["{python}", "-m", "pytest", "-q", "-p", "no:cacheprovider", "--junitxml={junit}"]
        self.sb.set_config(cfg)
        self.regate("G4")
        code, res = self.sb.gate("G5")
        self.assertEqual(res["status"], "FAILED", f"{RED} integration tests inside G5 with integration_test set: {res}")
        scope = self.check(res, "G5.SCOPE")
        self.assertEqual(scope["status"], "fail")
        self.assertEqual(sorted(i.split(":")[0] for i in scope["items"]), ["TEST-010", "TEST-011", "TEST-012"])

    def test_T05_integration_run_cannot_stand_in_for_a_unit_test(self):
        """A unit TEST id carried by a test in the integration folder is not run by the unit command: G5 cannot pass,
        so G6 is never reached (and G6.SCOPE would reject a unit id in its own run, see test_g6_gate T04)."""
        unit = self.sb.root / "tests/unit/test_report.py"
        replace_function(unit, "test_TEST_007_main_empty_file", None)
        (self.sb.root / "tests/integration/test_extra.py").write_text(
            "import json\n\nfrom pipeline.report import main\n\n\n"
            "def test_TEST_007_main_empty_file(tmp_path, capsys):\n"
            "    f = tmp_path / 'e.csv'\n    f.write_text('', encoding='utf-8')\n"
            "    assert main([str(f)]) == 0\n", encoding="utf-8")
        self.sb.review("G4")
        res = self.sb.gate("G4")[1]
        self.assertEqual(res["status"], "PASSED", res)  # the TEST-007 function exists (in the integration folder)
        res = self.sb.gate("G5")[1]
        self.assertEqual(res["status"], "FAILED", res)
        self.assertIn("TEST-007: not executed", self.check(res, "G5.TEST_MAPPING")["items"])
        self.sb.add_defect(res["record_id"], "G5", fix_scope=["tests/unit/test_report.py"])
        self.regate("G4")
        res = self.sb.gate("G5")[1]
        self.assertEqual(res["status"], "FAILED", res)  # the unit command still does not run TEST-007
        # G6 is never reached: it needs G5 PASSED
        res6 = self.sb.gate("G6")[1]
        self.assertFalse(res6["recorded"])
        self.assertTrue(any("G5 must be PASSED" in r for r in res6["reasons"]), f"{RED} {res6}")

    def test_D2_moving_integration_tests_out_of_g5_is_not_weakening(self):
        """Migration B: the wordfreq integration test leaves the unit run; G5.NO_WEAKENING accepts it (REQ-G6-07)."""
        sb = Sandbox()
        try:
            sb.init()
            sb.new_wi()
            sb.advance("G5")
            last_g5 = [r for r in ledger_records(sb) if r.get("gate") == "G5" and r.get("status") == "PASSED"][-1]
            tw = sb.root / "tests/test_wordfreq.py"
            replace_function(tw, "test_TEST_010_integration_punctuation", None)
            (sb.root / "tests/integration").mkdir()
            (sb.root / "tests/integration/test_wordfreq_if.py").write_text(
                "from textstats.wordfreq import count_words\n\n\n"
                "def test_TEST_010_integration_punctuation():\n    assert count_words('Hi! hi? HI.') == {'hi': 3}\n",
                encoding="utf-8")
            sb.split_tests()
            sb.save("change-requests.json", {"work_item": "WI-001", "change_requests": [{
                "id": "CR-001", "description": "G5/G6 분리: 통합 테스트를 tests/integration으로 옮김",
                "reason": "integration_test 명령 도입", "affected": ["TEST-010"], "status": "applied",
                "test_changes": [{"file": "tests/test_wordfreq.py", "since_record": last_g5["record_id"],
                                  "reason": "TEST-010을 통합 폴더로 이동", "requirements": ["REQ-001"],
                                  "impact": "G5는 unit만, TEST-010은 G6에서 실행"}]}]})
            sb.review("G4")
            self.assertEqual(sb.gate("G4")[1]["status"], "PASSED")
            res = sb.gate("G5")[1]
            self.assertEqual(res["status"], "PASSED", f"{RED} moving TEST-010 to G6 is not weakening: {res}")
            self.assertNotIn("TEST-010", ledger_record(sb, res["record_id"])["executed_tests"])
            res = sb.gate("G6")[1]
            self.assertEqual(res["status"], "PASSED", res)
        finally:
            sb.cleanup()

    def test_D3_mixed_run_without_integration_test_is_warned(self):
        sb = Sandbox()
        try:
            sb.init()
            sb.new_wi()
            sb.advance("G5")
            w = wi_status(sb)
            warnings = w.get("scope_warnings") or []
            self.assertTrue(any("TEST-010" in x for x in warnings), f"{RED} unit command ran TEST-010: {w}")
            self.assertTrue(any("not integration verification" in x for x in warnings), warnings)
            code, text = sb.vm("status")
            self.assertIn("TEST-010", text)
            self.assertEqual(sb.gate_status("G5"), "PASSED")  # a warning, not a decision (REQ-G6-06)
            sb.vm("report", "WI-001")
            report = (sb.root / ".vmodel/reports/WI-001.md").read_text(encoding="utf-8")
            self.assertIn("not integration verification", report)
        finally:
            sb.cleanup()


class ScopeChar(SandboxClass):
    def test_D5_unit_test_disappearing_is_still_weakening(self):
        cfg = self.sb.config()
        cfg["unit_test"]["argv"].insert(-1, "--deselect=tests/unit/test_report.py::test_TEST_007_main_empty_file")
        self.sb.set_config(cfg)
        self.regate("G4")
        res = self.sb.gate("G5")[1]
        self.assertEqual(res["status"], "FAILED", res)
        nw = self.check(res, "G5.NO_WEAKENING")
        self.assertEqual(nw["status"], "fail")
        self.assertTrue(any(i.startswith("TEST-007 was executed") for i in nw["items"]), nw)


@unittest.skipUnless(has_pytest(), "pytest not installed")
class ScopeInvariant(unittest.TestCase):
    def test_D4_g5_records_without_integration_test_are_unchanged(self):
        """wordfreq (unit command runs TEST-010) rework history: G5 records match the 0.1.5 release (REQ-G6-06)."""
        old = old_release("0.1.5")
        if old is None:
            self.skipTest("0.1.5 release not available")

        def history(plugin) -> list[tuple]:
            sb = Sandbox(plugin=plugin)
            try:
                s = fail_g5(sb)
                sb.add_defect(s["failed"], "G5", related=["REQ-002", *s["failing"]], status="fixed")
                s["wf"].write_text(s["good"], encoding="utf-8")
                sb.regate_g4()
                sb.gate("G5")
                # G5.EXECUTION items are the tail of pytest's output (timings vary run to run): status only
                return [(r["status"], r.get("failure_signature"),
                         tuple((c["id"], c["status"], () if c["id"] == "G5.EXECUTION" else tuple(c.get("items") or []))
                               for c in r["checks"]),
                         tuple(sorted(r["executed_tests"].items())), tuple(sorted(r["test_files"])))
                        for r in ledger_records(sb) if r.get("type") == "gate" and r["gate"] == "G5"]
            finally:
                sb.cleanup()

        self.assertEqual(history(PLUGIN), history(old))


if __name__ == "__main__":
    unittest.main()

"""G7 FAILED -> DEFECT -> fix -> re-verification, and the defect closure states (T11, T12; REQ-G7-16)."""
from __future__ import annotations

import unittest

from g7_base import CLI_EXIT_BUG, PYTEST, RED, G7Class, justify_test_change, replace_in, wi_status

FAILING = ["TEST-103", "TEST-106"]


class ReworkRed(G7Class):
    """gradecalc, system_test configured, G1-G6 PASSED."""

    def fail_g7(self) -> str:
        replace_in(self.sb.root / "src/gradecalc/cli.py", *CLI_EXIT_BUG)
        self.regate("G4", "G5", "G6")
        res = self.g7()
        self.assertEqual(res["status"], "FAILED", f"{RED} G7 must run and fail: {res}")
        return res["record_id"]

    def defect(self) -> dict:
        return [d for d in wi_status(self.sb)["defects"] if d["id"] == "DEFECT-001"][0]

    def record_defect(self, rid: str, **extra) -> None:
        kw = {"related": ["REQ-001", "REQ-003", "AC-001-3", *FAILING], "fix_scope": ["src/gradecalc/cli.py"],
              "status": "fixed"}
        kw.update(extra)
        self.sb.add_defect(rid, "G7", phase=kw.pop("phase", "P4"), **kw)

    def test_T11_failed_g7_needs_a_defect_then_the_fix_is_verified_and_closed(self):
        res = self.g7()
        self.assertEqual(res["status"], "PASSED", f"{RED} {res}")
        failed = self.fail_g7()
        again = self.sb.gate("G7")[1]
        self.assertEqual(again["status"], "BLOCKED")
        self.assertFalse(again["recorded"])
        self.assertTrue(any("rework record missing" in r and failed in r for r in again["reasons"]), again)
        replace_in(self.sb.root / "src/gradecalc/cli.py", CLI_EXIT_BUG[1], CLI_EXIT_BUG[0])  # the fix
        self.record_defect(failed)
        self.regate("G4", "G5", "G6")
        d = self.defect()
        self.assertEqual(d["closure_gate"], "G7")
        self.assertEqual(d["closure_state"], "FIX_APPLIED")  # G4-G6 passing again does not close a G7 defect
        self.assertEqual(d["failing_tests"], FAILING)
        passed = self.g7()
        self.assertEqual(passed["status"], "PASSED", passed)
        d = self.defect()
        self.assertEqual((d["closure_state"], d["verified_by"]), ("CLOSED", passed["record_id"]))
        self.assertEqual(wi_status(self.sb)["status"], "COMPLETED")
        self.assertEqual(self.sb.vm("lint", "WI-001")[0], 0)

    def test_T12_closure_is_withdrawn_when_g7_is_stale_or_blocked(self):
        failed = self.fail_g7()
        replace_in(self.sb.root / "src/gradecalc/cli.py", CLI_EXIT_BUG[1], CLI_EXIT_BUG[0])
        self.record_defect(failed)
        self.regate("G4", "G5", "G6")
        passed = self.g7()
        self.assertEqual(passed["status"], "PASSED", f"{RED} {passed}")
        self.assertEqual(self.defect()["closure_state"], "CLOSED")
        # a source change: G4-G7 STALE -> the past PASS is not a current closure
        src = self.sb.root / "src/gradecalc/grading.py"
        src.write_text(src.read_text(encoding="utf-8") + "\n# 주석\n", encoding="utf-8")
        d = self.defect()
        self.assertEqual((d["closure_state"], d["closure_gate_status"]), ("REVERIFY_REQUIRED", "STALE"))
        self.assertEqual(d["verified_by"], passed["record_id"])
        self.regate("G4", "G5", "G6")
        # G7 BLOCKED (the user broke system_test) is not a verification either
        cfg = self.sb.config()
        cfg["system_test"]["argv"] = [*PYTEST, "tests/system"]  # no {junit}
        self.sb.set_config(cfg)
        self.regate("G4", "G5", "G6")
        self.assertEqual(self.g7().get("blocked_reason"), "misconfigured")
        d = self.defect()
        self.assertEqual((d["closure_state"], d["closure_gate_status"], d["closure_action"]),
                         ("REVERIFY_REQUIRED", "BLOCKED", "resolve_block"))

    def test_T12_failed_reverification_and_unknown_results(self):
        failed = self.fail_g7()
        self.record_defect(failed)  # claims fixed, but the code is unchanged
        self.regate("G4", "G5", "G6")
        second = self.g7()
        self.assertEqual(second["status"], "FAILED", f"{RED} {second}")
        d = self.defect()
        self.assertEqual(d["closure_state"], "VERIFICATION_FAILED")
        self.assertEqual(d["closure_action"], "rework")
        self.assertIsNone(d["verified_by"])
        # the system test of AC-002-2 loses its id: its result in the cited failure is UNKNOWN, not "passed"
        replace_in(self.sb.root / "tests/system/test_api_system.py", "def test_TEST_105_api_rejects_invalid_score(",
                   "def test_api_rejects_invalid_score(")
        justify_test_change(self.sb, "tests/system/test_api_system.py", "TEST-105", reqs=("REQ-002",))
        self.sb.add_defect(second["record_id"], "G7")
        self.regate("G4", "G5", "G6")
        third = self.g7()
        self.assertEqual(third["status"], "FAILED", third)
        self.sb.add_defect(third["record_id"], "G7")
        d = self.defect()
        self.assertIn("TEST-105", d["unknown_tests"])
        self.assertTrue(any(w["category"] == "unknown_test_result" for w in d["warnings"]))

    def test_T12_three_identical_g7_failures_block(self):
        rid = self.fail_g7()
        for _ in range(2):
            self.record_defect(rid)
            self.regate("G4", "G5", "G6")
            res = self.g7()
            rid = res["record_id"]
        self.assertEqual((res["status"], res.get("blocked_reason")),
                         ("BLOCKED", "three_consecutive_identical_failures"), f"{RED} {res}")
        w = wi_status(self.sb)
        self.assertEqual(w["status"], "BLOCKED")
        self.assertEqual([g for g in w["gates"] if g["gate"] == "G7"][0]["blocked_reason"],
                         "three_consecutive_identical_failures")

    def test_T12_defect_schema_accepts_g7_and_p7(self):
        failed = self.fail_g7()
        self.record_defect(failed, phase="P7", status="open")
        code, out = self.sb.vm("lint", "WI-001")
        self.assertEqual(code, 0, out)
        self.regate("G4", "G5", "G6")
        res = self.g7()  # the rework precondition accepts the G7/P7 defect (schema-valid), so G7 runs again
        self.assertTrue(res["recorded"], res)
        self.assertFalse(any("defects.json invalid" in r for r in res["reasons"]))


if __name__ == "__main__":
    unittest.main()

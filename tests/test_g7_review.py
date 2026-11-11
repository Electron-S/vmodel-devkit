"""Independent implementation review of G7 (68b4d67): findings reproduced before the fix (RED target: that build).

R1 (MEDIUM) trace/report recomputed "verified" from the current tests.json mapping instead of the signed G7 record.
R2 (LOW) next_action said "report COMPLETED" for a work item whose profile is not implemented.
R3 (LOW) configure-tests missed the overlap with an integration command that names no folder (or ".").
"""
from __future__ import annotations

import os
import unittest

from g7_base import CLI_EXIT_BUG, GRADECALC, PYTEST, RED, G7Class, replace_in, wi_status
from helpers import Sandbox, has_pytest


class TraceRecordRed(G7Class):
    """gradecalc, system_test configured, G1-G6 PASSED."""

    def acceptance(self) -> dict:
        tv = self.sb.vm_json("trace", "WI-001")[1]
        return {a["ac"]: a for a in tv["acceptance"]}

    def test_R1_new_ac_is_not_verified_by_an_older_run(self):
        res = self.g7()
        self.assertEqual(res["status"], "PASSED", res)
        req = self.sb.load("requirements.json")
        req["requirements"][0]["acceptance_criteria"].append({"id": "AC-001-4", "criterion": "79는 C"})
        self.sb.save("requirements.json", req)
        tests = self.sb.load("tests.json")
        [t for t in tests["tests"] if t["id"] == "TEST-102"][0]["acceptance_criteria"].append("AC-001-4")
        self.sb.save("tests.json", tests)
        row = self.acceptance()["AC-001-4"]
        self.assertFalse(row["verified"], f"{RED} {row}")
        self.assertEqual(row.get("state"), "not evaluated")
        report = self.sb.vm("report", "WI-001", "--stdout")[1]
        self.assertNotIn("| REQ-001 | AC-001-4 | TEST-102 (passed) | yes |", report)
        self.assertIn("G7 now STALE", self.sb.vm("trace", "WI-001")[1])

    def test_R1_remapped_ac_keeps_the_recorded_failure(self):
        replace_in(self.sb.root / "src/gradecalc/cli.py", *CLI_EXIT_BUG)
        self.regate("G4", "G5", "G6")
        failed = self.g7()
        self.assertEqual(failed["status"], "FAILED", failed)
        tests = self.sb.load("tests.json")
        for t in tests["tests"]:
            if t["id"] == "TEST-103":
                t["acceptance_criteria"] = []
            if t["id"] == "TEST-101":
                t["acceptance_criteria"].append("AC-001-3")
        self.sb.save("tests.json", tests)
        row = self.acceptance()["AC-001-3"]
        self.assertFalse(row["verified"], f"{RED} {row}")
        self.assertEqual(row["tests"], {"TEST-103": "failed"})  # what the signed record says
        text = self.sb.vm("trace", "WI-001")[1]
        self.assertNotIn("AC-001-3 (REQ-001): TEST-101(passed) verified", text)


class ProfileRed(G7Class):
    """gradecalc whose workitem.json names the LITE profile (not implemented): G1-G6 PASSED."""

    @classmethod
    def mutate(cls, sb: Sandbox, gate: str) -> None:
        if gate == "G1":
            wi = sb.load("workitem.json")
            wi["profile"] = "LITE"
            sb.save("workitem.json", wi)

    def test_R2_next_action_does_not_claim_completed_for_an_unimplemented_profile(self):
        res = self.g7()
        self.assertEqual(res["status"], "PASSED", res)
        w = wi_status(self.sb)
        self.assertEqual(w["status"], "PARTIALLY_VERIFIED")
        self.assertNotIn("report COMPLETED", w["next_action"], f"{RED} {w['next_action']}")
        self.assertIn("PARTIALLY_VERIFIED", w["next_action"])


@unittest.skipUnless(has_pytest() and os.name == "posix", "pytest and a POSIX pty are needed")
class OverlapRed(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox(fixture=GRADECALC)
        self.sb.init()
        self.sb.put_code()

    def tearDown(self):
        self.sb.cleanup()

    def test_R3_integration_command_without_folder_or_dot_overlaps_the_system_folder(self):
        for target in ([], ["."]):
            cfg = self.sb.config()
            cfg["integration_test"] = {"argv": [*PYTEST, *target, "--junitxml={junit}"], "timeout_s": 60}
            self.sb.set_config(cfg)
            out = self.sb.run_tty("configure-tests", "--system", "tests/system").decode("utf-8", "replace")
            self.assertNotIn("system_test", self.sb.config(), f"{RED} {target} {out}")
            self.assertIn("overlap", out)



@unittest.skipUnless(has_pytest() and os.name == "posix", "pytest and a POSIX pty are needed")
class OverlapChar(unittest.TestCase):
    """A separate integration folder never overlapped (both builds); the fix must keep accepting it."""

    def setUp(self):
        self.sb = Sandbox(fixture=GRADECALC)
        self.sb.init()
        self.sb.put_code()

    def tearDown(self):
        self.sb.cleanup()

    def test_R3_option_values_are_not_paths(self):
        (self.sb.root / "tests/integration").mkdir()
        (self.sb.root / "tests/integration/test_x.py").write_text("def test_x():\n    pass\n", encoding="utf-8")
        cfg = self.sb.config()
        cfg["integration_test"] = {"argv": [*PYTEST, "tests/integration", "--junitxml={junit}"], "timeout_s": 60}
        self.sb.set_config(cfg)
        out = self.sb.run_tty("configure-tests", "--system", "tests/system").decode("utf-8", "replace")
        self.assertIn("system_test", self.sb.config(), out)  # a separate folder is fine (both builds)


if __name__ == "__main__":
    unittest.main()

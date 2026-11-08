"""Rework loop in the order the skills document it (findings of the real-session rework drill, 2026-11-08).

defects.json is a G4/G5 input (its test_changes are reviewed at G4 and read by G5.NO_WEAKENING), so any edit after
a PASS makes G4/G5 STALE. The 0.1.2 skills told the agent to mark the defect `fixed` only after the gate passed,
which guarantees that a correctly reworked work item drops back from PARTIALLY_VERIFIED to IN_PROGRESS.
"""
from __future__ import annotations

import json
import re
import unittest

from helpers import PLUGIN, Sandbox, has_pytest

SKILLS = {name: PLUGIN / "skills" / name / "SKILL.md" for name in ("start", "rework")}


@unittest.skipUnless(has_pytest(), "pytest not installed")
class ReworkOrder(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox()
        self.sb.init()
        self.sb.new_wi()
        self.sb.advance("G4")
        self.wf = self.sb.root / "src/textstats/wordfreq.py"
        self.good = self.wf.read_text(encoding="utf-8")
        self.wf.write_text(self.good.replace("if n <= 0:", "if n < 0:"), encoding="utf-8")
        self.sb.review("G4")
        self.assertEqual(self.sb.gate("G4")[1]["status"], "PASSED")
        res = self.sb.gate("G5")[1]
        self.assertEqual(res["status"], "FAILED")
        self.failed = res["record_id"]

    def tearDown(self):
        self.sb.cleanup()

    def wi_state(self) -> tuple[str, dict]:
        w = self.sb.status()["work_items"][0]
        return w["status"], {g["gate"]: g for g in w["gates"]}

    def test_editing_defects_after_the_pass_makes_g4_g5_stale(self):
        """Validator invariant the skills must respect (characterisation, holds since 0.1.0)."""
        self.wf.write_text(self.good, encoding="utf-8")
        self.sb.add_defect(self.failed, "G5", phase="P4")
        self.sb.regate_g4()
        self.assertEqual(self.sb.gate("G5")[1]["status"], "PASSED")
        self.assertEqual(self.wi_state()[0], "PARTIALLY_VERIFIED")
        path = self.sb.wi_dir / "defects.json"
        doc = json.loads(path.read_text(encoding="utf-8"))
        doc["defects"][0]["status"] = "fixed"
        path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
        status, gates = self.wi_state()
        self.assertEqual(status, "IN_PROGRESS")
        self.assertEqual((gates["G4"]["status"], gates["G5"]["status"]), ("STALE", "STALE"))
        self.assertIn("changed: .vmodel/work-items/WI-001/defects.json", gates["G4"]["changed_files"])

    def test_documented_order_ends_partially_verified_with_ledger_backed_closure(self):
        """Fix + `status: fixed` together, then re-review and re-verify: no extra STALE round."""
        self.wf.write_text(self.good, encoding="utf-8")
        self.sb.add_defect(self.failed, "G5", phase="P4", status="fixed")
        self.assertEqual(self.sb.gate_status("G4"), "STALE")
        self.sb.regate_g4()
        res = self.sb.gate("G5")[1]
        self.assertEqual(res["status"], "PASSED")
        self.assertEqual(self.wi_state()[0], "PARTIALLY_VERIFIED")
        self.sb.vm("report", "WI-001")
        report = (self.sb.root / ".vmodel/reports/WI-001.md").read_text(encoding="utf-8")
        self.assertIn(f"DEFECT-001 [fixed — verified by {res['record_id']}]", report)


@unittest.skipUnless(has_pytest(), "pytest not installed")
class DefectTraceFromLedger(unittest.TestCase):
    """The drill's defect linked 3 of the 5 failing TEST ids and nothing noticed; S2 had to `tail` the raw ledger to
    see what failed. The validator now shows the failure itself and derives defect links from the signed record."""

    def setUp(self):
        self.sb = Sandbox()
        self.sb.init()
        self.sb.new_wi()
        self.sb.advance("G4")
        self.wf = self.sb.root / "src/textstats/wordfreq.py"
        self.good = self.wf.read_text(encoding="utf-8")
        self.wf.write_text(self.good.replace("if n <= 0:", "if n < 0:"), encoding="utf-8")
        self.sb.review("G4")
        self.sb.gate("G4")
        res = self.sb.gate("G5")[1]
        self.assertEqual(res["status"], "FAILED")
        self.failed = res["record_id"]
        mapping = [c for c in res["checks"] if c["id"] == "G5.TEST_MAPPING"][0]
        self.failing = sorted(i.split(":")[0] for i in mapping["items"] if i.endswith(": failed"))
        self.assertTrue(self.failing)

    def tearDown(self):
        self.sb.cleanup()

    def wi(self) -> dict:
        return self.sb.status()["work_items"][0]

    def test_status_shows_the_failed_checks_of_a_failed_gate(self):
        g5 = [g for g in self.wi()["gates"] if g["gate"] == "G5"][0]
        ids = [c["id"] for c in g5["failed_checks"]]
        self.assertIn("G5.RESULTS", ids)
        self.assertEqual(g5["failing_tests"], self.failing)
        code, text = self.sb.vm("status", "WI-001")
        self.assertIn("G5.RESULTS", text)
        self.assertIn(self.failing[0], text)

    def test_defect_links_are_derived_from_the_ledger_and_gaps_are_flagged(self):
        self.sb.add_defect(self.failed, "G5", phase="P4", related=["REQ-001"])
        d = self.wi()["defects"][0]
        self.assertEqual((d["id"], d["failing_tests"], d["unlinked_failing_tests"]),
                         ("DEFECT-001", self.failing, self.failing))
        self.assertIsNone(d["verified_by"])
        code, out = self.sb.vm("lint", "WI-001")
        self.assertEqual(code, 1, out)
        self.assertIn(f"DEFECT-001 does not link failing test(s) of {self.failed}", out)
        # complete the links, fix, re-verify: the gap disappears and the closure comes from the ledger
        self.sb.add_defect(self.failed, "G5", related=["REQ-001", *self.failing], status="fixed")
        self.sb.vm("lint", "WI-001")
        self.wf.write_text(self.good, encoding="utf-8")
        self.sb.regate_g4()
        res = self.sb.gate("G5")[1]
        self.assertEqual(res["status"], "PASSED")
        d = self.wi()["defects"][0]
        self.assertEqual((d["unlinked_failing_tests"], d["verified_by"]), ([], res["record_id"]))
        self.sb.vm("report", "WI-001")
        report = (self.sb.root / ".vmodel/reports/WI-001.md").read_text(encoding="utf-8")
        self.assertIn(f"failing tests in {self.failed} (from the signed ledger): {', '.join(self.failing)}", report)

    def test_closure_follows_the_signed_failure_record_not_the_agent_written_gate(self):
        self.sb.add_defect(self.failed, "G4", phase="P4", related=list(self.failing), status="fixed")  # wrong gate
        self.wf.write_text(self.good, encoding="utf-8")
        self.sb.regate_g4()
        res = self.sb.gate("G5")[1]
        self.assertEqual(res["status"], "PASSED")
        self.assertEqual(self.wi()["defects"][0]["verified_by"], res["record_id"])

    def test_unlinked_failing_tests_do_not_block_the_rework(self):
        """Visibility, not a new gate: the semantic check is the verifier's G4 review (no extra STALE rounds)."""
        self.sb.add_defect(self.failed, "G5", phase="P4", status="fixed")
        self.wf.write_text(self.good, encoding="utf-8")
        self.sb.regate_g4()
        self.assertEqual(self.sb.gate("G5")[1]["status"], "PASSED")
        self.assertEqual(self.wi()["defects"][0]["unlinked_failing_tests"], self.failing)


class SkillWording(unittest.TestCase):
    """The skills must put `status: fixed` before the re-review, never after the pass."""

    def test_no_skill_marks_the_defect_fixed_after_the_gate_passes(self):
        for name, path in SKILLS.items():
            text = path.read_text(encoding="utf-8")
            self.assertIsNone(re.search(r"when the gate passes,?\s+set the defect", text, re.I), name)
            self.assertIsNone(re.search(r"set the defect `?status`? to `?fixed`? once fixed", text, re.I), name)

    def test_skills_say_mark_fixed_before_the_re_review_and_why(self):
        for name, path in SKILLS.items():
            text = path.read_text(encoding="utf-8")
            self.assertIn("before the re-review", text, name)
            self.assertRegex(text, r"(?s)defects\.json.{0,200}STALE", name)

    def test_verifier_checks_root_cause_against_the_failure_and_does_not_ask_for_post_pass_edits(self):
        """In the drill the G4 reviewer asked to close the defect 'after this gate' -> one extra STALE round."""
        text = (PLUGIN / "agents" / "verifier.md").read_text(encoding="utf-8")
        self.assertIn("failing_tests", text)
        self.assertRegex(text, r"(?i)root cause .{0,80}every failing")
        self.assertRegex(text, r"(?i)never ask .{0,60}defects\.json .{0,40}after")


if __name__ == "__main__":
    unittest.main()

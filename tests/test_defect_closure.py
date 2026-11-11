"""v0.1.4 F1: derived defect closure state (D32 option C, D36; state names revised by D37: the former VERIFIED is now
REVERIFY_REQUIRED or VERIFICATION_FAILED, a withheld verification is UNKNOWN, see test_defect_display_states.py).

defects.json keeps `open` / `fixed` (the agent's claim). The validator derives the closure from the signed ledger and
the *current* gate state, so a past "verified by" no longer reads as valid once the gate went STALE (drill-3 P-F1).
Class suffixes follow scripts/red_green.py (...Red fails on 0.1.3, ...Invariant passes on both).
"""
from __future__ import annotations

import json
import unittest

from helpers import Sandbox
from rework_case import FailedG5Case


class DefectClosureRed(FailedG5Case):
    def test_open_and_fix_applied_before_verification(self):
        self.sb.add_defect(self.failed, "G5", related=["REQ-002", *self.failing])
        d = self.defect()
        self.assertEqual((d.get("closure_state"), d["verified_by"]), ("OPEN", None))
        self.set_defect(status="fixed")
        d = self.defect()
        self.assertEqual((d.get("closure_state"), d["verified_by"], d.get("closure_gate_status")),
                         ("FIX_APPLIED", None, None))
        self.assertTrue(self.defect_line().startswith("DEFECT-001 FIX_APPLIED"), self.defect_line())

    def test_closed_after_the_gate_passes(self):
        res = self.close_defect()
        d = self.defect()
        self.assertEqual((d.get("closure_state"), d.get("closure_gate"), d.get("closure_gate_status"), d["verified_by"]),
                         ("CLOSED", "G5", "PASSED", res["record_id"]))
        self.assertTrue(self.defect_line().startswith("DEFECT-001 CLOSED"), self.defect_line())

    def test_source_change_after_closure_shows_verified_not_closed(self):
        """P-F1 reproduced: G4/G5 STALE after the closure -> REVERIFY_REQUIRED (D37; was VERIFIED), not CLOSED."""
        res = self.close_defect()
        wf = self.s["wf"]
        wf.write_bytes(wf.read_bytes() + b"\n")
        g = self.gates()
        self.assertEqual((g["G4"], g["G5"]), ("STALE", "STALE"))
        d = self.defect()
        self.assertEqual((d.get("closure_state"), d.get("closure_gate_status"), d["verified_by"]),
                         ("REVERIFY_REQUIRED", "STALE", res["record_id"]))
        line = self.defect_line()
        self.assertTrue(line.startswith("DEFECT-001 REVERIFY_REQUIRED"), line)
        self.assertIn("G5 is now STALE", line)
        self.assertIn("re-verify", line)
        self.assertNotIn("CLOSED", line)

    def test_upstream_artifact_change_keeps_it_from_closed(self):
        self.close_defect()
        tests = self.sb.load("tests.json")
        tests["tests"][0]["title"] += " (edited)"
        self.sb.save("tests.json", tests)
        self.assertEqual(self.gates()["G3"], "STALE")
        d = self.defect()
        self.assertEqual(d.get("closure_state"), "REVERIFY_REQUIRED")
        self.assertNotEqual(d.get("closure_gate_status"), "PASSED")

    def test_claim_open_but_verified_is_annotated(self):
        self.sb.add_defect(self.failed, "G5", related=["REQ-002", *self.failing])  # never marked fixed
        self.s["wf"].write_text(self.s["good"], encoding="utf-8")
        self.gate_g4()
        res = self.sb.gate("G5")[1]
        self.assertEqual(res["status"], "PASSED")
        d = self.defect()
        self.assertEqual(d.get("closure_state"), "CLOSED")
        note = d.get("claim_note") or ""
        self.assertIn("says open", note)
        self.assertIn(res["record_id"], note)
        self.assertIn("says open", self.status_text())

    def test_report_shows_the_same_closure_state_as_status(self):
        res = self.close_defect()
        report = self.report()
        self.assertIn(f"DEFECT-001 [fixed — verified by {res['record_id']}]", report)  # 0.1.3 wording kept
        self.assertIn("closure: CLOSED", report)
        wf = self.s["wf"]
        wf.write_bytes(wf.read_bytes() + b"\n")
        self.assertEqual(self.defect().get("closure_state"), "REVERIFY_REQUIRED")
        report = self.report()
        self.assertIn("closure: REVERIFY_REQUIRED", report)
        self.assertIn("G5 is now STALE", report)
        self.assertNotIn("closure: CLOSED", report)

    def test_invalid_or_withheld_verification_is_never_closed(self):
        """Closure follows only valid failure evidence (F3): a PASSED record cited as 'failure', or a verifying PASS
        whose evidence no longer matches the ledger, must not produce a verified state (D37: the latter is UNKNOWN)."""
        self.sb.add_defect(self.s["g4_pass"], "G4", status="fixed")
        self.s["wf"].write_text(self.s["good"], encoding="utf-8")
        self.gate_g4()
        self.assertEqual(self.defect().get("closure_state"), "FIX_APPLIED")
        self.set_defect(found_in_records=[self.failed], related=["REQ-002", *self.failing])
        self.gate_g4()
        res = self.sb.gate("G5")[1]
        self.assertEqual(self.defect().get("closure_state"), "CLOSED")
        ev = self.sb.root / res["evidence"][0]["path"]
        (ev.parent / "stdout.bin").write_bytes(b"edited output")
        d = self.defect()
        self.assertEqual((d.get("closure_state"), d["verified_by"]), ("UNKNOWN", None))
        self.assertIn("withheld", self.defect_line())


class DefectClosureReviewRed(FailedG5Case):
    """Findings of the independent F1/F3 reviews (2026-11-09), reproduced before the fix."""

    def test_multi_gate_failure_is_not_closed_by_the_upstream_pass(self):
        self.sb.add_defect(self.failed, "G5", related=["REQ-002", *self.failing], status="fixed")
        self.s["wf"].write_text(self.s["good"], encoding="utf-8")
        self.sb.review("G4", verdict="reject")
        g4_fail = self.sb.gate("G4")[1]
        self.sb.add_defect(g4_fail["record_id"], "G4")
        self.gate_g4()
        self.assertEqual(self.gates()["G5"], "FAILED")
        self.assertEqual(self.defect().get("closure_state"), "FIX_APPLIED")
        self.assertNotIn("CLOSED", self.defect_line())
        self.assertEqual(self.sb.gate("G5")[1]["status"], "PASSED")
        self.assertEqual(self.defect().get("closure_state"), "CLOSED")

    def test_rerun_after_stale_names_the_current_pass(self):
        first = self.close_defect()
        wf = self.s["wf"]
        wf.write_bytes(wf.read_bytes() + b"\n")
        self.gate_g4()
        again = self.sb.gate("G5")[1]
        self.assertEqual(again["status"], "PASSED")
        d = self.defect()
        self.assertEqual((d.get("closure_state"), d["verified_by"], d.get("closure_gate_record")),
                         ("CLOSED", first["record_id"], again["record_id"]))
        self.assertIn(f"G5 PASSED ({again['record_id']})", self.defect_line())

    def test_failure_after_the_pass_is_verified_not_closed(self):  # D37: VERIFICATION_FAILED (was VERIFIED)
        self.close_defect()
        wf = self.s["wf"]
        wf.write_text(self.s["good"].replace("if n <= 0:", "if n < 0:"), encoding="utf-8")
        self.gate_g4()
        self.assertEqual(self.sb.gate("G5")[1]["status"], "FAILED")
        d = self.defect()
        self.assertEqual((d.get("closure_state"), d.get("closure_gate_status")), ("VERIFICATION_FAILED", "FAILED"))
        self.assertIn("G5 re-verification", self.defect_line())

    def test_ledger_failure_is_unknown_not_unverified(self):
        self.close_defect()
        ledger = self.sb.root / ".vmodel/state/ledger.jsonl"
        ledger.write_text(ledger.read_text(encoding="utf-8").replace('"status":"PASSED"', '"status":"FAILED"', 1),
                          encoding="utf-8")
        d = self.defect()
        self.assertEqual((d.get("closure_state"), d["verified_by"]), ("UNKNOWN", None))
        self.assertIn("cannot be determined", self.defect_line())
        self.assertIn("closure: UNKNOWN", self.report())

    def test_claim_note_appears_in_the_report(self):
        self.sb.add_defect(self.failed, "G5", related=["REQ-002", *self.failing])
        self.s["wf"].write_text(self.s["good"], encoding="utf-8")
        self.gate_g4()
        self.assertEqual(self.sb.gate("G5")[1]["status"], "PASSED")
        self.assertIn("note: defects.json says open", self.report())

    def test_session_start_context_shows_the_closure_state(self):
        self.close_defect()
        wf = self.s["wf"]
        wf.write_bytes(wf.read_bytes() + b"\n")
        code, out = self.sb.hook("session-start", {"hook_event_name": "SessionStart", "cwd": str(self.sb.root)})
        self.assertEqual(code, 0, out)
        self.assertIn("DEFECT-001 REVERIFY_REQUIRED", out)
        self.assertIn("G5 is now STALE", out)


class DefectClosureBlockedRed(unittest.TestCase):
    def test_blocked_gate_does_not_say_re_verify(self):
        import os
        from helpers import copy_plugin, fail_g5
        sb = Sandbox()
        try:
            sb.plugin = copy_plugin(sb.tmp)
            sb.entry = sb.plugin / "validator" / "vmodel.py"
            s = fail_g5(sb)
            sb.add_defect(s["failed"], "G5", related=["REQ-002", *s["failing"]], status="fixed")
            s["wf"].write_text(s["good"], encoding="utf-8")
            sb.regate_g4()
            self.assertEqual(sb.gate("G5")[1]["status"], "PASSED")
            init_py = sb.plugin / "validator" / "vmodel_validator" / "__init__.py"
            os.chmod(init_py, 0o644)  # a release copy is read-only
            init_py.write_text(init_py.read_text(encoding="utf-8") + "# changed core\n", encoding="utf-8")
            st = sb.status()
            d = st["work_items"][0]["defects"][0]
            self.assertEqual((d.get("closure_state"), d.get("closure_gate_status")), ("REVERIFY_REQUIRED", "BLOCKED"))
            line = [ln.strip() for ln in sb.vm("status", "WI-001")[1].splitlines()
                    if ln.strip().startswith("DEFECT-001")][0]
            self.assertIn("resolve the block", line)
            self.assertNotIn("re-verify", line)
        finally:
            sb.cleanup()


class DefectClosureInvariant(FailedG5Case):
    def test_display_commands_do_not_touch_ledger_or_manifests(self):
        """Closure is display-only: no ledger record, no manifest or gate change from status/lint/report/trace."""
        self.close_defect()
        wf = self.s["wf"]
        wf.write_bytes(wf.read_bytes() + b"\n")  # include a STALE state

        def snapshot():
            state = self.sb.root / ".vmodel/state"
            hashes = {g: self.sb.vm("hash", "WI-001", g)[1].strip() for g in ("G1", "G2", "G3", "G4", "G5")}
            return {"ledger": (state / "ledger.jsonl").read_bytes(), "head": (state / "head.json").read_bytes(),
                    "hashes": hashes, "gates": self.gates()}

        before = snapshot()
        for args in (("status",), ("status", "WI-001", "--json"), ("lint", "WI-001"), ("report", "WI-001"),
                     ("trace", "WI-001"), ("impact", "WI-001")):
            self.sb.vm(*args)
        self.sb.hook("session-start", {"hook_event_name": "SessionStart", "cwd": str(self.sb.root)})
        after = snapshot()
        self.assertEqual(before, after)
        self.assertEqual(json.loads(json.dumps(before["gates"])), {"G1": "PASSED", "G2": "PASSED", "G3": "PASSED",
                                                                    "G4": "STALE", "G5": "STALE",
                                                                    # 0.2.0 REQ-G6-25 (0.1.5: G6 NOT_IMPLEMENTED),
                                                                    # 0.3.0 REQ-G7-17 (0.2.0: G7 NOT_IMPLEMENTED)
                                                                    "G6": "IN_PROGRESS", "G7": "IN_PROGRESS"})


if __name__ == "__main__":
    unittest.main()

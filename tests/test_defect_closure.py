"""v0.1.4 F1: derived defect closure state OPEN / FIX_APPLIED / VERIFIED / CLOSED (D32 option C, D36).

defects.json keeps `open` / `fixed` (the agent's claim). The validator derives the closure from the signed ledger and
the *current* gate state, so a past "verified by" no longer reads as valid once the gate went STALE (drill-3 P-F1).
Class suffixes follow scripts/red_green.py (...Red fails on 0.1.3, ...Invariant passes on both).
"""
from __future__ import annotations

import json
import unittest

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
        """P-F1 reproduced: G4/G5 STALE after the closure -> VERIFIED with the current gate state, not CLOSED."""
        res = self.close_defect()
        wf = self.s["wf"]
        wf.write_bytes(wf.read_bytes() + b"\n")
        g = self.gates()
        self.assertEqual((g["G4"], g["G5"]), ("STALE", "STALE"))
        d = self.defect()
        self.assertEqual((d.get("closure_state"), d.get("closure_gate_status"), d["verified_by"]),
                         ("VERIFIED", "STALE", res["record_id"]))
        line = self.defect_line()
        self.assertTrue(line.startswith("DEFECT-001 VERIFIED"), line)
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
        self.assertEqual(d.get("closure_state"), "VERIFIED")
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
        self.assertEqual(self.defect().get("closure_state"), "VERIFIED")
        report = self.report()
        self.assertIn("closure: VERIFIED", report)
        self.assertIn("G5 is now STALE", report)
        self.assertNotIn("closure: CLOSED", report)

    def test_invalid_or_withheld_verification_is_never_closed(self):
        """Closure follows only valid failure evidence (F3): a PASSED record cited as 'failure', or a verifying PASS
        whose evidence no longer matches the ledger, must not produce VERIFIED/CLOSED."""
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
        self.assertEqual((d.get("closure_state"), d["verified_by"]), ("FIX_APPLIED", None))
        self.assertIn("withheld", self.defect_line())


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
        after = snapshot()
        self.assertEqual(before, after)
        self.assertEqual(json.loads(json.dumps(before["gates"])), {"G1": "PASSED", "G2": "PASSED", "G3": "PASSED",
                                                                    "G4": "STALE", "G5": "STALE",
                                                                    "G6": "NOT_IMPLEMENTED", "G7": "NOT_IMPLEMENTED"})


if __name__ == "__main__":
    unittest.main()

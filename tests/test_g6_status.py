"""Status, verify, trace and report for G6 (REQ-G6-17, 25; display of D41 decision 4)."""
from __future__ import annotations

import unittest

from g6_base import RED, SandboxClass, gate_view, wi_status


class StatusRed(SandboxClass):
    """pipeline, split commands, G1-G5 PASSED, G6 not evaluated."""

    def test_G1_not_evaluated_is_in_progress_with_gate_summary(self):
        w = wi_status(self.sb)
        view = gate_view(self.sb, "G6")
        self.assertEqual(view["status"], "IN_PROGRESS", f"{RED} G6 is implemented: {view}")
        self.assertTrue(view.get("not_evaluated"))
        self.assertEqual(w["status"], "IN_PROGRESS")
        summary = w["gate_summary"]
        self.assertEqual(summary["passed_current"], ["G1", "G2", "G3", "G4", "G5"])
        self.assertEqual(summary["not_evaluated"], ["G6"])
        self.assertEqual(summary["not_implemented"], ["G7"])
        self.assertIn("vmodel gate WI-001 G6", w["next_action"])
        text = self.sb.vm("status")[1]
        self.assertIn("not evaluated yet", text)
        self.assertIn("gates: G1-G5 PASSED (current), G6 not evaluated, G7 not implemented", text)

    def test_G2_required_pass_is_partially_verified(self):
        res = self.g6()
        self.assertEqual(res["status"], "PASSED", f"{RED} {res}")
        w = wi_status(self.sb)
        self.assertEqual(w["status"], "PARTIALLY_VERIFIED")
        self.assertIn("G1-G6 verified", w["next_action"])
        st = self.sb.status()
        self.assertIn("G1-G6", st["mvp_note"])
        self.assertIn("NOT a full V-Model completion", st["mvp_note"])
        text = self.sb.vm("status")[1]
        self.assertIn("IF 2/2 test-level verified", text)  # D44 wording (14b34af: "IF 2/2 covered")
        code, out = self.sb.vm("gate", "WI-001", "G6")
        self.assertIn("applicability: required", out)

    def test_G4_verify_runs_g1_to_g6(self):
        code, res = self.sb.vm_json("verify", "WI-001")
        self.assertEqual([r["gate"] for r in res["results"]], ["G1", "G2", "G3", "G4", "G5", "G6"],
                         f"{RED} {res}")
        self.assertEqual([r["status"] for r in res["results"]], ["PASSED"] * 6)
        self.assertEqual(code, 0)
        self.assertEqual(res["work_item_status"], "PARTIALLY_VERIFIED")

    def test_G6_trace_has_interface_rows_and_integration_results_from_g6(self):
        res = self.g6()
        self.assertEqual(res["status"], "PASSED", f"{RED} {res}")
        code, tv = self.sb.vm_json("trace", "WI-001")
        rows = {r["id"]: r for r in tv.get("interfaces") or []}
        self.assertEqual(set(rows), {"IF-001", "IF-002"}, f"{RED} {tv}")
        self.assertEqual(rows["IF-001"]["tests"]["TEST-010"]["result"], "passed")
        self.assertEqual(rows["IF-001"]["g6_record"], res["record_id"])
        req2 = [r for r in tv["rows"] if r["req"] == "REQ-002"][0]
        self.assertEqual(req2["tests"]["TEST-004"]["result"], "passed")  # unit: from G5
        text = self.sb.vm("trace", "WI-001")[1]
        self.assertIn("IF-001", text)

    def test_G7_preview_names_the_missing_input(self):
        cfg = self.sb.config()
        del cfg["integration_test"]
        self.sb.set_config(cfg)
        self.regate("G4", "G5")
        w = wi_status(self.sb)
        self.assertIn("integration_test", w["next_action"], f"{RED} {w['next_action']}")
        self.assertEqual(w["g6_applicability_preview"]["applicability"], "required")


if __name__ == "__main__":
    unittest.main()

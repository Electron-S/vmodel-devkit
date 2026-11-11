"""Work item completion and display (T13-T16; REQ-G7-17, 18)."""
from __future__ import annotations

import json
import unittest

from g7_base import (CLI_EXIT_BUG, PIPELINE_SYSTEM, PYTEST, RED, G7Class, gate_view, replace_in, states,
                     wi_status)
from helpers import PIPELINE


class StatusRed(G7Class):
    """gradecalc (G6 N/A), system_test configured, G1-G6 PASSED, G7 not evaluated."""

    def test_T15_g6_na_and_g7_pass_complete_the_work_item(self):
        w = wi_status(self.sb)
        self.assertEqual(w["status"], "IN_PROGRESS", f"{RED} G7 not evaluated yet")
        view = gate_view(self.sb, "G7")
        self.assertTrue(view.get("not_evaluated"), f"{RED} {view}")
        self.assertEqual(w["gate_summary"]["not_evaluated"], ["G7"])
        self.assertEqual(w["gate_summary"]["na"], ["G6"])
        self.assertIn("vmodel gate WI-001 G7", w["next_action"])
        res = self.g7()
        self.assertEqual(res["status"], "PASSED", res)
        w = wi_status(self.sb)
        self.assertEqual(w["status"], "COMPLETED")
        self.assertEqual(w["gate_summary"]["passed_current"], ["G1", "G2", "G3", "G4", "G5", "G7"])
        self.assertEqual(w["gate_summary"]["na"], ["G6"])
        self.assertEqual(w["gate_summary"]["not_implemented"], [])
        self.assertIn("all gates passed", w["next_action"])
        self.assertIn("G6 N/A", w["next_action"])
        view = gate_view(self.sb, "G7")
        self.assertEqual(view["acceptance"]["acceptance_criteria"], 6)
        self.assertEqual(view["acceptance"]["verified"], 6)
        st = self.sb.status()
        self.assertIn("G1-G7", st["mvp_note"])
        self.assertIn("not user acceptance", st["mvp_note"])
        text = self.sb.vm("status")[1]
        self.assertIn("WI-001 [COMPLETED]", text)
        self.assertIn("AC 6/6 verified by passed system tests", text)
        report = self.sb.vm("report", "WI-001", "--stdout")[1]
        self.assertIn("Status: **COMPLETED**", report)
        self.assertNotIn("G7, LITE and STRICT profiles are not implemented", report)

    def test_T14_stale_g7_blocks_completion(self):
        res = self.g7()
        self.assertEqual(res["status"], "PASSED", f"{RED} {res}")
        src = self.sb.root / "src/gradecalc/cli.py"
        original = src.read_bytes()
        src.write_bytes(original + b"\n")
        st = states(self.sb)
        self.assertEqual([st[g] for g in ("G3", "G4", "G5", "G6", "G7")], ["PASSED", "STALE", "STALE", "STALE", "STALE"])
        self.assertEqual(wi_status(self.sb)["status"], "IN_PROGRESS")
        self.assertIn("G4 STALE", wi_status(self.sb)["next_action"])
        src.write_bytes(original)
        self.assertEqual(wi_status(self.sb)["status"], "COMPLETED")
        # a system test file change alone
        t = self.sb.root / "tests/system/test_api_system.py"
        t.write_bytes(t.read_bytes() + b"\n")
        self.assertEqual(states(self.sb)["G7"], "STALE")
        t.write_bytes(t.read_bytes()[:-1])
        # the G2 review replaced (only G6 depends on review files): G6 STALE, so G7 no longer stands on a PASS
        self.sb.review("G2", extra={**(self.review_extra("G2") or {}), "summary": "G2 re-reviewed"})
        self.assertEqual(self.sb.gate("G2")[1]["status"], "PASSED")
        st = states(self.sb)
        self.assertEqual((st["G5"], st["G6"], st["G7"]), ("PASSED", "STALE", "STALE"))
        self.assertNotEqual(wi_status(self.sb)["status"], "COMPLETED")
        self.assertTrue(any("upstream G6" in n for n in gate_view(self.sb, "G7")["notes"]))

    def test_T16_failed_or_blocked_g7_blocks_completion(self):
        replace_in(self.sb.root / "src/gradecalc/cli.py", *CLI_EXIT_BUG)
        self.regate("G4", "G5", "G6")
        res = self.g7()
        self.assertEqual(res["status"], "FAILED", f"{RED} {res}")
        w = wi_status(self.sb)
        self.assertEqual(w["status"], "IN_PROGRESS")
        self.assertIn("G7 FAILED: run /vmodel:rework", w["next_action"])
        self.assertEqual(w["gate_summary"]["failed"], ["G7"])
        self.sb.restore()
        cfg = self.sb.config()
        cfg["system_test"]["argv"] = [*PYTEST, "tests/system"]  # no {junit}
        self.sb.set_config(cfg)
        self.regate("G4", "G5", "G6")
        res = self.g7()
        self.assertEqual(res.get("blocked_reason"), "misconfigured", res)
        w = wi_status(self.sb)
        self.assertEqual(w["status"], "BLOCKED")
        self.assertIn("configure-tests --system", w["next_action"])

    def test_verify_runs_g1_to_g7(self):
        code, res = self.sb.vm_json("verify", "WI-001")
        self.assertEqual([r["gate"] for r in res["results"]], ["G1", "G2", "G3", "G4", "G5", "G6", "G7"],
                         f"{RED} {res}")
        self.assertEqual([r["status"] for r in res["results"]], ["PASSED"] * 7)
        self.assertEqual(res["work_item_status"], "COMPLETED")
        self.assertEqual(code, 0)
        out = self.sb.vm("gate", "WI-001", "G7")[1]
        self.assertIn("G7.AC_COVERAGE", out)
        self.assertIn("WI-001 G7 PASSED", out)


class PipelineRed(G7Class):
    """pipeline (two components, G6 required) with the system test overlay; integration and system commands split."""
    fixture = PIPELINE
    overlay = PIPELINE_SYSTEM
    integration = "tests/integration"
    na_endpoints = None

    def test_T13_g1_to_g7_passed_is_completed(self):
        self.assertEqual(gate_view(self.sb, "G6").get("applicability"), "required")
        res = self.g7()
        self.assertEqual(res["status"], "PASSED", f"{RED} {json.dumps(res, ensure_ascii=False)[:3000]}")
        self.assertEqual(self.check(res, "G7.AC_COVERAGE")["status"], "pass")
        w = wi_status(self.sb)
        self.assertEqual(w["status"], "COMPLETED")
        self.assertEqual(w["gate_summary"]["passed_current"], ["G1", "G2", "G3", "G4", "G5", "G6", "G7"])
        code, v = self.sb.vm_json("verify", "WI-001")
        self.assertEqual(([r["status"] for r in v["results"]], v["work_item_status"], code),
                         (["PASSED"] * 7, "COMPLETED", 0))

    def test_G6_scope_fails_when_the_integration_command_runs_system_tests(self):
        cfg = self.sb.config()
        cfg["integration_test"]["argv"] = [*PYTEST, "tests/integration", "tests/system", "--junitxml={junit}"]
        self.sb.set_config(cfg)
        self.regate("G4", "G5")
        res = self.sb.gate("G6")[1]
        self.assertEqual(res["status"], "FAILED", f"{RED} {res}")
        items = self.check(res, "G6.SCOPE")["items"]
        self.assertIn("TEST-020: system test executed by the integration_test command (it belongs to G7)", items)


if __name__ == "__main__":
    unittest.main()

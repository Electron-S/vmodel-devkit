"""Requirement <-> system test traceability and staleness (T05, T18; REQ-G7-09, 10, 19, 24)."""
from __future__ import annotations

import json
import unittest

from g7_base import (RED, G7Class, justify_test_change, ledger_record, ledger_records, remove_function, replace_in,
                     states, wi_status)
from helpers import Sandbox


class TraceRed(G7Class):
    """gradecalc, system_test configured, G1-G6 PASSED."""

    def test_T05_system_test_not_mapped_by_name_fails_ac_coverage(self):
        replace_in(self.sb.root / "tests/system/test_api_system.py", "def test_TEST_105_api_rejects_invalid_score(",
                   "def test_api_rejects_invalid_score(")
        justify_test_change(self.sb, "tests/system/test_api_system.py", "TEST-105", reqs=("REQ-002",))
        self.regate("G4", "G5", "G6")
        res = self.g7()
        self.assertEqual(res["status"], "FAILED", f"{RED} {res}")
        self.assertEqual(self.check(res, "G7.TEST_MAPPING")["items"], ["TEST-105: not executed"])
        self.assertIn("AC-002-2 (REQ-002): TEST-105 not executed", self.check(res, "G7.AC_COVERAGE")["items"])
        rec = ledger_record(self.sb, res["record_id"])
        self.assertTrue(any("test_api_rejects_invalid_score" in c for c in rec["unmapped_cases"]))
        self.assertFalse(rec["requirements_coverage"]["REQ-002"]["acceptance_criteria"]["AC-002-2"]["verified"])

    def test_trace_and_report_show_req_ac_system_test_results(self):
        res = self.g7()
        self.assertEqual(res["status"], "PASSED", f"{RED} {res}")
        code, tv = self.sb.vm_json("trace", "WI-001")
        self.assertEqual(tv.get("system_results_from"), res["record_id"], f"{RED} {tv}")
        req1 = [r for r in tv["rows"] if r["req"] == "REQ-001"][0]
        self.assertEqual(req1["tests"]["TEST-101"], {"level": "system", "result": "passed"})
        self.assertEqual(req1["tests"]["TEST-001"]["result"], "passed")  # unit: from G5
        acc = {a["ac"]: a for a in tv["acceptance"]}
        self.assertEqual(acc["AC-001-2"], {"req": "REQ-001", "ac": "AC-001-2", "tests": {"TEST-102": "passed"},
                                           "verified": True, "state": "verified", "g7_record": res["record_id"]})
        text = self.sb.vm("trace", "WI-001")[1]
        self.assertIn("AC-001-2 (REQ-001): TEST-102(passed) verified", text)
        report = self.sb.vm("report", "WI-001", "--stdout")[1]
        self.assertIn("## Acceptance (system verification)", report)
        self.assertIn("| REQ-001 | AC-001-2 | TEST-102 (passed) | yes |", report)

    def test_T18_requirement_change_restales_g1_to_g7_and_reverifies(self):
        res = self.g7()
        self.assertEqual(res["status"], "PASSED", f"{RED} {res}")
        self.assertEqual(wi_status(self.sb)["status"], "COMPLETED")
        req = self.sb.load("requirements.json")
        req["requirements"][0]["acceptance_criteria"][1]["criterion"] += " (경계값 79는 C)"
        self.sb.save("requirements.json", req)
        self.assertEqual(states(self.sb), {g: "STALE" for g in ("G1", "G2", "G3", "G4", "G5", "G6", "G7")})
        self.assertEqual(wi_status(self.sb)["status"], "IN_PROGRESS")
        code, iv = self.sb.vm_json("impact", "WI-001")
        self.assertIn("REQ-001", iv["changed_items"])
        self.assertIn("TEST-102", iv["impacted_items"])
        self.assertIn("G7", iv["stale_gates"])
        # the change needs a CR (G1.CHANGE_CONTROL), then every gate is re-evaluated, G7 runs the system tests again
        path = self.sb.wi_dir / "change-requests.json"
        path.write_text(json.dumps({"work_item": "WI-001", "change_requests": [
            {"id": "CR-001", "description": "AC-001-2 문구 보강", "reason": "경계값 명시", "affected": ["REQ-001", "AC-001-2"],
             "status": "applied"}]}, ensure_ascii=False), encoding="utf-8")
        self.regate("G1", "G2", "G3", "G4", "G5", "G6")
        again = self.g7()
        self.assertEqual(again["status"], "PASSED", again)
        self.assertNotEqual(again["record_id"], res["record_id"])
        self.assertEqual(wi_status(self.sb)["status"], "COMPLETED")


class NfrWithoutSystemTestRed(G7Class):
    """gradecalc where the non-functional REQ-003 has no system test (G3 does not require one)."""

    @classmethod
    def mutate(cls, sb: Sandbox, gate: str) -> None:
        if gate == "G3":
            tests = sb.load("tests.json")
            tests["tests"] = [t for t in tests["tests"] if t["id"] != "TEST-106"]
            sb.save("tests.json", tests)
        if gate == "G4":
            remove_function(sb.root / "tests/system/test_cli_system.py", "test_TEST_106_cli_error_message_is_korean")

    def test_T05_non_functional_ac_without_system_test_is_a_warning(self):
        res = self.g7()
        self.assertEqual(res["status"], "PASSED", f"{RED} {res}")
        cov = self.check(res, "G7.AC_COVERAGE")
        self.assertEqual(cov["status"], "warn")
        self.assertTrue(any(i.startswith("AC-003-1 (REQ-003, non-functional)") for i in cov["items"]), cov)
        self.assertEqual(wi_status(self.sb)["status"], "COMPLETED")
        w = [g for g in wi_status(self.sb)["gates"] if g["gate"] == "G7"][0]
        self.assertEqual(w["acceptance"]["not_system_tested"], ["AC-003-1"])
        self.assertTrue(all(r.get("type") != "gate" or r["gate"] != "G7" or r["status"] == "PASSED"
                            for r in ledger_records(self.sb)))


if __name__ == "__main__":
    unittest.main()

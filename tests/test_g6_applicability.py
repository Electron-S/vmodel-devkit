"""G6 N/A only when every condition is confirmed (T10, T11; REQ-G6-14-17, 22)."""
from __future__ import annotations

import json
import unittest

from g6_base import (RED, SINGLE_ENDPOINTS, SandboxClass, applicability, gate_view, ledger_record, wi_status)
from helpers import SINGLE


class NaBase(SandboxClass):
    """single (one component, no IF, no integration spec), default config, G1-G5 PASSED with N/A-confirming reviews."""
    fixture = SINGLE
    split = False
    na_reviews = True

    def rereview(self, gate: str, extra: dict | None) -> dict:
        self.sb.review(gate, extra=extra)
        res = self.sb.gate(gate)[1]
        assert res["status"] == "PASSED", res
        return res


class NaRed(NaBase):
    def test_T10_confirmed_single_component_is_na(self):
        code, res = self.sb.gate("G6")
        self.assertEqual((res["status"], res.get("applicability")), ("PASSED", "not_applicable"),
                         f"{RED} confirmed N/A: {res}")
        self.assertEqual(code, 0)
        self.assertEqual(res["evidence"], [])
        self.assertFalse((self.sb.root / ".vmodel/evidence/WI-001/G6").exists())
        self.assertEqual(self.check(res, "G6.EXECUTION")["status"], "skip")
        rec = ledger_record(self.sb, res["record_id"])
        self.assertEqual(rec["executed_tests"], {})
        basis = rec["applicability_basis"]
        self.assertEqual(basis["interfaces"], 0)
        self.assertEqual(sorted(basis["external_endpoints"]), sorted(SINGLE_ENDPOINTS))
        code, text = self.sb.vm("gate", "WI-001", "G6")
        self.assertIn("N/A", text)
        self.assertNotIn("integration tests passed", text.lower())
        view = gate_view(self.sb, "G6")
        self.assertEqual((view["status"], view.get("applicability"), view.get("display_status")),
                         ("PASSED", "not_applicable", "N/A"))
        w = wi_status(self.sb)
        # 0.3.0 (REQ-G7-17/18): G7 is not evaluated yet, so IN_PROGRESS and the next step is G7 (0.2.0:
        # PARTIALLY_VERIFIED, next action "G1-G5 PASSED, G6 N/A ...")
        self.assertEqual(w["status"], "IN_PROGRESS")
        self.assertEqual(w["gate_summary"]["na"], ["G6"])
        self.assertIn("G7", w["next_action"])
        self.assertNotIn("G1-G5 verified", w["next_action"])
        self.assertNotIn("G1-G6 verified", w["next_action"])
        code, text = self.sb.vm("status")
        self.assertIn("N/A", text)
        self.sb.vm("report", "WI-001")
        report = (self.sb.root / ".vmodel/reports/WI-001.md").read_text(encoding="utf-8")
        self.assertIn("N/A", report)
        self.assertNotIn("integration tests passed", report.lower())

    def test_Cb_only_g2_confirmed_blocks(self):
        self.rereview("G3", None)
        res = self.g6()
        self.assertEqual((res["status"], res.get("blocked_reason")), ("BLOCKED", "applicability_unconfirmed"),
                         f"{RED} G3 review did not confirm: {res}")
        self.assertTrue(any("G3" in i for i in self.check(res, "G6.APPLICABILITY")["items"]))

    def test_Cc_only_g3_confirmed_blocks(self):
        self.rereview("G2", None)
        res = self.g6()
        self.assertEqual((res["status"], res.get("blocked_reason")), ("BLOCKED", "applicability_unconfirmed"),
                         f"{RED} {res}")

    def test_Cd_blank_reason_blocks(self):
        self.rereview("G2", applicability(SINGLE_ENDPOINTS, reason="  "))
        res = self.g6()
        self.assertEqual(res.get("blocked_reason"), "applicability_unconfirmed", f"{RED} {res}")

    def test_Ce_unsubmitted_review_edit_blocks(self):
        path = self.sb.wi_dir / "reviews" / "G2.json"
        doc = json.loads(path.read_text(encoding="utf-8"))
        doc["integration_applicability"]["reason"] += " (edited after the PASS)"
        path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
        res = self.g6()
        self.assertEqual(res.get("blocked_reason"), "applicability_unconfirmed", f"{RED} {res}")

    def test_Cg2_external_endpoint_not_reviewed_blocks(self):
        self.rereview("G2", applicability(SINGLE_ENDPOINTS[:1]))
        res = self.g6()
        self.assertEqual(res.get("blocked_reason"), "applicability_unconfirmed", f"{RED} {res}")
        self.assertIn("결과 출력", json.dumps(self.check(res, "G6.APPLICABILITY"), ensure_ascii=False))

    def test_Cg_data_flow_to_another_component_blocks(self):
        arch = self.sb.load("architecture.json")
        arch["data_flows"].append({"from": "ARCH-001", "to": "ARCH-009", "data": "숨은 연동"})
        self.sb.save("architecture.json", arch)
        self.regate("G2", "G3", "G4", "G5")
        res = self.g6()
        self.assertEqual(res.get("blocked_reason"), "applicability_unconfirmed", f"{RED} {res}")
        self.assertIn("ARCH-009", json.dumps(self.check(res, "G6.APPLICABILITY")))

    def test_Ch_review_change_after_na_stales_only_g6(self):
        res = self.g6()
        self.assertEqual(res.get("applicability"), "not_applicable", f"{RED} {res}")
        self.rereview("G2", applicability(SINGLE_ENDPOINTS, reason="다시 검토한 사유"))
        st = {g["gate"]: g["status"] for g in wi_status(self.sb)["gates"]}
        self.assertEqual(st, {"G1": "PASSED", "G2": "PASSED", "G3": "PASSED", "G4": "PASSED", "G5": "PASSED",
                              "G6": "STALE", "G7": "IN_PROGRESS"})  # 0.3.0 REQ-G7-17 (0.2.0: NOT_IMPLEMENTED)

    def test_Cf_integration_spec_without_interface_is_required(self):
        tests = self.sb.load("tests.json")
        tests["tests"].append({"id": "TEST-005", "level": "integration", "title": "모듈 연동", "category": "normal",
                               "verifies": ["ARCH-001"], "procedure": "p", "expected": "e"})
        self.sb.save("tests.json", tests)
        (self.sb.root / "tests/integration").mkdir()
        (self.sb.root / "tests/integration/test_flow.py").write_text(
            "from meanstat.stats import mean\n\n\ndef test_TEST_005_flow():\n    assert mean([2, 4]) == 3\n",
            encoding="utf-8")
        self.regate("G3", "G4", "G5")
        res = self.g6()
        self.assertEqual((res["status"], res.get("blocked_reason")), ("BLOCKED", "misconfigured"),
                         f"{RED} an integration spec makes G6 required: {res}")
        self.assertEqual(self.check(res, "G6.APPLICABILITY")["data"]["applicability"], "required")


class NaRemovalRed(NaBase):
    """T11: an interface that passed G2 once cannot disappear into N/A without a justified removal."""
    upto = None

    @classmethod
    def build(cls, sb):
        super().build(sb)
        for g in ("G1", "G2"):
            sb.prepare(g)
        arch = json.loads((sb.wi_dir / "architecture.json").read_text(encoding="utf-8"))
        arch["interfaces"] = [{"id": "IF-001", "name": "mean API", "provider": "ARCH-001", "consumers": ["EXTERNAL"],
                               "description": "mean(values)", "signature": "def mean(values: list[float]) -> float"}]
        arch["integration_test_strategy"]["interfaces_covered"] = ["IF-001"]
        sb.save("architecture.json", arch)
        for g in ("G1", "G2"):
            sb.review(g)
            assert sb.gate(g)[1]["status"] == "PASSED"
        sb.put_artifact("architecture.json")  # IF-001 removed again, no CR yet
        from g6_base import advance
        advance(sb, "G5", na=True)

    def test_T11_interface_removed_without_justification_blocks(self):
        res = self.g6()
        self.assertEqual((res["status"], res.get("blocked_reason")), ("BLOCKED", "applicability_unconfirmed"),
                         f"{RED} IF-001 vanished without removed_ids: {res}")
        self.assertIn("IF-001", json.dumps(self.check(res, "G6.APPLICABILITY")))

    def test_T11_justified_removal_with_confirmed_reviews_is_na(self):
        self.sb.save("change-requests.json", {"work_item": "WI-001", "change_requests": [{
            "id": "CR-001", "description": "외부 API(IF-001) 제공을 범위에서 뺌", "reason": "사용자 결정: 라이브러리 내부용",
            "affected": ["ARCH-001"], "removed_ids": ["IF-001"], "status": "applied"}]})
        self.regate("G4", "G5")
        res = self.g6()
        self.assertEqual((res["status"], res.get("applicability")), ("PASSED", "not_applicable"), f"{RED} {res}")
        basis = ledger_record(self.sb, res["record_id"])["applicability_basis"]
        self.assertEqual(basis["removed_interfaces"], {"IF-001": ["CR-001"]})

    def test_T11_justified_removal_without_review_confirmation_blocks(self):
        self.sb.save("change-requests.json", {"work_item": "WI-001", "change_requests": [{
            "id": "CR-001", "description": "IF-001 제거", "reason": "범위 축소", "affected": ["ARCH-001"],
            "removed_ids": ["IF-001"], "status": "applied"}]})
        self.regate("G4", "G5")
        self.rereview("G2", None)
        res = self.g6()
        self.assertEqual(res.get("blocked_reason"), "applicability_unconfirmed", f"{RED} {res}")


if __name__ == "__main__":
    unittest.main()

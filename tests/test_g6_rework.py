"""G6 failure, defect, rework and scope removal (T12, T13; REQ-G6-21, 23, 24, 34)."""
from __future__ import annotations

import json
import shutil
import unittest

from g6_base import RED, SandboxClass, applicability, ledger_record, ledger_records, wi_status

ENDPOINTS = ["사용자 입력 파일", "사용자 터미널"]


class ReworkBase(SandboxClass):
    """pipeline, split commands, G1-G5 PASSED."""

    def break_consumer(self) -> None:
        rp = self.sb.root / "src/pipeline/report.py"
        self.good_report = rp.read_text(encoding="utf-8")
        rp.write_text(self.good_report.replace(
            "    records = parse(text)\n",
            "    try:\n        records = parse(text)\n    except ValueError:\n        records = []\n"), encoding="utf-8")
        self.regate("G4", "G5")

    def fail_g6(self) -> dict:
        self.break_consumer()
        res = self.g6()
        self.assertEqual(res["status"], "FAILED", f"{RED} {res}")
        return res

    def defect(self) -> dict:
        return wi_status(self.sb)["defects"][0]


class ReworkRed(ReworkBase):
    def test_T13_failure_defect_fix_reverify_closes(self):
        failed = self.fail_g6()
        res = self.g6()
        self.assertEqual((res["status"], res["recorded"]), ("BLOCKED", False))
        self.assertTrue(any("rework record missing" in r for r in res["reasons"]), res)
        self.sb.add_defect(failed["record_id"], "G6", phase="P4", related=["IF-001", "TEST-011"],
                           fix_scope=["src/pipeline/report.py"])
        d = self.defect()
        self.assertEqual(d["closure_state"], "OPEN")
        self.assertEqual(d["failing_tests"], ["TEST-011"])
        (self.sb.root / "src/pipeline/report.py").write_text(self.good_report, encoding="utf-8")
        self.regate("G4", "G5")
        res = self.g6()
        self.assertEqual(res["status"], "PASSED", res)
        d = self.defect()
        self.assertEqual((d["closure_state"], d["verified_by"]), ("CLOSED", res["record_id"]))
        self.assertIn(f"verified by {res['record_id']}", self.sb.vm("status")[1])

    def test_F3_partial_run_failure_splits_failing_and_unknown(self):
        cfg = self.sb.config()
        cfg["integration_test"]["argv"] = ["{python}", "-m", "pytest", "-q", "-p", "no:cacheprovider",
                                           "tests/integration/test_pipeline.py::test_TEST_011_parser_error_reaches_report",
                                           "--junitxml={junit}"]
        self.sb.set_config(cfg)
        failed = self.fail_g6()
        self.sb.add_defect(failed["record_id"], "G6", related=["IF-001", "TEST-011"])
        d = self.defect()
        self.assertEqual(d["failing_tests"], ["TEST-011"])
        self.assertEqual(d["unknown_tests"], ["TEST-010", "TEST-012"])
        self.assertEqual([c["test_results"] for c in d["citations"]], ["partial"])

    def test_F7_misconfigured_block_is_neutral(self):
        cfg = self.sb.config()
        del cfg["integration_test"]
        self.sb.set_config(cfg)
        self.regate("G4", "G5")
        for _ in range(3):
            res = self.g6()
            self.assertEqual(res.get("blocked_reason"), "misconfigured", f"{RED} {res}")
        self.sb.split_tests()
        self.regate("G4", "G5")
        res = self.g6()  # no DEFECT needed after a neutral block, and no 3-strike count
        self.assertEqual(res["status"], "PASSED", res)
        self.assertIn("first G6 run", self.check(res, "G6.NO_WEAKENING")["detail"])

    def test_T12_scope_removed_by_change_request_is_out_of_scope_not_closed(self):
        failed = self.fail_g6()
        self.sb.add_defect(failed["record_id"], "G6", phase="P2", related=["IF-001", "TEST-011"],
                           fix_scope=[".vmodel/work-items/WI-001/architecture.json"])
        last_g5 = [r for r in ledger_records(self.sb) if r.get("gate") == "G5" and r["status"] == "PASSED"][-1]
        # the user decides the report CLI and the parser become one component: no interface is left
        arch = self.sb.load("architecture.json")
        arch["components"] = [{"id": "ARCH-001", "name": "pipeline", "responsibility": "파싱과 요약",
                               "requirements": ["REQ-001", "REQ-002"], "location": "src/pipeline"}]
        arch["interfaces"] = []
        arch["data_flows"] = [{"from": "사용자 입력 파일", "to": "ARCH-001", "data": "점수 텍스트"},
                              {"from": "ARCH-001", "to": "사용자 터미널", "data": "JSON 요약"}]
        arch["integration_test_strategy"] = {"approach": "단일 컴포넌트", "interfaces_covered": []}
        self.sb.save("architecture.json", arch)
        design = self.sb.load("design.json")
        for u in design["units"]:
            u["component"] = "ARCH-001"
        self.sb.save("design.json", design)
        tests = self.sb.load("tests.json")
        tests["tests"] = [t for t in tests["tests"] if t["level"] != "integration"]
        self.sb.save("tests.json", tests)
        shutil.rmtree(self.sb.root / "tests/integration")
        (self.sb.root / "src/pipeline/report.py").write_text(self.good_report, encoding="utf-8")
        self.sb.save("change-requests.json", {"work_item": "WI-001", "change_requests": [{
            "id": "CR-001", "description": "parser와 report를 한 컴포넌트로 합침", "reason": "사용자 결정: 통합 경계 없음",
            "affected": ["ARCH-001"], "removed_ids": ["IF-001", "IF-002", "TEST-010", "TEST-011", "TEST-012"],
            "status": "applied",
            "test_changes": [{"file": "tests/integration/test_pipeline.py", "since_record": last_g5["record_id"],
                              "reason": "통합 대상이 없어짐", "requirements": ["REQ-001", "REQ-002"],
                              "impact": "통합 테스트 삭제"}]}]})
        for g in ("G2", "G3"):
            self.sb.review(g, extra=applicability(ENDPOINTS))
            self.assertEqual(self.sb.gate(g)[1]["status"], "PASSED")
        self.regate("G4", "G5")
        res = self.g6()
        self.assertEqual((res["status"], res.get("applicability")), ("PASSED", "not_applicable"), res)
        d = self.defect()
        self.assertEqual(d["closure_state"], "OUT_OF_SCOPE", d)
        self.assertIsNone(d["verified_by"])
        self.assertEqual(d["verification_history"], [])
        self.assertIn("CR-001", json.dumps(d["scope_removal"]))
        self.assertIn("IF-001", json.dumps(d["scope_removal"]))
        self.assertEqual(ledger_record(self.sb, failed["record_id"])["status"], "FAILED")  # history kept
        text = self.sb.vm("status")[1]
        self.assertIn("OUT_OF_SCOPE", text)
        self.assertNotIn("verified by", text)


if __name__ == "__main__":
    unittest.main()

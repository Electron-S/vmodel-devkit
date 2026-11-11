"""Gate state machine and G1-G5 checks (T01-T11, T13, T14 and gate rules)."""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

from helpers import GATES, Sandbox, has_pytest


class GateTestBase(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox()
        self.sb.init()
        self.assertEqual(self.sb.new_wi(), "WI-001")

    def tearDown(self):
        self.sb.cleanup()

    def check(self, res: dict, cid: str) -> dict:
        found = [c for c in res.get("checks") or [] if c["id"] == cid]
        self.assertTrue(found, f"{cid} not in {json.dumps(res, indent=1, ensure_ascii=False)[:3000]}")
        return found[0]


class HappyPath(GateTestBase):
    def test_T01_T05_full_flow_partially_verified(self):
        self.sb.advance("G5")
        st = self.sb.status()["work_items"][0]
        # 0.2.0 (REQ-G6-25, D41 decision 4): G6 is implemented and not evaluated yet, so the work item is IN_PROGRESS
        # (0.1.5: PARTIALLY_VERIFIED, gates PASSED x5 + NOT_IMPLEMENTED x2). G1-G5 stay PASSED.
        self.assertEqual(st["status"], "IN_PROGRESS")
        # 0.3.0 (REQ-G7-17): G7 is implemented and not evaluated either (0.2.0: G7 NOT_IMPLEMENTED)
        self.assertEqual([g["status"] for g in st["gates"]],
                         ["PASSED"] * 5 + ["IN_PROGRESS", "IN_PROGRESS"])
        self.assertEqual(st["gate_summary"]["passed_current"], ["G1", "G2", "G3", "G4", "G5"])
        self.assertEqual(st["gate_summary"]["not_evaluated"], ["G6", "G7"])  # 0.2.0: ["G6"]
        # 0.3.0 (REQ-G7-18): COMPLETED is reachable now (0.2.0 note: "NOT a full V-Model completion")
        self.assertIn("COMPLETED only when G1-G7 are PASSED", self.sb.status()["mvp_note"])

    def test_verify_reexecutes_everything(self):
        self.sb.advance("G5")
        code, res = self.sb.vm_json("verify", "WI-001")
        # 0.2.0 (REQ-G6-02): verify now runs G6 too; this work item has an interface (IF-001) but the project has no
        # integration_test command, so G6 is BLOCKED (misconfigured) without running anything
        # (0.1.5: exit 0, PASSED x5, PARTIALLY_VERIFIED).
        self.assertEqual(code, 3, res)
        self.assertEqual([r["status"] for r in res["results"]], ["PASSED"] * 5 + ["BLOCKED"])
        self.assertEqual(res["results"][5]["blocked_reason"], "misconfigured")
        self.assertEqual(res["results"][5]["evidence"], [])
        self.assertEqual(len(res["results"][4]["evidence"]), 1)  # tests were executed again
        self.assertEqual(res["work_item_status"], "BLOCKED")

    def test_T14_state_restored_in_new_process(self):
        self.sb.advance("G3")
        first = self.sb.status()
        second = self.sb.status()  # a brand-new validator process reads only files
        self.assertEqual(first["work_items"], second["work_items"])
        self.assertEqual(self.sb.gate_status("G3"), "PASSED")
        self.assertEqual(self.sb.gate_status("G4"), "IN_PROGRESS")


class ReviewRules(GateTestBase):
    def setUp(self):
        super().setUp()
        self.sb.put_artifact("requirements.json")

    def test_missing_review_is_review_required_by_verifier(self):
        code, res = self.sb.gate("G1")
        self.assertEqual((code, res["status"]), (4, "REVIEW_REQUIRED"))
        self.assertEqual(res["review_required_by"], ["vmodel:verifier"])

    def test_stale_review_after_artifact_change(self):
        self.sb.review("G1")
        rq = self.sb.load("requirements.json")
        rq["requirements"][0]["description"] += " (수정)"
        self.sb.save("requirements.json", rq)
        code, res = self.sb.gate("G1")
        self.assertEqual(res["status"], "REVIEW_REQUIRED")
        self.assertIn("re-review", self.check(res, "G1.REVIEW")["detail"])

    def test_reject_fails_gate(self):
        self.sb.review("G1", verdict="reject",
                       findings=[{"id": "F-1", "severity": "major", "description": "AC 모호", "status": "open"}])
        code, res = self.sb.gate("G1")
        self.assertEqual((code, res["status"]), (1, "FAILED"))

    def test_wrong_reviewer_identity_fails(self):
        self.sb.review("G1", reviewer="main-session", submit=False)
        code, out = self.sb.vm("review-submit", "WI-001", "G1")
        self.assertEqual(code, 1, out)  # the validator refuses to register it
        code, res = self.sb.gate("G1")
        self.assertEqual(res["status"], "FAILED")

    def test_unsubmitted_review_file_is_not_accepted(self):
        self.sb.review("G1", submit=False)  # e.g. a review file planted by the main session
        code, res = self.sb.gate("G1")
        self.assertEqual(res["status"], "REVIEW_REQUIRED")
        self.assertIn("not submitted", self.check(res, "G1.REVIEW")["detail"])

    def test_review_submit_refuses_outdated_review(self):
        self.sb.review("G1")
        rq = self.sb.load("requirements.json")
        rq["requirements"][0]["title"] += " v2"
        self.sb.save("requirements.json", rq)
        code, out = self.sb.vm("review-submit", "WI-001", "G1")
        self.assertEqual(code, 1, out)
        self.assertIn("review again", out)

    def test_approve_with_open_major_finding_fails(self):
        self.sb.review("G1", findings=[{"id": "F-1", "severity": "major", "description": "x", "status": "open"}])
        self.assertEqual(self.sb.gate("G1")[1]["status"], "FAILED")

    def test_critical_issue_needs_user(self):
        rq = self.sb.load("requirements.json")
        rq["open_issues"].append({"id": "ISSUE-002", "description": "개인정보 저장 여부", "critical": True,
                                  "status": "open"})
        self.sb.save("requirements.json", rq)
        self.sb.review("G1")
        code, res = self.sb.gate("G1")
        self.assertEqual(res["status"], "REVIEW_REQUIRED")
        self.assertEqual(res["review_required_by"], ["user"])

    def test_critical_issue_resolved_without_user_fails(self):
        rq = self.sb.load("requirements.json")
        rq["open_issues"][0]["decided_by"] = "orchestrator"
        self.sb.save("requirements.json", rq)
        self.sb.review("G1")
        self.assertEqual(self.sb.gate("G1")[1]["status"], "FAILED")


class MechanicalChecks(GateTestBase):
    def test_T10_missing_required_artifact_blocks_gate(self):
        code, res = self.sb.gate("G1")
        self.assertEqual(res["status"], "FAILED")
        self.assertIn("requirements.json: required artifact missing", self.check(res, "G1.SCHEMA")["items"])

    def test_T10_missing_architecture_and_prereq(self):
        code, res = self.sb.gate("G2")  # G1 not passed yet
        self.assertEqual((code, res["status"], res["recorded"]), (3, "BLOCKED", False))
        self.assertIn("G1 must be PASSED", res["reasons"][0])
        self.sb.advance("G1")
        code, res = self.sb.gate("G2")
        self.assertEqual(res["status"], "FAILED")
        self.assertIn("architecture.json: required artifact missing", self.check(res, "G2.SCHEMA")["items"])

    def test_missing_acceptance_criteria(self):
        self.sb.put_artifact("requirements.json")
        rq = self.sb.load("requirements.json")
        rq["requirements"][1]["acceptance_criteria"] = []
        self.sb.save("requirements.json", rq)
        self.sb.review("G1")
        res = self.sb.gate("G1")[1]
        self.assertEqual(res["status"], "FAILED")
        self.assertEqual(self.check(res, "G1.ACCEPTANCE")["items"], ["REQ-002"])

    def test_unresolved_conflict_fails(self):
        self.sb.put_artifact("requirements.json")
        rq = self.sb.load("requirements.json")
        rq["conflict_analysis"]["conflicts"] = [{"ids": ["REQ-001", "REQ-002"], "description": "x",
                                                 "status": "open", "resolution": ""}]
        self.sb.save("requirements.json", rq)
        self.sb.review("G1")
        self.assertEqual(self.check(self.sb.gate("G1")[1], "G1.CONFLICTS")["status"], "fail")

    def test_ambiguity_is_only_a_warning(self):
        self.sb.put_artifact("requirements.json")
        rq = self.sb.load("requirements.json")
        rq["requirements"][0]["description"] = "적절히 빠르게 단어를 센다"
        self.sb.save("requirements.json", rq)
        self.sb.review("G1")
        res = self.sb.gate("G1")[1]
        self.assertEqual(res["status"], "PASSED")
        self.assertEqual(self.check(res, "G1.AMBIGUITY")["status"], "warn")

    def test_T11_broken_traceability_g2(self):
        self.sb.advance("G1")
        self.sb.put_artifact("architecture.json")
        ar = self.sb.load("architecture.json")
        ar["components"][1]["requirements"] = ["REQ-001", "REQ-099"]  # REQ-002 unmapped + dangling REQ-099
        self.sb.save("architecture.json", ar)
        self.sb.review("G2")
        res = self.sb.gate("G2")[1]
        self.assertEqual(res["status"], "FAILED")
        items = self.check(res, "G2.REQ_MAPPING")["items"]
        self.assertIn("REQ-002", items)
        self.assertTrue(any("REQ-099" in i for i in items))

    def test_T11_broken_traceability_g3(self):
        self.sb.advance("G2")
        self.sb.prepare("G3")
        ts = self.sb.load("tests.json")
        ts["tests"][0]["verifies"] = ["DESIGN-042"]  # dangling, and DESIGN-001 loses its normal test
        self.sb.save("tests.json", ts)
        self.sb.review("G3")
        res = self.sb.gate("G3")[1]
        self.assertEqual(res["status"], "FAILED")
        self.assertTrue(any("DESIGN-042" in i for i in self.check(res, "G3.TRACE")["items"]))
        self.assertIn("DESIGN-001: no normal-case unit test", self.check(res, "G3.UNIT_TESTS")["items"])
        code, out = self.sb.vm("trace", "WI-001")
        self.assertEqual(code, 1)
        self.assertIn("TEST-001 -> DESIGN-042", out)

    def test_g3_requires_abnormal_and_system_tests(self):
        self.sb.advance("G2")
        self.sb.prepare("G3")
        ts = self.sb.load("tests.json")
        ts["tests"] = [t for t in ts["tests"] if t["id"] not in ("TEST-009", "TEST-012")]
        self.sb.save("tests.json", ts)
        self.sb.review("G3")
        res = self.sb.gate("G3")[1]
        self.assertIn("DESIGN-003: declares errors but has no abnormal unit test",
                      self.check(res, "G3.UNIT_TESTS")["items"])
        self.assertIn("AC-002-1 (REQ-002): no system test spec",
                      self.check(res, "G3.INTEGRATION_SYSTEM_TESTS")["items"])

    def test_project_unique_ids_across_work_items(self):
        self.sb.put_artifact("requirements.json")
        wi2 = self.sb.new_wi("두 번째", "다른 기능")
        self.sb.put_artifact("requirements.json", wi=wi2)
        p = self.sb.root / ".vmodel" / "work-items" / wi2 / "requirements.json"
        rq = json.loads(p.read_text(encoding="utf-8"))
        rq["work_item"] = wi2
        p.write_text(json.dumps(rq), encoding="utf-8")
        self.sb.wi = wi2
        self.sb.review("G1")
        res = self.sb.gate("G1")[1]
        self.assertEqual(res["status"], "FAILED")
        self.assertTrue(any("already used by WI-001" in i for i in self.check(res, "G1.IDS")["items"]))
        code, out = self.sb.vm("next-id", "REQ")
        self.assertEqual(out.strip(), "REQ-004")

    def test_change_control_requires_cr(self):
        self.sb.advance("G1")
        rq = self.sb.load("requirements.json")
        rq["requirements"][1]["description"] = "top_n은 빈도 내림차순으로 최대 n개를 반환한다 (변경)"
        self.sb.save("requirements.json", rq)
        self.assertEqual(self.sb.gate_status("G1"), "STALE")
        code, iv = self.sb.vm_json("impact", "WI-001")
        self.assertEqual(iv["changed_items"], ["REQ-002"])
        self.sb.review("G1")
        res = self.sb.gate("G1")[1]
        self.assertEqual(self.check(res, "G1.CHANGE_CONTROL")["items"], ["REQ-002"])
        self.sb.add_defect(res["record_id"], "G1", phase="P1")
        self.sb.save("change-requests.json", {"work_item": "WI-001", "change_requests": [
            {"id": "CR-001", "description": "정렬 규칙 변경", "reason": "사용자 요청", "affected": ["REQ-002"],
             "status": "applied"}]})
        self.assertEqual(self.sb.gate("G1")[1]["status"], "PASSED")


@unittest.skipUnless(has_pytest(), "pytest not installed for this interpreter")
class ImplementationAndUnitVerification(GateTestBase):
    def test_T04_design_conformance(self):
        self.sb.advance("G3")
        self.sb.put_code()
        (self.sb.root / "src/textstats/wordfreq.py").write_text(
            "from collections import Counter\n\ndef count_words(text):\n    return {}\n", encoding="utf-8")
        self.sb.review("G4")
        res = self.sb.gate("G4")[1]
        self.assertEqual(res["status"], "FAILED")
        self.assertIn("DESIGN-003: function 'top_n' not defined in src/textstats/wordfreq.py",
                      self.check(res, "G4.DESIGN_CONFORMANCE")["items"])
        self.assertIn("REQ-002", self.check(res, "G4.REQ_IMPLEMENTED")["items"])

    def test_g4_syntax_error_and_missing_test_code(self):
        self.sb.advance("G3")
        self.sb.put_code()
        t = self.sb.root / "tests/test_wordfreq.py"
        t.write_text(t.read_text(encoding="utf-8").replace("test_TEST_009", "test_nine") + "\ndef broken(:\n",
                     encoding="utf-8")
        self.sb.review("G4")
        res = self.sb.gate("G4")[1]
        self.assertEqual(self.check(res, "G4.SYNTAX")["status"], "fail")
        self.assertIn("TEST-009", self.check(res, "G4.TEST_CODE")["items"])  # unparsable file proves nothing

    def test_g4_lint_missing_blocks_without_user_choice(self):
        sb = Sandbox()
        try:
            sb.init("--lint", "none")  # no syntax-only permission
            sb.new_wi()
            sb.advance("G3")
            sb.put_code()
            sb.review("G4")
            code, res = sb.gate("G4")
            self.assertEqual((code, res["status"], res["blocked_reason"]), (3, "BLOCKED", "tool_unavailable"))
        finally:
            sb.cleanup()

    def test_g4_lint_executed_with_evidence(self):
        import shutil
        if not shutil.which("ruff"):
            self.skipTest("ruff not installed")
        sb = Sandbox()
        try:
            sb.init("--lint", "ruff")
            sb.new_wi()
            sb.advance("G3")
            sb.put_code()
            (sb.root / "src/textstats/wordfreq.py").write_text(
                (sb.root / "src/textstats/wordfreq.py").read_text(encoding="utf-8") + "\nimport os\n",
                encoding="utf-8")
            sb.review("G4")
            res = sb.gate("G4")[1]
            lint = self.check(res, "G4.LINT")
            self.assertEqual(lint["status"], "fail")
            self.assertTrue(res["evidence"])
        finally:
            sb.cleanup()

    def test_T05_evidence_contents(self):
        self.sb.git("init", "-q")
        self.sb.git("add", "-A")
        self.sb.git("commit", "-qm", "base")
        self.sb.advance("G5")
        st = self.sb.status()
        rec_path = [g for g in st["work_items"][0]["gates"] if g["gate"] == "G5"][0]
        code, res = self.sb.vm_json("verify", "WI-001", "G5")
        ev = self.sb.root / res["results"][0]["evidence"][0]["path"]
        rec = json.loads(ev.read_text(encoding="utf-8"))
        for key in ("work_item", "gate", "command", "executable", "runtime", "started_at", "finished_at",
                    "exit_code", "files", "git", "manifest_hash", "validator", "sig", "verified_files"):
            self.assertIn(key, rec)
        self.assertEqual((rec["work_item"], rec["gate"], rec["exit_code"]), ("WI-001", "G5", 0))
        self.assertIn("--junitxml=", " ".join(rec["command"]))
        self.assertTrue(rec["executable"]["resolved"])
        self.assertEqual(len(rec["git"]["head"]), 40)
        self.assertTrue(rec["git"]["dirty"])  # code added after the commit: dirty tree is allowed, hashed
        import hashlib
        raw = (ev.parent / "stdout.bin").read_bytes()
        self.assertEqual(rec["files"]["stdout.bin"]["sha256"], "sha256:" + hashlib.sha256(raw).hexdigest())
        self.assertIn("src/textstats/wordfreq.py", rec["verified_files"])
        self.assertIsNotNone(rec_path)
        code, out = self.sb.vm("audit")
        self.assertEqual(code, 0, out)

    def test_T06_failing_test_blocks_g5(self):
        self.sb.advance("G4")
        wf = self.sb.root / "src/textstats/wordfreq.py"
        wf.write_text(wf.read_text(encoding="utf-8").replace("(-kv[1], kv[0])", "(kv[1], kv[0])"), encoding="utf-8")
        self.sb.review("G4")
        self.assertEqual(self.sb.gate("G4")[1]["status"], "PASSED")
        code, res = self.sb.gate("G5")
        self.assertEqual((code, res["status"]), (1, "FAILED"))
        self.assertEqual(self.check(res, "G5.EXECUTION")["status"], "fail")
        self.assertIn("TEST-007: failed", self.check(res, "G5.TEST_MAPPING")["items"])
        self.assertEqual(self.sb.status()["work_items"][0]["status"], "IN_PROGRESS")

    def test_T08_source_change_makes_pass_stale(self):
        self.sb.advance("G5")
        wf = self.sb.root / "src/textstats/wordfreq.py"
        wf.write_text(wf.read_text(encoding="utf-8") + "\n# tweak\n", encoding="utf-8")
        st = self.sb.status()["work_items"][0]
        stat = {g["gate"]: g for g in st["gates"]}
        self.assertEqual([stat[g]["status"] for g in GATES], ["PASSED"] * 3 + ["STALE", "STALE"])
        self.assertIn("changed: src/textstats/wordfreq.py", stat["G5"]["changed_files"])
        self.assertEqual(st["status"], "IN_PROGRESS")
        code, res = self.sb.gate("G5")  # old G4 PASS cannot be reused
        self.assertEqual(res["status"], "BLOCKED")
        self.assertIn("G4 must be PASSED", res["reasons"][0])

    def test_T09_test_change_invalidates_and_needs_justification(self):
        self.sb.advance("G5")
        t = self.sb.root / "tests/test_wordfreq.py"
        t.write_text(t.read_text(encoding="utf-8").replace('[("b", 3), ("a", 2)]', '[("b", 3), ("a", 2)][:2]'),
                     encoding="utf-8")
        self.assertEqual(self.sb.gate_status("G5"), "STALE")
        self.assertEqual(self.sb.gate_status("G4"), "STALE")
        self.sb.review("G4")
        self.assertEqual(self.sb.gate("G4")[1]["status"], "PASSED")
        res = self.sb.gate("G5")[1]
        self.assertEqual(res["status"], "FAILED")
        prev = [c for c in res["checks"] if c["id"] == "G5.NO_WEAKENING"][0]
        self.assertIn("without a test_changes justification", prev["items"][0])
        since = prev["items"][0].split("since_record=")[1].rstrip(")")
        self.sb.add_defect(res["record_id"], "G5", phase="P4", test_changes=[
            {"file": "tests/test_wordfreq.py", "since_record": since, "reason": "슬라이스 명시",
             "requirements": ["REQ-002"], "impact": "의미 변화 없음"}])
        self.sb.regate_g4()
        self.assertEqual(self.sb.gate("G5")[1]["status"], "PASSED")

    def test_deleted_test_is_detected(self):
        self.sb.advance("G5")
        t = self.sb.root / "tests/test_wordfreq.py"
        src = t.read_text(encoding="utf-8")
        cut = src.index("def test_TEST_008")
        end = src.index("def test_TEST_009")
        t.write_text(src[:cut] + src[end:], encoding="utf-8")
        self.sb.review("G4")
        res = self.sb.gate("G4")[1]
        self.assertEqual(res["status"], "FAILED")  # TEST-008 spec has no test code any more
        self.assertEqual(self.check(res, "G4.TEST_CODE")["items"], ["TEST-008"])

    def test_inputs_modified_during_run(self):
        self.sb.advance("G4")
        t = self.sb.root / "tests/test_mutate.py"
        t.write_text("from pathlib import Path\n\ndef test_mutates():\n"
                     "    p = Path('src/textstats/wordfreq.py')\n    p.write_text(p.read_text() + '\\n#x\\n')\n",
                     encoding="utf-8")
        self.sb.review("G4")
        self.assertEqual(self.sb.gate("G4")[1]["status"], "PASSED")
        res = self.sb.gate("G5")[1]
        self.assertEqual(self.check(res, "G5.INPUTS_UNCHANGED")["status"], "fail")

    def test_T13_fail_defect_fix_reverify_pass(self):
        self.sb.advance("G4")
        wf = self.sb.root / "src/textstats/wordfreq.py"
        good = wf.read_text(encoding="utf-8")
        wf.write_text(good.replace("if n <= 0:", "if n < 0:"), encoding="utf-8")
        self.sb.review("G4")
        self.assertEqual(self.sb.gate("G4")[1]["status"], "PASSED")
        res = self.sb.gate("G5")[1]
        self.assertEqual(res["status"], "FAILED")
        failed = res["record_id"]
        # 1) re-evaluation without a defect record is refused
        wf.write_text(good, encoding="utf-8")
        self.sb.review("G4")
        self.assertEqual(self.sb.gate("G4")[1]["status"], "PASSED")
        code, res = self.sb.gate("G5")
        self.assertEqual((res["status"], res["recorded"]), ("BLOCKED", False))
        self.assertIn("rework record missing", res["reasons"][0])
        # 2) record the defect -> G4 re-review (defects.json is reviewed with the code) -> re-verify -> PASS
        self.sb.add_defect(failed, "G5", phase="P4")
        self.assertEqual(self.sb.gate_status("G4"), "STALE")
        self.sb.regate_g4()
        self.assertEqual(self.sb.gate("G5")[1]["status"], "PASSED")
        code, out = self.sb.vm("report", "WI-001")
        report = (self.sb.root / ".vmodel/reports/WI-001.md").read_text(encoding="utf-8")
        self.assertIn("DEFECT-001", report)
        self.assertIn("verified by", report)

    def test_three_identical_failures_block(self):
        self.sb.advance("G4")
        wf = self.sb.root / "src/textstats/wordfreq.py"
        wf.write_text(wf.read_text(encoding="utf-8").replace("if n <= 0:", "if n < 0:"), encoding="utf-8")
        self.sb.review("G4")
        self.sb.gate("G4")
        statuses = []
        for i in range(3):
            res = self.sb.gate("G5")[1]
            statuses.append(res["status"])
            self.sb.add_defect(res["record_id"], "G5")
            self.sb.regate_g4()
        self.assertEqual(statuses, ["FAILED", "FAILED", "BLOCKED"])
        code, res = self.sb.gate("G5")
        self.assertEqual(res["status"], "BLOCKED")
        self.assertTrue(any("3 identical failures" in r for r in res["reasons"]), res["reasons"])
        self.assertEqual(self.sb.gate_status("G5"), "BLOCKED")
        self.assertEqual(self.sb.status()["work_items"][0]["status"], "BLOCKED")
        # an agent (no TTY) cannot unblock
        code, out = self.sb.vm("unblock", "WI-001", "G5", "--reason", "agent tries")
        self.assertEqual(code, 3)
        self.assertIn("needs an interactive terminal", out)

    def test_streak_not_reset_by_review_required(self):
        """FAILED, REVIEW_REQUIRED, FAILED, FAILED with the same cause -> BLOCKED (M1 regression)."""
        self.sb.advance("G3")
        self.sb.put_code()
        wf = self.sb.root / "src/textstats/wordfreq.py"
        good = wf.read_text(encoding="utf-8")
        bad = good.replace("def top_n", "def top_k")
        wf.write_text(bad, encoding="utf-8")
        self.sb.review("G4")
        r1 = self.sb.gate("G4")[1]
        self.sb.add_defect(r1["record_id"], "G4")
        wf.write_text(good, encoding="utf-8")  # fixed, but the review targets older inputs
        r2 = self.sb.gate("G4")[1]
        wf.write_text(bad, encoding="utf-8")  # the same defect comes back
        self.sb.review("G4")
        r3 = self.sb.gate("G4")[1]
        self.sb.add_defect(r3["record_id"], "G4")
        self.sb.review("G4")
        r4 = self.sb.gate("G4")[1]
        self.assertEqual([r["status"] for r in (r1, r2, r3, r4)], ["FAILED", "REVIEW_REQUIRED", "FAILED", "BLOCKED"])

    @unittest.skipUnless(sys.platform != "win32", "pty is POSIX only")
    def test_user_unblock_with_tty(self):
        self.test_three_identical_failures_block()
        out = self.sb.run_tty("unblock", "WI-001", "G5", "--reason", "user reviewed")
        self.assertIn(b"unblocked", out)
        self.assertEqual(self.sb.gate_status("G5"), "FAILED")


if __name__ == "__main__":
    unittest.main()

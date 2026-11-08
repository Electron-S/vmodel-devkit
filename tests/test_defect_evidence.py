"""v0.1.4 F3: failing-TEST evidence of DEFECT records (D35 policy P1; user policies A, B, C of 2026-11-08).

- Only a signed FAILED (or 3-strike BLOCKED) gate record of the same work item is failure evidence; anything else is an
  `invalid_citation` error and is excluded from failing_tests and from the verified_by baseline.
- Per-TEST results: G5 records give failed / UNKNOWN (not executed or no results); G1-G4 records are N/A.
- `evidence_integrity` errors (ledger integrity, evidence files that differ from the ledger) vs trace warnings
  (`unlinked_failing_test`, `unknown_test_result`), with the same names in status, lint and report.
Class suffixes follow scripts/red_green.py (...Red fails on 0.1.3, ...Char passes on both).
"""
from __future__ import annotations

import json
import re
import unittest

from helpers import PLUGIN, Sandbox, has_pytest
from rework_case import FailedG5Case

UNIT_TESTS = [f"TEST-{i:03d}" for i in range(1, 10)]  # unit tests of the wordfreq fixture (TEST-010.. are not unit)


def problems(d: dict, kind: str) -> list[tuple]:
    return sorted((p.get("category"), p.get("record")) for p in d.get(kind) or [])


class DefectEvidenceRed(FailedG5Case):
    def test_unlinked_failing_tests_are_trace_warnings_everywhere(self):
        self.sb.add_defect(self.failed, "G5", related=["REQ-002"])
        d = self.defect()
        self.assertEqual([(w.get("severity"), w.get("category"), w.get("record"), w.get("tests"))
                          for w in d.get("warnings") or []],
                         [("warning", "unlinked_failing_test", self.failed, self.failing)])
        self.assertEqual(d.get("errors"), [])
        self.assertEqual(self.wi().get("defect_checks"), {"errors": 0, "warnings": 1})
        code, out = self.sb.vm("lint", "WI-001")
        self.assertEqual(code, 1, out)
        self.assertIn("WARNING [unlinked_failing_test]", out)
        self.assertIn(f"DEFECT-001 does not link failing test(s) of {self.failed}", out)  # 0.1.3 wording kept
        text = self.status_text()
        self.assertIn("WARNING [unlinked_failing_test]", text)
        self.assertIn("defect checks: 0 error(s), 1 warning(s)", text)
        report = self.report()
        section = report.split("## Defect trace check", 1)[-1].split("\n## ", 1)[0]
        self.assertIn("WARNING [unlinked_failing_test]", section)
        for t in self.failing:
            self.assertIn(t, section)

    def test_passed_record_alone_is_an_invalid_citation(self):
        g4_pass = self.s["g4_pass"]
        self.sb.add_defect(g4_pass, "G4", status="fixed")  # cites the G4 PASS the failed run stood on
        self.s["wf"].write_text(self.s["good"], encoding="utf-8")
        later_g4_pass = self.gate_g4()  # 0.1.3 reported this unrelated PASS as the closure evidence
        d = self.defect()
        self.assertIsNone(d["verified_by"], f"0.1.3 showed {later_g4_pass}")
        self.assertEqual(d["failing_tests"], [])
        self.assertEqual(problems(d, "errors"), [("invalid_citation", g4_pass)])
        self.assertIn("ERROR [invalid_citation]", self.status_text())

    def test_mixed_citation_closes_on_the_failure_gate(self):
        self.sb.add_defect(self.failed, "G5", related=["REQ-002", *self.failing], status="fixed")
        self.s["wf"].write_text(self.s["good"], encoding="utf-8")
        g4_pass = self.gate_g4()
        self.set_defect(found_in_records=[self.failed, g4_pass])  # a PASSED record cited next to the failure
        wrong = self.gate_g4()  # 0.1.3 took the latest cited record (G4) as the baseline -> this G4 PASS
        res = self.sb.gate("G5")[1]
        self.assertEqual(res["status"], "PASSED")
        d = self.defect()
        self.assertEqual(d["verified_by"], res["record_id"], f"not {wrong}")
        self.assertEqual(d.get("closure_gate"), "G5")
        self.assertEqual(problems(d, "errors"), [("invalid_citation", g4_pass)])
        self.assertEqual(d["failing_tests"], self.failing)

    def test_review_required_record_is_an_invalid_citation(self):
        self.s["wf"].write_text(self.s["good"], encoding="utf-8")
        rr = self.sb.gate("G4")[1]  # inputs changed, no new review -> REVIEW_REQUIRED (recorded)
        self.assertEqual((rr["status"], rr["recorded"]), ("REVIEW_REQUIRED", True))
        self.sb.add_defect(rr["record_id"], "G4")
        d = self.defect()
        self.assertEqual(problems(d, "errors"), [("invalid_citation", rr["record_id"])])
        self.assertIn("REVIEW_REQUIRED", " ".join(e.get("detail", "") for e in d.get("errors") or []))

    def test_environment_blocked_record_is_an_invalid_citation(self):
        self.sb.add_defect(self.failed, "G5", related=["REQ-002", *self.failing], status="fixed")
        self.s["wf"].write_text(self.s["good"], encoding="utf-8")
        cfg_path = self.sb.root / ".vmodel/config.json"
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        cfg["unit_test"]["argv"] = [a for a in cfg["unit_test"]["argv"] if "{junit}" not in a]
        cfg_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
        self.gate_g4()
        blk = self.sb.gate("G5")[1]
        self.assertEqual((blk["status"], blk.get("blocked_reason"), blk["recorded"]), ("BLOCKED", "misconfigured", True))
        self.sb.add_defect(blk["record_id"], "G5", did="DEFECT-002")
        d = self.defect("DEFECT-002")
        self.assertEqual(problems(d, "errors"), [("invalid_citation", blk["record_id"])])
        self.assertIsNone(d["verified_by"])

    def test_missing_foreign_and_non_gate_records_share_the_category(self):
        review_id = [r["record_id"] for r in self.ledger_records() if r.get("type") == "review"][0]
        code, out = self.sb.vm("new-wi", "--title", "other", "--request", "other work item")
        self.assertEqual(code, 0, out)
        other = out.strip().splitlines()[-1]
        self.sb.put_artifact("requirements.json", wi=other)  # duplicate ids -> a recorded FAILED G1 of the other WI
        res = self.sb.vm_json("gate", other, "G1")[1]
        self.assertTrue(res["recorded"], res)
        cited = ["R99999", review_id, res["record_id"]]
        self.sb.add_defect("R99999", "G5", did="DEFECT-002")
        self.set_defect("DEFECT-002", found_in_records=cited)
        d = self.defect("DEFECT-002")
        self.assertEqual(problems(d, "errors"), sorted(("invalid_citation", r) for r in cited))
        self.assertEqual(d["unknown_records"], sorted(cited))  # 0.1.3 key kept
        code, out = self.sb.vm("lint", "WI-001")
        self.assertEqual(code, 1, out)
        self.assertEqual(out.count("ERROR [invalid_citation]"), 3, out)

    def test_report_always_has_the_defect_trace_check_section(self):
        report = self.report()
        self.assertIn("## Defect trace check", report)
        section = report.split("## Defect trace check", 1)[1].split("\n## ", 1)[0]
        self.assertRegex(section, r"(?m)^None\b")
        self.assertIn("defect checks: 0 error(s), 0 warning(s)", self.status_text())
        # PARTIALLY_VERIFIED with an unlinked failing test: the gap is still listed in the final report
        self.sb.add_defect(self.failed, "G5", related=["REQ-002", *self.failing[1:]], status="fixed")
        self.s["wf"].write_text(self.s["good"], encoding="utf-8")
        self.gate_g4()
        self.assertEqual(self.sb.gate("G5")[1]["status"], "PASSED")
        self.assertEqual(self.wi()["status"], "PARTIALLY_VERIFIED")
        section = self.report().split("## Defect trace check", 1)[1].split("\n## ", 1)[0]
        self.assertIn("WARNING [unlinked_failing_test]", section)
        self.assertIn(self.failing[0], section)
        self.assertIn("WI-001 [PARTIALLY_VERIFIED]", self.status_text())
        self.assertIn("defect checks: 0 error(s), 1 warning(s)", self.status_text())


@unittest.skipUnless(has_pytest(), "pytest not installed")
class DefectTestResultsRed(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox()
        self.sb.init()
        self.sb.new_wi()

    def tearDown(self):
        self.sb.cleanup()

    def set_argv(self, argv: list[str]) -> None:
        p = self.sb.root / ".vmodel/config.json"
        cfg = json.loads(p.read_text(encoding="utf-8"))
        cfg["unit_test"]["argv"] = argv
        p.write_text(json.dumps(cfg, indent=2), encoding="utf-8")

    def defect(self) -> dict:
        return self.sb.status()["work_items"][0]["defects"][0]

    def defect_line(self) -> str:
        text = self.sb.vm("status", "WI-001")[1]
        return [ln.strip() for ln in text.splitlines() if ln.strip().startswith("DEFECT-001")][0]

    def run_g5(self) -> tuple[dict, list[str], list[str]]:
        self.sb.review("G4")
        self.assertEqual(self.sb.gate("G4")[1]["status"], "PASSED")
        res = self.sb.gate("G5")[1]
        self.assertEqual(res["status"], "FAILED", res)
        items = [c for c in res["checks"] if c["id"] == "G5.TEST_MAPPING"][0]["items"]
        failing = sorted(i.split(":")[0] for i in items if i.endswith((": failed", ": error")))
        unknown = sorted(i.split(":")[0] for i in items if i.endswith(": not executed"))
        return res, failing, unknown

    def test_g5_failure_without_junit_is_unknown_not_dash(self):
        self.sb.advance("G4")
        self.set_argv(["{python}", "-c", "import sys; sys.exit(1)", "{junit}"])  # fails, writes no results
        res, failing, unknown = self.run_g5()
        self.assertEqual((failing, unknown), ([], UNIT_TESTS))
        self.sb.add_defect(res["record_id"], "G5", related=["REQ-001"])
        d = self.defect()
        cit = (d.get("citations") or [{}])[0]
        self.assertEqual((cit.get("test_results"), cit.get("unknown_tests")), ("unknown", UNIT_TESTS))
        self.assertEqual(d["failing_tests"], [])
        self.assertEqual([(w.get("category"), w.get("tests")) for w in d.get("warnings") or []],
                         [("unknown_test_result", UNIT_TESTS)])
        line = self.defect_line()
        self.assertIn("UNKNOWN", line)
        self.assertNotIn("failing tests (ledger): -", line)

    def test_partially_executed_g5_separates_failing_and_unknown(self):
        self.sb.advance("G4")
        argv = json.loads((self.sb.root / ".vmodel/config.json").read_text(encoding="utf-8"))["unit_test"]["argv"]
        self.set_argv([*argv[:3], "-x", *argv[3:]])  # stop at the first failure -> later TESTs never run
        tok = self.sb.root / "src/textstats/tokenizer.py"
        tok.write_text(tok.read_text(encoding="utf-8").replace(".lower()", ""), encoding="utf-8")
        res, failing, unknown = self.run_g5()
        self.assertTrue(failing and unknown, (failing, unknown))
        self.sb.add_defect(res["record_id"], "G5", related=["REQ-001", *failing])
        d = self.defect()
        cit = (d.get("citations") or [{}])[0]
        self.assertEqual((cit.get("test_results"), cit.get("failing_tests"), cit.get("unknown_tests")),
                         ("partial", failing, unknown))
        self.assertEqual(d["failing_tests"], failing)
        self.assertEqual([(w.get("category"), w.get("tests")) for w in d.get("warnings") or []],
                         [("unknown_test_result", unknown)])
        line = self.defect_line()
        self.assertIn(failing[0], line)
        self.assertIn("UNKNOWN", line)

    def test_unknown_results_are_named_in_lint_and_report(self):
        self.sb.advance("G4")
        self.set_argv(["{python}", "-c", "import sys; sys.exit(1)", "{junit}"])
        res, failing, unknown = self.run_g5()
        self.sb.add_defect(res["record_id"], "G5", related=["REQ-001"])
        code, out = self.sb.vm("lint", "WI-001")
        self.assertEqual(code, 1, out)
        self.assertIn("WARNING [unknown_test_result]", out)
        self.sb.vm("report", "WI-001")
        report = (self.sb.root / ".vmodel/reports/WI-001.md").read_text(encoding="utf-8")
        self.assertIn("WARNING [unknown_test_result]", report.split("## Defect trace check", 1)[-1])
        self.assertIn(f"failing tests in {res['record_id']} (from the signed ledger): none; UNKNOWN", report)

    def test_g4_review_reject_is_not_applicable(self):
        self.sb.advance("G3")
        self.sb.put_code()
        self.sb.review("G4", verdict="reject")
        res = self.sb.gate("G4")[1]
        self.assertEqual(res["status"], "FAILED")
        self.sb.add_defect(res["record_id"], "G4", related=["REQ-001"])
        d = self.defect()
        cit = (d.get("citations") or [{}])[0]
        self.assertEqual((cit.get("valid"), cit.get("test_results")), (True, "not_applicable"))
        self.assertEqual((d["failing_tests"], d.get("warnings"), d.get("errors")), ([], [], []))
        line = self.defect_line()
        self.assertIn("N/A", line)
        self.assertNotIn("UNKNOWN", line)


class DefectIntegrityRed(FailedG5Case):
    def test_tampered_failure_evidence_is_an_integrity_error(self):
        self.sb.add_defect(self.failed, "G5", related=["REQ-002", *self.failing])
        ledger = (self.sb.root / ".vmodel/state/ledger.jsonl").read_bytes()
        ev = self.sb.root / self.s["evidence"][0]["path"]
        (ev.parent / "stdout.bin").write_bytes(b"edited output")
        d = self.defect()
        self.assertEqual(problems(d, "errors"), [("evidence_integrity", self.failed)])
        self.assertIn("stdout.bin", " ".join(e.get("detail", "") for e in d["errors"]))
        code, out = self.sb.vm("lint", "WI-001")
        self.assertEqual(code, 1, out)
        self.assertIn("ERROR [evidence_integrity]", out)
        self.assertNotIn("invalid_citation", out)
        code, out = self.sb.vm("audit")
        self.assertEqual(code, 1)
        self.assertIn("stdout.bin content differs", out)
        self.assertEqual((self.sb.root / ".vmodel/state/ledger.jsonl").read_bytes(), ledger)  # nothing rewritten

    def test_tampered_verification_evidence_withholds_closure(self):
        res = self.close_defect()
        self.assertEqual(self.defect()["verified_by"], res["record_id"])
        ev = self.sb.root / res["evidence"][0]["path"]
        (ev.parent / "stdout.bin").write_bytes(b"edited output")
        d = self.defect()
        self.assertEqual((d["verified_by"], d.get("verification_withheld")), (None, res["record_id"]))
        self.assertEqual(problems(d, "errors"), [("evidence_integrity", res["record_id"])])
        self.assertEqual(self.gates()["G5"], "PASSED")  # gate decisions are unchanged; audit reports the tampering
        self.assertEqual(self.sb.vm("audit")[0], 1)

    def test_forged_ledger_is_one_integrity_error_not_invalid_citations(self):
        self.sb.add_defect(self.failed, "G5", related=["REQ-002", *self.failing])
        ledger = self.sb.root / ".vmodel/state/ledger.jsonl"
        lines = ledger.read_text(encoding="utf-8").splitlines()
        forged = {"seq": json.loads(lines[-1])["seq"] + 1, "prev": "sha256:" + "a" * 64,
                  "record": {"type": "gate", "work_item": "WI-001", "gate": "G5", "status": "PASSED",
                             "record_id": "R99999"}, "sig": "hmac-sha256:" + "b" * 64}
        ledger.write_text("\n".join(lines + [json.dumps(forged)]) + "\n", encoding="utf-8")
        w = self.wi()
        self.assertTrue(all(g["status"] in ("BLOCKED", "NOT_IMPLEMENTED") for g in w["gates"]))
        d = w["defects"][0]
        self.assertEqual(problems(d, "errors"), [("evidence_integrity", None)])
        self.assertEqual((d["verified_by"], d["failing_tests"]), (None, []))
        self.assertIn("ERROR [evidence_integrity]", self.status_text())


class DefectEvidenceReviewRed(FailedG5Case):
    """Findings of the independent F3/F1 reviews (2026-11-09), reproduced before the fix."""

    def test_multi_gate_citation_is_not_verified_by_an_upstream_pass(self):
        self.sb.add_defect(self.failed, "G5", related=["REQ-002", *self.failing], status="fixed")
        self.s["wf"].write_text(self.s["good"], encoding="utf-8")
        self.sb.review("G4", verdict="reject")
        g4_fail = self.sb.gate("G4")[1]
        self.assertEqual(g4_fail["status"], "FAILED")
        self.sb.add_defect(g4_fail["record_id"], "G4")  # the same DEFECT recurs at G4
        g4_pass = self.gate_g4()
        d = self.defect()
        self.assertEqual((d["verified_by"], d.get("closure_gate")), (None, "G5"), f"not {g4_pass}")
        res = self.sb.gate("G5")[1]
        self.assertEqual(res["status"], "PASSED")
        self.assertEqual(self.defect()["verified_by"], res["record_id"])

    def test_malformed_evidence_record_is_an_integrity_error_not_a_crash(self):
        self.sb.add_defect(self.failed, "G5", related=["REQ-002", *self.failing])
        record = self.sb.root / self.s["evidence"][0]["path"]
        for content in ("[]", "5", '{"files": ["x"]}', '{"files": {"stdout.bin": "x"}}'):
            record.write_text(content, encoding="utf-8")
            code, st = self.sb.vm_json("status", "WI-001")
            self.assertEqual(code, 0, content)
            d = st["work_items"][0]["defects"][0]
            self.assertIn(("evidence_integrity", self.failed), problems(d, "errors"), content)
            code, out = self.sb.vm("lint", "WI-001")
            self.assertEqual(code, 1, out)
            self.assertIn("ERROR [evidence_integrity]", out)
            code, out = self.sb.vm("report", "WI-001")
            self.assertEqual(code, 0, out)

    def test_duplicate_citations_count_once(self):
        g4_pass = self.s["g4_pass"]
        self.sb.add_defect(self.failed, "G5", related=["REQ-002"])
        self.set_defect(found_in_records=[g4_pass, g4_pass, self.failed, self.failed])
        d = self.defect()
        self.assertEqual(problems(d, "errors"), [("invalid_citation", g4_pass)])
        self.assertEqual(problems(d, "warnings"), [("unlinked_failing_test", self.failed)])

    def test_three_strike_chain_counts_a_missing_link_once(self):
        records = [self.failed]
        for _ in range(2):
            self.sb.add_defect(records[-1], "G5")
            self.sb.regate_g4()
            records.append(self.sb.gate("G5")[1]["record_id"])
        self.sb.add_defect(records[-1], "G5")
        d = self.defect()
        warns = d.get("warnings") or []
        self.assertEqual([(w.get("category"), w.get("records"), w.get("tests")) for w in warns],
                         [("unlinked_failing_test", records, self.failing)])
        self.assertEqual(self.wi().get("defect_checks"), {"errors": 0, "warnings": 1})

    def test_defect_without_citations_is_an_invalid_citation(self):
        self.sb.add_defect(self.failed, "G5", related=["REQ-002", *self.failing])
        self.set_defect(found_in_records=self.failed)  # a string, not a list (schema error too)
        d = self.defect()
        self.assertEqual(problems(d, "errors"), [("invalid_citation", None)])
        self.assertIn("defect checks: 1 error(s)", self.status_text())

    def test_forged_or_truncated_ledger_is_reported_in_lint_and_report(self):
        self.sb.add_defect(self.failed, "G5", related=["REQ-002", *self.failing])
        ledger = self.sb.root / ".vmodel/state/ledger.jsonl"
        lines = ledger.read_text(encoding="utf-8").splitlines()
        ledger.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")  # head/anchor mismatch
        d = self.defect()
        self.assertEqual(problems(d, "errors"), [("evidence_integrity", None)])
        self.assertEqual(d["unknown_records"], [self.failed])  # 0.1.3 value kept
        code, out = self.sb.vm("lint", "WI-001")
        self.assertEqual(code, 1, out)
        self.assertIn("ERROR [evidence_integrity]", out)
        self.assertNotIn("invalid_citation", out)
        section = self.report().split("## Defect trace check", 1)[1]
        self.assertIn("ERROR [evidence_integrity]", section)

    def test_withheld_verification_is_named_in_status_and_report(self):
        res = self.close_defect()
        ev = self.sb.root / res["evidence"][0]["path"]
        (ev.parent / "stdout.bin").write_bytes(b"edited output")
        self.assertIn(f"{res['record_id']} withheld", self.defect_line())
        self.assertIn(f"{res['record_id']} withheld", self.report())

    def test_counts_agree_across_status_lint_and_report(self):
        self.sb.add_defect(self.failed, "G5", related=["REQ-002"])
        self.set_defect(found_in_records=[self.failed, self.s["g4_pass"]])
        self.assertEqual(self.wi().get("defect_checks"), {"errors": 1, "warnings": 1})
        self.assertIn("defect checks: 1 error(s), 1 warning(s)", self.status_text())
        code, out = self.sb.vm("lint", "WI-001")
        self.assertIn("2 problem(s): 1 error(s), 1 warning(s)", out)
        section = self.report().split("## Defect trace check", 1)[1].split("\n## ", 1)[0]
        self.assertEqual((section.count("- ERROR ["), section.count("- WARNING [")), (1, 1))


class DefectEvidenceReviewChar(FailedG5Case):
    def test_clean_defect_lint_exits_zero(self):
        self.close_defect()
        code, out = self.sb.vm("lint", "WI-001")
        self.assertEqual(code, 0, out)
        self.assertIn("lint OK", out)


class SkillReportingRed(unittest.TestCase):
    def test_final_report_steps_carry_errors_and_warnings(self):
        for name in ("start", "rework"):
            text = (PLUGIN / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
            self.assertRegex(text, r"(?s)every ERROR and WARNING.{0,200}defect trace check", name)


class DefectEvidenceChar(FailedG5Case):
    def test_three_strike_blocked_record_is_valid_failure_evidence(self):
        records = [self.failed]
        for _ in range(2):
            self.sb.add_defect(records[-1], "G5")
            self.sb.regate_g4()
            res = self.sb.gate("G5")[1]
            records.append(res["record_id"])
        self.assertEqual(res["status"], "BLOCKED")
        self.assertEqual(res.get("blocked_reason"), "three_consecutive_identical_failures")
        self.sb.add_defect(records[-1], "G5")
        d = self.defect()
        self.assertEqual(d["found_in_records"], records)
        self.assertEqual((d["failing_tests"], d["unknown_records"]), (self.failing, []))
        self.assertEqual(d["failing_tests_by_record"][records[-1]], self.failing)

    def test_invalid_citations_alone_do_not_satisfy_the_rework_precondition(self):
        self.sb.add_defect(self.s["g4_pass"], "G4", status="fixed")
        self.s["wf"].write_text(self.s["good"], encoding="utf-8")
        self.gate_g4()
        code, res = self.sb.gate("G5")
        self.assertEqual((res["status"], res["recorded"]), ("BLOCKED", False))
        self.assertTrue(any(re.search(r"rework record missing: " + self.failed, r) for r in res["reasons"]),
                        res["reasons"])

    def test_status_json_keeps_the_013_defect_keys(self):
        self.sb.add_defect(self.failed, "G5", related=["REQ-002"])
        d = self.defect()
        for key in ("id", "gate", "claimed_status", "root_cause_phase", "found_in_records", "unknown_records",
                    "failing_tests_by_record", "failing_tests", "unlinked_failing_tests", "verified_by"):
            self.assertIn(key, d)
        self.assertEqual((d["failing_tests"], d["unlinked_failing_tests"], d["failing_tests_by_record"]),
                         (self.failing, self.failing, {self.failed: self.failing}))


if __name__ == "__main__":
    unittest.main()

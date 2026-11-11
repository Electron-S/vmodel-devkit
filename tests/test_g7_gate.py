"""G7 System Verification: execution, evidence, results (T01, T02, T06-T10, T19; REQ-G7-03, 04, 08-10).

gradecalc fixture: system tests drive the CLI (python -m gradecalc.cli) and the HTTP API (python -m gradecalc.server)
as separate processes; G6 is N/A (one component, confirmed by the G2/G3 reviews).
"""
from __future__ import annotations

import json
import unittest

from g7_base import (API_STATUS_BUG, BOUNDARY_BUG, CLI_EXIT_BUG, MESSAGE_BUG, PYTEST, RED, SYSTEM_IDS,
                     G7Class, gate_view, ledger_record, replace_in, wi_status)



class GateRed(G7Class):
    """gradecalc, system_test configured, G1-G6 PASSED (G6 N/A)."""

    def seed(self, path: str, bug: tuple[str, str]) -> None:
        replace_in(self.sb.root / path, *bug)
        self.regate("G4", "G5", "G6")

    def test_T01_T09_T10_system_tests_pass_with_signed_evidence(self):
        res = self.g7()
        self.assertEqual(res["status"], "PASSED", f"{RED} {json.dumps(res, ensure_ascii=False)[:2000]}")
        self.assertTrue(res["recorded"])
        for cid in ("G7.PREREQ", "G7.CONFIG", "G7.EXECUTION", "G7.RESULTS", "G7.SCOPE", "G7.TEST_MAPPING",
                    "G7.AC_COVERAGE", "G7.NO_WEAKENING", "G7.INPUTS_UNCHANGED"):
            self.assertEqual(self.check(res, cid)["status"], "pass", cid)
        self.assertFalse([c for c in res["checks"] if c["kind"] == "ai_review"])  # REQ-G7-14: mechanical only
        self.assertEqual(len(res["evidence"]), 1)
        ev_path = self.sb.root / res["evidence"][0]["path"]
        ev = json.loads(ev_path.read_text(encoding="utf-8"))
        self.assertEqual(ev["kind"], "system_test")
        self.assertEqual(ev["command_source"], "system_test")
        self.assertEqual(ev["exit_code"], 0)
        self.assertIn("tests/system", ev["command"])
        self.assertEqual(ev["junit_summary"]["tests"], 6)
        for key in ("config_sha256", "system_test_sha256", "manifest_hash", "git", "verified_files", "environment",
                    "started_at", "finished_at", "executable"):
            self.assertIn(key, ev)
        for name in ("stdout.bin", "stderr.bin", "junit.xml"):
            self.assertTrue(ev["files"][name]["sha256"], name)
        self.assertEqual(ev["validator"]["core_hash"], self.sb.status()["validator"]["core_hash"])
        self.assertEqual(self.sb.vm("verify-evidence", str(ev_path))[0], 0)
        rec = ledger_record(self.sb, res["record_id"])
        self.assertEqual(rec["executed_tests"], {t: "passed" for t in SYSTEM_IDS})  # T09 (CLI) and T10 (API)
        self.assertEqual(set(rec["executed_levels"].values()), {"system"})
        self.assertEqual(rec["system_specs"], SYSTEM_IDS)
        cov = rec["requirements_coverage"]
        self.assertEqual(cov["REQ-001"]["acceptance_criteria"]["AC-001-1"], {"tests": {"TEST-101": "passed"},
                                                                             "verified": True})
        self.assertTrue(all(ac["verified"] for r in cov.values() for ac in r["acceptance_criteria"].values()))
        g5 = [r for r in self.sb.status()["work_items"][0]["gates"] if r["gate"] == "G5"][0]
        self.assertEqual(rec["basis_records"]["G5"], g5["record_id"])
        self.assertEqual(self.sb.vm("audit")[0], 0)

    def test_T08_normal_boundary_error_scenarios_are_recorded_and_judged(self):
        res = self.g7()
        self.assertEqual(res["status"], "PASSED", f"{RED} {res}")
        cov = ledger_record(self.sb, res["record_id"])["requirements_coverage"]
        self.assertEqual(cov["REQ-001"]["categories"], {"normal": ["TEST-101"], "boundary": ["TEST-102"],
                                                        "abnormal": ["TEST-103"]})
        self.assertEqual(cov["REQ-002"]["categories"], {"normal": ["TEST-104"], "abnormal": ["TEST-105"]})
        # an error scenario: the API answers 200 instead of 400 for a bad score
        self.seed("src/gradecalc/server.py", API_STATUS_BUG)
        res = self.g7()
        self.assertEqual(res["status"], "FAILED", res)
        self.assertIn("TEST-105: failed", self.check(res, "G7.TEST_MAPPING")["items"])
        self.assertTrue(any(i.startswith("AC-002-2 (REQ-002)") for i in self.check(res, "G7.AC_COVERAGE")["items"]))
        self.assertEqual(self.check(res, "G7.AC_COVERAGE")["status"], "fail")

    def test_T08_boundary_scenario_failure_fails_g7(self):
        self.seed("src/gradecalc/cli.py", BOUNDARY_BUG)
        res = self.g7()
        self.assertEqual(res["status"], "FAILED", f"{RED} {res}")
        self.assertEqual(self.check(res, "G7.TEST_MAPPING")["items"], ["TEST-102: failed"])
        self.assertEqual([i for i in self.check(res, "G7.AC_COVERAGE")["items"] if i.startswith("AC-")],
                         ["AC-001-2 (REQ-001): TEST-102 failed"])

    def test_T02_real_defect_fails_g7(self):
        self.seed("src/gradecalc/cli.py", CLI_EXIT_BUG)
        res = self.g7()
        self.assertEqual(res["status"], "FAILED", f"{RED} {res}")
        self.assertEqual(self.check(res, "G7.RESULTS")["status"], "fail")
        self.assertEqual(self.check(res, "G7.EXECUTION")["status"], "fail")  # pytest exit 1
        self.assertEqual(sorted(self.check(res, "G7.TEST_MAPPING")["items"]), ["TEST-103: failed", "TEST-106: failed"])
        acs = self.check(res, "G7.AC_COVERAGE")["items"]
        self.assertIn("AC-001-3 (REQ-001): TEST-103 failed", acs)
        rec = ledger_record(self.sb, res["record_id"])
        self.assertTrue(rec["failure_signature"])
        self.assertEqual({t: s for t, s in rec["executed_tests"].items() if s != "passed"},
                         {"TEST-103": "failed", "TEST-106": "failed"})
        self.assertTrue(any("TEST_103" in c for c in rec["failed_cases"]))
        self.assertEqual(gate_view(self.sb, "G7")["failing_tests"], ["TEST-103", "TEST-106"])

    def test_T19_korean_output_of_a_failed_run_is_readable(self):
        self.seed("src/gradecalc/cli.py", MESSAGE_BUG)
        res = self.g7()
        self.assertEqual(res["status"], "FAILED", f"{RED} {res}")
        self.assertEqual(self.check(res, "G7.TEST_MAPPING")["items"], ["TEST-106: failed"])
        self.assertIn("AC-003-1 (REQ-003, non-functional): TEST-106 failed", self.check(res, "G7.AC_COVERAGE")["items"])
        results = self.check(res, "G7.RESULTS")["items"]
        self.assertTrue(any("점수는 0에서 100 사이의 정수여야 합니다" in i for i in results), results)
        tail = self.check(res, "G7.EXECUTION")["items"]
        self.assertTrue(any("오류" in i for i in tail), tail)  # raw stdout decoded (UTF-8 here, CP949 on Windows)
        out = self.sb.vm("gate", "WI-001", "G7")[1]
        self.assertIn("rework record missing", out)  # the failure needs a DEFECT first (rework precondition)

    def test_T06_fake_pass_files_are_not_evidence(self):
        fake = self.sb.root / ".vmodel/evidence/WI-001/G7/20260101T000000Z-system-fake"
        fake.mkdir(parents=True)
        (fake / "record.json").write_text(json.dumps({"gate": "G7", "status": "PASSED", "exit_code": 0}), encoding="utf-8")
        (fake / "junit.xml").write_text('<testsuite tests="6">' + "".join(
            f'<testcase classname="tests.system" name="test_{t.replace("-", "_")}_ok"/>' for t in SYSTEM_IDS)
            + "</testsuite>", encoding="utf-8")
        (self.sb.wi_dir / "g7-result.json").write_text(json.dumps({"gate": "G7", "status": "PASSED"}), encoding="utf-8")
        view = gate_view(self.sb, "G7")
        self.assertTrue(view.get("not_evaluated"), f"{RED} {view}")
        self.assertNotEqual(wi_status(self.sb)["status"], "COMPLETED")
        code, out = self.sb.vm("verify-evidence", str(fake / "record.json"))
        self.assertNotEqual(code, 0)
        self.assertIn("not referenced by the signed ledger", out)
        res = self.g7()  # the validator runs the system tests itself; the planted files play no part
        self.assertEqual(res["status"], "PASSED", res)
        self.assertNotIn("system-fake", res["evidence"][0]["path"])

    def test_T06_exit_zero_without_junit_is_not_a_pass(self):
        self.set_system_argv(["{python}", "-c", "print('ALL SYSTEM TESTS PASSED')", "{junit}"])
        self.regate("G4", "G5", "G6")
        res = self.g7()
        self.assertEqual(res["status"], "FAILED", f"{RED} {res}")
        ex = self.check(res, "G7.EXECUTION")
        self.assertEqual(ex["status"], "fail")
        self.assertIn("junit.xml was not produced", ex["detail"])
        self.assertEqual(self.check(res, "G7.RESULTS")["status"], "fail")
        self.assertIn("TEST-101: not executed", self.check(res, "G7.TEST_MAPPING")["items"])

    def test_T07_no_test_collected_fails(self):
        (self.sb.root / "tests/system_empty").mkdir()
        (self.sb.root / "tests/system_empty/README.txt").write_text("no tests here\n", encoding="utf-8")
        self.set_system_argv([*PYTEST, "tests/system_empty", "--junitxml={junit}"])
        self.regate("G4", "G5", "G6")
        res = self.g7()
        self.assertEqual(res["status"], "FAILED", f"{RED} {res}")
        self.assertEqual(self.check(res, "G7.EXECUTION")["status"], "fail")  # pytest exit 5
        self.assertEqual(self.check(res, "G7.RESULTS")["detail"], "0 tests executed")

    def test_T07_exit_zero_with_empty_junit_fails(self):
        self.set_system_argv(["{python}", "-c", "import sys; open(sys.argv[1], 'w').write('<testsuite tests=\"0\"/>')",
                              "{junit}"])
        self.regate("G4", "G5", "G6")
        res = self.g7()
        self.assertEqual(res["status"], "FAILED", f"{RED} {res}")
        self.assertEqual(self.check(res, "G7.EXECUTION")["status"], "pass")  # exit 0 and a junit file ...
        self.assertEqual(self.check(res, "G7.RESULTS")["detail"], "0 tests executed")  # ... are not a PASS
        self.assertEqual(self.check(res, "G7.AC_COVERAGE")["status"], "fail")

    def test_a_process_left_running_by_a_system_test_neither_hangs_nor_times_out_g7(self):
        # design review M1: a child that inherited the test run's stdout/stderr (a server a test forgot to stop).
        # Its cwd is outside the project: on Windows the validator does not kill leftovers (documented, D49), and a
        # process whose cwd is the sandbox would keep the next test from restoring it (Windows run of 1deef79)
        (self.sb.root / "tests/system/conftest.py").write_text(
            "import subprocess\nimport sys\nimport tempfile\n\n"
            "LEFTOVER = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(40)'], "
            "cwd=tempfile.gettempdir())\n", encoding="utf-8")
        self.set_system_argv([*PYTEST, "tests/system", "--junitxml={junit}"], timeout_s=20)
        self.regate("G4", "G5", "G6")
        res = self.g7()
        self.assertEqual(res["status"], "PASSED", f"{RED} {json.dumps(res, ensure_ascii=False)[:2000]}")
        ev = json.loads((self.sb.root / res["evidence"][0]["path"]).read_text(encoding="utf-8"))
        self.assertFalse(ev["timed_out"])
        self.assertLess(ev["duration_s"], 20)

    def test_command_that_cannot_start_is_blocked_tool_unavailable(self):
        self.set_system_argv(["vmodel-no-such-runner-xyz", "{junit}"])
        self.regate("G4", "G5", "G6")
        res = self.g7()
        self.assertEqual(res.get("blocked_reason"), "tool_unavailable", f"{RED} {res}")
        self.assertEqual(res["status"], "BLOCKED")
        self.assertTrue(res["recorded"])


if __name__ == "__main__":
    unittest.main()

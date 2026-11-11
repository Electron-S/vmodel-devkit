"""Unit / integration / system separation (T04; REQ-G7-05, 06, 07)."""
from __future__ import annotations

import json
import unittest

from g7_base import PYTEST, RED, SYSTEM_IDS, G7Class, ledger_record, remove_function, set_test_commands, wi_status


class ScopeRed(G7Class):
    """gradecalc, system_test configured, G1-G6 PASSED."""

    def test_T04_system_command_running_the_unit_command_fails(self):
        self.set_system_argv(list(self.sb.config()["unit_test"]["argv"]))  # the unit command reused as system test
        self.regate("G4", "G5", "G6")
        res = self.g7()
        self.assertEqual(res["status"], "FAILED", f"{RED} {res}")
        scope = self.check(res, "G7.SCOPE")
        self.assertEqual(scope["status"], "fail")
        self.assertIn("TEST-001: unit test executed by the system_test command (it belongs to G5)", scope["items"])
        mapping = self.check(res, "G7.TEST_MAPPING")["items"]
        self.assertEqual(sorted(mapping), [f"{t}: not executed" for t in SYSTEM_IDS])
        self.assertEqual(self.check(res, "G7.AC_COVERAGE")["status"], "fail")

    def test_T04_system_command_on_the_unit_folder_fails(self):
        self.set_system_argv([*PYTEST, "tests/unit", "--junitxml={junit}"])
        self.regate("G4", "G5", "G6")
        res = self.g7()
        self.assertEqual(res["status"], "FAILED", f"{RED} {res}")
        self.assertEqual(self.check(res, "G7.SCOPE")["status"], "fail")
        self.assertEqual(self.check(res, "G7.RESULTS")["status"], "pass")  # the unit tests themselves pass ...
        self.assertEqual(self.check(res, "G7.EXECUTION")["status"], "pass")  # ... with exit code 0

    def test_G5_scope_fails_when_the_unit_command_runs_system_tests(self):
        cfg = self.sb.config()
        cfg["unit_test"]["argv"] = [*PYTEST, "--junitxml={junit}"]  # forgot --ignore=tests/system
        self.sb.set_config(cfg)
        self.regate("G4")
        res = self.sb.gate("G5")[1]
        self.assertEqual(res["status"], "FAILED", f"{RED} {res}")
        items = self.check(res, "G5.SCOPE")["items"]
        self.assertIn("TEST-101: system test executed by the unit_test command (it belongs to G7)", items)


class ScopeChar(G7Class):
    """Behaviour 0.2.0 already has: moving a unit test into the system folder under a system id fails at G4."""

    def test_T04_unit_test_relabelled_as_system_test_fails_g4(self):
        unit = self.sb.root / "tests/unit/test_cli.py"
        remove_function(unit, "test_TEST_004_cli_prints_grade")
        system = self.sb.root / "tests/system/test_cli_system.py"
        remove_function(system, "test_TEST_101_cli_prints_grade")
        system.write_text(system.read_text(encoding="utf-8") + '''

def test_TEST_101_cli_prints_grade(capsys):
    from gradecalc.cli import main

    assert main(["95"]) == 0
    assert capsys.readouterr().out.strip() == "95 A"
''', encoding="utf-8")
        self.sb.review("G4")
        res = self.sb.gate("G4")[1]  # the unit spec lost its test function (G4.TEST_CODE, unchanged rule)
        self.assertEqual(res["status"], "FAILED", res)
        code = [c for c in res["checks"] if c["id"] == "G4.TEST_CODE"][0]
        self.assertEqual(code["status"], "fail")
        self.assertTrue(any("TEST-004" in i for i in code["items"]), code)


class MixedRed(G7Class):
    """gradecalc as a 0.2.0 project: the unit command runs the system tests too, no system_test; G1-G6 PASSED."""
    mode = "mixed"

    def test_G5_no_weakening_accepts_system_tests_moving_to_g7(self):
        g5 = [g for g in wi_status(self.sb)["gates"] if g["gate"] == "G5"][0]
        self.assertEqual(sorted(t for t in ledger_record(self.sb, g5["record_id"])["executed_tests"]
                                if t.startswith("TEST-1")), SYSTEM_IDS)
        set_test_commands(self.sb, "system")  # the user separates the system tests (configure-tests --system)
        self.regate("G4")
        res = self.sb.gate("G5")[1]
        self.assertEqual(res["status"], "PASSED", f"{RED} {json.dumps(res, ensure_ascii=False)[:3000]}")
        self.regate("G6")
        self.assertEqual(self.g7()["status"], "PASSED")

    def test_status_warns_that_the_unit_command_ran_system_tests(self):
        warnings = wi_status(self.sb)["scope_warnings"]
        self.assertTrue(any("system test" in w and "TEST-101" in w for w in warnings), f"{RED} {warnings}")
        report = self.sb.vm("report", "WI-001", "--stdout")[1]
        self.assertIn("system_test", report)


if __name__ == "__main__":
    unittest.main()

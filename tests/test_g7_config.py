"""system_test configuration, init and configure-tests (T03; REQ-G7-01, 02, 20, 21)."""
from __future__ import annotations

import json
import os
import shutil
import unittest

from g7_base import GRADECALC, PYTEST, RED, G7Class, gate_view, ledger_records, wi_status
from helpers import Sandbox, has_pytest


class ConfigRed(G7Class):
    """gradecalc, the unit command ignores tests/system but no system_test is configured; G1-G6 PASSED."""
    mode = "nosystem"

    def test_T03_missing_system_test_blocks_without_running_anything(self):
        g5_dirs = sorted((self.sb.root / ".vmodel/evidence/WI-001/G5").iterdir())
        res = self.g7()
        self.assertTrue(res["recorded"], f"{RED} G7 must be evaluated and recorded: {res}")
        self.assertEqual(res["status"], "BLOCKED")
        self.assertEqual(res["blocked_reason"], "misconfigured")
        self.assertEqual(self.check(res, "G7.CONFIG")["status"], "blocked")
        self.assertEqual(res["evidence"], [])
        self.assertEqual(self.g7_evidence_dirs(), [])  # nothing was executed, not even the unit command
        self.assertEqual(sorted((self.sb.root / ".vmodel/evidence/WI-001/G5").iterdir()), g5_dirs)
        w = wi_status(self.sb)
        self.assertEqual(w["status"], "BLOCKED")
        self.assertIn("configure-tests --system", w["next_action"])
        self.assertIn("never used instead", w["next_action"])

    def test_T03_preview_names_the_missing_command_before_the_first_evaluation(self):
        w = wi_status(self.sb)
        self.assertIn("configure-tests --system", w["next_action"], f"{RED} {w['next_action']}")
        self.assertTrue(gate_view(self.sb, "G7").get("not_evaluated"))
        self.assertEqual(w["status"], "IN_PROGRESS")

    def test_T03_invalid_system_test_blocks_misconfigured(self):
        for argv, drop in ((f"{PYTEST}", False),  # argv is a string
                           ([*PYTEST, "tests/system"], False),  # no {junit}
                           ([*PYTEST, "tests/system", "--junitxml={junit}"], True)):  # no timeout_s
            self.sb.restore()
            self.set_system_argv(argv, drop_timeout=drop)
            self.regate("G4", "G5", "G6")
            res = self.g7()
            self.assertEqual(res.get("blocked_reason"), "misconfigured", f"{RED} {argv} {res}")
            self.assertEqual(res["evidence"], [])
            self.assertEqual(self.g7_evidence_dirs(), [])

    def test_T03_misconfigured_block_needs_no_defect_and_is_not_counted(self):
        for _ in range(4):  # a neutral block: no DEFECT, no 3-strike count
            res = self.g7()
            self.assertEqual(res.get("blocked_reason"), "misconfigured", f"{RED} {res}")


class NoSystemTestsYetRed(G7Class):
    """gradecalc where the system tests were never written (G4 does not judge system tests): G1-G6 PASSED."""
    mode = "nosystem"

    @classmethod
    def mutate(cls, sb: Sandbox, gate: str) -> None:
        if gate == "G4":
            shutil.rmtree(sb.root / "tests/system")

    def test_next_action_asks_for_the_system_tests_before_the_command(self):
        w = wi_status(self.sb)
        nxt = w["next_action"]
        self.assertIn("G7 needs system tests", nxt, f"{RED} {nxt}")
        self.assertIn("TEST-101", nxt)
        self.assertIn("tests/system/", nxt)
        self.assertIn("configure-tests --system", nxt)  # the user step comes after the tests exist
        self.assertEqual(w["g7_preview"]["missing_functions"],
                         ["TEST-101", "TEST-102", "TEST-103", "TEST-104", "TEST-105", "TEST-106"])
        res = self.g7()
        self.assertEqual(res.get("blocked_reason"), "misconfigured")
        self.assertIn("G7 needs system tests", wi_status(self.sb)["next_action"])


@unittest.skipUnless(has_pytest(), "pytest not installed")
class InitRed(unittest.TestCase):
    """init registers an existing tests/system folder as system_test and keeps it out of the unit command."""

    def setUp(self):
        self.sb = Sandbox(fixture=GRADECALC)
        self.sb.put_code()

    def tearDown(self):
        self.sb.cleanup()

    def test_init_registers_tests_system(self):
        self.sb.init()
        cfg = self.sb.config()
        self.assertIn("system_test", cfg, f"{RED} {cfg}")
        self.assertEqual(cfg["system_test"]["argv"], [*PYTEST, "tests/system", "--junitxml={junit}"])
        self.assertIn("--ignore=tests/system", cfg["unit_test"]["argv"])
        self.assertTrue(cfg["system_test"]["timeout_s"] > 0)

    def test_init_refuses_overlapping_integration_and_system_paths(self):
        code, out = self.sb.vm("init", "--project", str(self.sb.root), "--lint", "none", "--allow-syntax-only",
                               "--integration-tests", "tests/system", "--system-tests", "tests/system")
        self.assertNotEqual(code, 0)
        self.assertIn("overlap", out, f"{RED} {out}")
        self.assertFalse((self.sb.root / ".vmodel/config.json").exists())

    def test_init_refuses_a_system_path_without_tests(self):
        (self.sb.root / "tests/empty").mkdir()
        code, out = self.sb.vm("init", "--project", str(self.sb.root), "--lint", "none", "--allow-syntax-only",
                               "--system-tests", "tests/empty")
        self.assertNotEqual(code, 0)
        self.assertIn("system test path tests/empty has no test function", out, f"{RED} {out}")



@unittest.skipUnless(has_pytest(), "pytest not installed")
class InitChar(unittest.TestCase):
    """Without a tests/system folder nothing is registered (same as 0.2.0)."""

    def setUp(self):
        self.sb = Sandbox(fixture=GRADECALC)
        self.sb.put_code()
        shutil.rmtree(self.sb.root / "tests/system")

    def tearDown(self):
        self.sb.cleanup()

    def test_init_without_system_folder_leaves_system_test_out(self):
        self.sb.init()
        cfg = self.sb.config()
        self.assertNotIn("system_test", cfg)
        self.assertNotIn("--ignore=tests/system", cfg["unit_test"]["argv"])


@unittest.skipUnless(has_pytest() and os.name == "posix", "pytest and a POSIX pty are needed")
class ConfigureTestsRed(unittest.TestCase):
    """configure-tests --system (user only, TTY) on an existing project."""

    def setUp(self):
        self.sb = Sandbox(fixture=GRADECALC)
        self.sb.init()  # before the code exists: nothing to register yet
        self.sb.put_code()

    def tearDown(self):
        self.sb.cleanup()

    def test_configure_tests_system_writes_a_signed_record_then_the_config(self):
        before = len(ledger_records(self.sb))
        out = self.sb.run_tty("configure-tests", "--system", "tests/system").decode("utf-8", "replace")
        cfg = self.sb.config()
        self.assertIn("system_test", cfg, f"{RED} {out}")
        self.assertIn("--ignore=tests/system", cfg["unit_test"]["argv"])
        recs = ledger_records(self.sb)[before:]
        self.assertEqual([r["type"] for r in recs], ["config"])
        self.assertEqual(recs[0]["change"], "system_test")
        self.assertEqual(recs[0]["system_path"], "tests/system")

    def test_configure_tests_refuses_unit_scope_and_overlap(self):
        out = self.sb.run_tty("configure-tests", "--system", "tests").decode("utf-8", "replace")
        self.assertIn("same scope as the unit test command", out, f"{RED} {out}")
        self.assertNotIn("system_test", self.sb.config())
        (self.sb.root / "tests/integration").mkdir()
        (self.sb.root / "tests/integration/test_x.py").write_text("def test_x():\n    pass\n", encoding="utf-8")
        self.sb.run_tty("configure-tests", "--integration", "tests/integration")
        self.assertIn("integration_test", self.sb.config())
        out = self.sb.run_tty("configure-tests", "--system", "tests/integration").decode("utf-8", "replace")
        self.assertIn("overlap", out, f"{RED} {out}")
        self.assertNotIn("system_test", self.sb.config())

    def test_configure_tests_needs_a_terminal(self):
        code, out = self.sb.vm("configure-tests", "--system", "tests/system")
        self.assertEqual(code, 3, f"{RED} {out}")
        self.assertIn("needs an interactive terminal", out)
        self.assertNotIn("system_test", json.loads((self.sb.root / ".vmodel/config.json").read_text(encoding="utf-8")))


if __name__ == "__main__":
    unittest.main()

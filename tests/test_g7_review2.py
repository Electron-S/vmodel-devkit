"""Narrow re-review of the G7 review fixes (7939f97): two over-strict configure-tests refusals (RED target: 7939f97).

S1 (LOW) a system_test that is not a pytest command made 'configure-tests --integration' refuse: the overlap cannot be
   told there, but G6/G7.SCOPE judge what really runs, so it is a note, not a refusal.
S2 (LOW) '--pyargs' is a flag, not an option with a value: the module name after it was skipped, so the command looked
   like "no folder, every test" and was refused as overlapping.
"""
from __future__ import annotations

import os
import unittest

from g7_base import GRADECALC, PYTEST, RED
from helpers import Sandbox, has_pytest


@unittest.skipUnless(has_pytest() and os.name == "posix", "pytest and a POSIX pty are needed")
class ConfigureReview2Red(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox(fixture=GRADECALC)
        self.sb.init()
        self.sb.put_code()
        (self.sb.root / "tests/integration").mkdir()
        (self.sb.root / "tests/integration/test_x.py").write_text("def test_x():\n    pass\n", encoding="utf-8")

    def tearDown(self):
        self.sb.cleanup()

    def configure_integration_with_system(self, argv: list[str]) -> str:
        cfg = self.sb.config()
        cfg["system_test"] = {"argv": argv, "timeout_s": 60}
        self.sb.set_config(cfg)
        return self.sb.run_tty("configure-tests", "--integration", "tests/integration").decode("utf-8", "replace")

    def test_S1_non_pytest_system_command_is_a_note_not_a_refusal(self):
        out = self.configure_integration_with_system(["{python}", "scripts/run_system.py", "--junit", "{junit}"])
        self.assertIn("integration_test", self.sb.config(), f"{RED} {out}")
        self.assertIn("not a pytest command", out)  # the user is told it could not be checked

    def test_S2_pyargs_is_a_flag(self):
        out = self.configure_integration_with_system([*PYTEST, "--pyargs", "gradecalc_system", "--junitxml={junit}"])
        self.assertIn("integration_test", self.sb.config(), f"{RED} {out}")


if __name__ == "__main__":
    unittest.main()

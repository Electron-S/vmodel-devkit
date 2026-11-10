"""Independent review 16 of the D46 guard change (11bb551): commands the quote masking let through.

Once a command counts as a validator call the guard allows it before any write check, so the masking must never hide
syntax bash (or PowerShell) acts on. Reproduced by the reviewer with a fake vmodel (the shell really wrote the file)
and re-run here against the guard.
- New in 11bb551: bash ANSI-C quoting $'...\\'...' (\\' does not end it), and the PowerShell tool, where a backslash is
  no escape inside double quotes.
- Also on fa815b3 and older: an unquoted newline separates commands, and backslash-newline joins "$" and "(" into a
  command substitution (also inside double quotes).
RED target: git archive 11bb551 plugins/vmodel.
"""
from __future__ import annotations

import unittest

from helpers import PLUGIN
from test_guard_redirects import _Guard

VM = f'"{PLUGIN / "bin" / "vmodel"}"'
CORE = PLUGIN / "validator" / "vmodel_validator" / "hook.py"


class GuardQuoted2Red(_Guard):
    def test_ansi_c_quoting_does_not_hide_a_redirection(self):
        self.assert_denied([f"{VM} status $'x\\'' >.vmodel/state/ledger.jsonl '\\'",
                            f"{VM} status $'x\\'' >\"{CORE}\" '\\'",
                            f"{VM} status $'x\\'' ; rm -rf .vmodel/state '\\'"])

    def test_powershell_double_quotes_have_no_backslash_escape(self):
        denied = [self.decide(f'{VM} status "\\" > .vmodel/state/ledger.jsonl "\\"', tool="PowerShell"),
                  self.decide(f'{VM} status "\\" > "{CORE}" "\\"', tool="PowerShell")]
        self.assertEqual([d is not None for d in denied], [True, True], f"RED-TARGET {denied}")

    def test_newline_and_line_continuation_are_shell_syntax(self):
        self.assert_denied([f"{VM} status\nrm -rf .vmodel/state",
                            f"{VM} status $\\\n(rm -rf .vmodel/state)",
                            f'{VM} status "$\\\n(rm -rf .vmodel/state)"'])

    def assert_denied(self, cmds, agent_type=None):
        allowed = [c for c in cmds if self.decide(c, agent_type) is None]
        self.assertEqual(allowed, [], "RED-TARGET should be denied")


class GuardQuoted2Char(_Guard):
    def test_quoted_text_stays_allowed(self):
        self.assert_allowed([f'{VM} new-wi --title "t" --request "x > 0 and <id>"',
                             f"{VM} new-wi --title 't' --request 'a; b | c'",
                             f'{VM} new-wi --title "t" --request "line one\nline two > x"'])


if __name__ == "__main__":
    unittest.main()

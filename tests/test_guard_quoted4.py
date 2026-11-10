"""Independent review 18 of the guard hardening (88971ac).

RED target: git archive 88971ac plugins/vmodel. Reproduced by the reviewer (bash really truncated / removed the test
ledger; PowerShell 5.1 checked) and re-run here against the guard.
- A ' inside a bash comment opened a "quote" for the masking, hiding the newline after it (the redirect form was denied
  on fa815b3: made worse by 11bb551; the rm form was open before).
- PowerShell: a '(' inside a quoted request text made the call a non-validator call (no masking for PowerShell), and a
  word like "copy" then counted as a write next to the plugin path: a legitimate call denied (fa815b3 allowed it).
"""
from __future__ import annotations

import unittest

from helpers import PLUGIN
from test_guard_redirects import _Guard

VM = f'"{PLUGIN / "bin" / "vmodel"}"'


class GuardQuoted4DenyRed(_Guard):
    def test_a_quote_in_a_comment_does_not_hide_the_next_line(self):
        allowed = [c for c in (f"{VM} status #'\n>.vmodel/state/ledger.jsonl #'",
                               f"{VM} status #'\nrm -rf .vmodel/state #'") if self.decide(c) is None]
        self.assertEqual(allowed, [], "RED-TARGET should be denied")


class GuardQuoted4AllowRed(_Guard):
    def test_powershell_quoted_text_with_parentheses(self):
        cmds = [f'{PLUGIN / "bin" / "vmodel"} new-wi --title "t" --request "Add a copy button (UI)"',
                f"{PLUGIN / 'bin' / 'vmodel'} new-wi --title 't' --request 'install it (twice)'"]
        # (review 20: a quoted > is refused under PowerShell after all - it runs vmodel.cmd; test_guard_quoted6)
        denied = {c[-45:]: self.decide(c, tool="PowerShell") for c in cmds}
        self.assertEqual({c: r for c, r in denied.items() if r is not None}, {}, "RED-TARGET should be allowed")


class GuardQuoted4Char(_Guard):
    def test_powershell_expressions_and_bash_quoted_text(self):
        for c in (f"{VM} status (Remove-Item -Recurse -Force .vmodel/state)",
                  f'{VM} new-wi --request "$(Remove-Item -Recurse .vmodel/state)"',
                  f"{VM} status | grep x\nRemove-Item -Recurse -Force .vmodel/state"):
            self.assertIsNotNone(self.decide(c, tool="PowerShell"), c)
        self.assert_allowed([f'{VM} new-wi --title "t" --request "a #tag > b (copy)"', f"{VM} status"])


if __name__ == "__main__":
    unittest.main()

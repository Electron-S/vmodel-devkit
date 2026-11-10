"""Independent review 17 of the guard hardening (7526ce3).

RED target: git archive 7526ce3 plugins/vmodel. Reproduced by the reviewer with a fake vmodel (the shell ran the
second command / PowerShell ran the inner expression) and re-run here against the guard.
- Still a validator call although the shell runs another command (also on fa815b3 and older): a newline inside the
  allowed read-only pipe tail (bash and PowerShell), and PowerShell argument-mode expressions (...) / @(...).
- Legitimate request text denied again by 7526ce3 (allowed on 11bb551): a quoted text containing '$', and a call
  split over lines with backslash-newline (bash removes it before parsing).
"""
from __future__ import annotations

import unittest

from helpers import PLUGIN
from test_guard_redirects import _Guard

VM = f'"{PLUGIN / "bin" / "vmodel"}"'


class GuardQuoted3DenyRed(_Guard):
    def test_newline_in_the_safe_tail_and_powershell_expressions(self):
        cases = [(f"{VM} status | grep x\nrm -rf .vmodel/state", "Bash"),
                 (f"{VM} status 2>&1 | tail -5\nrm -rf .vmodel/state", "Bash"),
                 (f"{VM} status | grep x\nRemove-Item -Recurse -Force .vmodel/state", "PowerShell"),
                 (f"{VM} status (Remove-Item -Recurse -Force .vmodel/state)", "PowerShell"),
                 (f"{VM} status @(Set-Content -Path .vmodel/state/ledger.jsonl -Value x)", "PowerShell")]
        allowed = [c for c, tool in cases if self.decide(c, tool=tool) is None]
        self.assertEqual(allowed, [], "RED-TARGET should be denied")


class GuardQuoted3AllowRed(_Guard):
    def test_dollar_in_quoted_text_and_backslash_continued_calls(self):
        cmds = [f"{VM} new-wi --title \"t\" --request \"통화 기호 '$'를 붙이고 금액 > 0\"",
                f'{VM} new-wi \\\n  --title "t" \\\n  --request "x > 0"']
        denied = {c[-40:]: self.decide(c) for c in cmds}
        self.assertEqual({c: r for c, r in denied.items() if r is not None}, {}, "RED-TARGET should be allowed")


class GuardQuoted3Char(_Guard):
    def test_round16_bypasses_stay_closed(self):
        self.assert_denied([f"{VM} status $'x\\'' >.vmodel/state/ledger.jsonl '\\'",
                            f"{VM} status $\\\n(rm -rf .vmodel/state)",
                            f'{VM} status "$\\\n(rm -rf .vmodel/state)"',
                            f"{VM} status\nrm -rf .vmodel/state"])

    def test_plain_calls_and_tails_stay_allowed(self):
        self.assert_allowed([f"{VM} status 2>&1 | tail -5", f"{VM} status",
                             f'{VM} new-wi --title "t" --request "line one\nline two > x"'])


if __name__ == "__main__":
    unittest.main()

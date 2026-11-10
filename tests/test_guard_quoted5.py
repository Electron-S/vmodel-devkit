"""Independent review 19 of the guard hardening (690e757): the quote masking kept disagreeing with real shells.

RED target: git archive 690e757 plugins/vmodel. Reproduced by the reviewer with Windows PowerShell 5.1, pwsh 7 and
Git Bash (the files were created) and re-run here against the guard.
- PowerShell closes strings with typographic quotes (U+2018-U+201E) the masking did not know.
- A batch target (vmodel.cmd) is parsed again by cmd.exe, where a quoted > is a redirection (PowerShell and Git Bash).
fa815b3 denied all of these. D46 now accepts quoted text only in a narrow positive grammar (plain words and simple
quoted strings) and judges everything else as fa815b3 did, plus the newline and PowerShell '(' rules.
"""
from __future__ import annotations

import unittest

from helpers import PLUGIN
from test_guard_redirects import _Guard

VMP = str(PLUGIN / "bin" / "vmodel")


class GuardQuoted5Red(_Guard):
    def test_typographic_quotes_and_batch_targets(self):
        cases = [(f"{VMP} status 'a’ > .vmodel/state/ledger.jsonl ’'", "PowerShell"),
                 (f'{VMP} status "a” > .vmodel/state/ledger.jsonl “"', "PowerShell"),
                 (f"{VMP}.cmd status 'x>.vmodel/state/ledger.jsonl'", "PowerShell"),
                 (f"{VMP}.cmd status 'x>.vmodel/state/ledger.jsonl'", "Bash")]
        allowed = [c for c, tool in cases if self.decide(c, tool=tool) is None]
        self.assertEqual(allowed, [], "RED-TARGET should be denied")


class GuardQuoted5Char(_Guard):
    def test_plain_quoted_requests_stay_allowed(self):
        bash = [f'"{VMP}" new-wi --title "주문 가격" --request "첫 줄 \'ORDER <order_id>\', 합계 > 0 (UI) #1 — a; b | c"',
                f'"{VMP}" new-wi \\\n  --title "t" \\\n  --request "x > 0"',
                f'"{VMP}" new-wi --title "t" --request "통화 기호 \'$\'를 붙이고 금액 > 0"']
        self.assert_allowed(bash)
        for c in (f'{VMP} new-wi --title "t" --request "Add a copy button (UI) > 0"',
                  f"{VMP} new-wi --title 't' --request 'install (twice) > 0'"):
            self.assertIsNone(self.decide(c, tool="PowerShell"), c)


class GuardQuoted5PerfAccept(_Guard):
    def test_long_commands_outside_the_grammar_are_decided_quickly(self):
        """The first D46 grammar nested a quantifier ([word chars]+)+ and backtracked exponentially on a long
        non-matching command (found while running the guard suites, before release)."""
        import sys
        import time
        sys.path.insert(0, str(PLUGIN / "validator"))
        try:
            from vmodel_validator import hook
        finally:
            sys.path.remove(str(PLUGIN / "validator"))
        for tool in ("Bash", "PowerShell"):
            for cmd in ("a" * 20000 + "!", "ab " * 7000 + "!", '"a" ' * 5000 + "$(", "a\\\n " * 5000 + "!"):
                t0 = time.perf_counter()
                hook._is_validator_call(cmd, tool)
                self.assertLess(time.perf_counter() - t0, 2.0, (tool, cmd[:30]))


if __name__ == "__main__":
    unittest.main()

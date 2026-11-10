"""Independent review 20 of the D46 grammar (6f332f1): PowerShell runs bin/vmodel as vmodel.cmd.

RED target: git archive 6f332f1 plugins/vmodel. Reproduced by the reviewer with Windows PowerShell 5.1 and pwsh 7:
with vm and vm.cmd side by side, `vm status 'x>f'` and `<dir>\\vm status 'x>f'` resolve to vm.cmd (PATHEXT) and
cmd.exe parses the unquoted argument again, creating f. The .cmd/.bat exclusion looked only at the written name.
For the PowerShell tool the D46 grammar now refuses quoted cmd.exe metacharacters (& | < > ^ %) altogether.
"""
from __future__ import annotations

import unittest

from helpers import PLUGIN
from test_guard_redirects import _Guard

VMP = str(PLUGIN / "bin" / "vmodel")


class GuardQuoted6Red(_Guard):
    def test_powershell_resolves_vmodel_to_the_batch_file(self):
        cases = ["vmodel status 'x>.vmodel/state/ledger.jsonl'", f"{VMP} status 'x>.vmodel/state/ledger.jsonl'",
                 f'{VMP} status "x>{PLUGIN}/validator/vmodel_validator/hook.py"']
        allowed = [c for c in cases if self.decide(c, tool="PowerShell") is None]
        self.assertEqual(allowed, [], "RED-TARGET should be denied")


class GuardQuoted6Char(_Guard):
    def test_powershell_quoted_text_without_cmd_metacharacters_stays_allowed(self):
        for c in (f'{VMP} new-wi --title "t" --request "Add a copy button (UI); #1 — 첫 줄"',
                  f"{VMP} new-wi --title 't' --request 'install it (twice)'"):
            self.assertIsNone(self.decide(c, tool="PowerShell"), c)


if __name__ == "__main__":
    unittest.main()

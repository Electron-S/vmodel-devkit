"""Guard gap found in review 21 (D46): a cmd.exe builtin followed by ',' ';' '=' instead of a space was no write.

Under PowerShell `vmodel` resolves to vmodel.cmd (PATHEXT) and cmd.exe parses the arguments again, so
`vmodel status 'x|del,.vmodel/state/ledger.jsonl'` pipes into `del,<file>`, which cmd runs as `del <file>` (the reviewer
deleted a test file this way with Windows PowerShell 5.1). WRITE_VERBS required whitespace after del/erase/rd/ren/
move/copy/..., so the guard saw no write and allowed it (also through Git Bash with vmodel.cmd). Also open on 0.1.x.
RED target: git archive 20d2139 plugins/vmodel.
"""
from __future__ import annotations

import unittest

from helpers import PLUGIN
from test_guard_redirects import _Guard

CMD = str(PLUGIN / "bin" / "vmodel.cmd")


class GuardCmdBuiltinRed(_Guard):
    def test_cmd_builtins_with_comma_semicolon_or_equals(self):
        cases = [("vmodel status 'x|del,.vmodel/state/ledger.jsonl'", "PowerShell"),
                 ("vmodel status 'x|erase;.vmodel/state/ledger.jsonl'", "PowerShell"),
                 ("vmodel status 'x&rd=.vmodel/state'", "PowerShell"),
                 (f"{CMD} status 'x|del,.vmodel/state/ledger.jsonl'", "Bash"),
                 (f"{CMD} status 'x|move,.vmodel/state/ledger.jsonl,y'", "Bash")]
        allowed = [c for c, tool in cases if self.decide(c, tool=tool) is None]
        self.assertEqual(allowed, [], "RED-TARGET should be denied")


class GuardCmdBuiltinChar(_Guard):
    def test_plain_calls_and_quoted_words_stay_allowed(self):
        self.assert_allowed(['vmodel new-wi --title "t" --request "add a delete button, copy text"', "vmodel status",
                             "grep -n delimiter README.md"])


if __name__ == "__main__":
    unittest.main()

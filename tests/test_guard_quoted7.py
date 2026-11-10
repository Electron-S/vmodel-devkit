"""Windows regression of the D46 grammar (18bbcb8): a quoted Windows path in a Git Bash validator call.

On Windows the plugin path is like "C:\\Users\\x\\vmodel 한글 테스트\\bin\\vmodel"; the agent calls it quoted from the Bash
tool (Git Bash). The bash grammar allowed only \\" and \\\\ inside double quotes, so a quoted Windows path left the
grammar and a request text with < or > was denied again (the drill S1 failure, on Windows only: 8 guard tests failed
in the Windows harness for 18bbcb8). In bash double quotes a backslash before any other character is literal, and
\\$ / \\` are escaped characters (no expansion), so any backslash pair except backslash-newline is plain text.
RED target: git archive 18bbcb8 plugins/vmodel (on WSL the grammar is checked directly with a Windows-shaped path).
"""
from __future__ import annotations

import sys
import unittest

from helpers import PLUGIN
from test_guard_redirects import _Guard


def load_hook():
    sys.path.insert(0, str(PLUGIN / "validator"))
    try:
        for m in [m for m in sys.modules if m == "vmodel_validator" or m.startswith("vmodel_validator.")]:
            del sys.modules[m]
        import vmodel_validator.hook as hook
    finally:
        sys.path.remove(str(PLUGIN / "validator"))
    return hook


class GuardQuoted7Red(unittest.TestCase):
    def test_windows_path_and_escaped_characters_are_plain(self):
        hook = load_hook()
        win = '"C:\\Users\\x\\vmodel 한글 테스트\\bin\\vmodel"'
        for text in (f'{win} new-wi --title "t" --request "x > 0"', f"{win} status",
                     '"/opt/a" new-wi --title "t" --request "price \\$5 and \\`x\\` > 0"'):
            self.assertTrue(hook._plain_call(text, "Bash"), f"RED-TARGET {text}")


class GuardQuoted7Char(_Guard):
    def test_backslash_newline_and_substitution_stay_outside_the_grammar(self):
        hook = load_hook()
        for text in ('"/opt/a" status "$\\\n(rm -rf x)"', '"/opt/a" status "\\\\$(rm -rf x)"', '"/opt/a" status "a\\\nb"'):
            self.assertFalse(hook._plain_call(text, "Bash"), text)
        self.assert_denied(['vmodel status "$\\\n(rm -rf .vmodel/state)"', 'vmodel status "\\\\$(rm -rf .vmodel/state)"'])


if __name__ == "__main__":
    unittest.main()

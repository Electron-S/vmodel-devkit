"""Independent review 23 of D48 (733d708): regressions the run-time protections caused.

RED target: git archive 733d708 plugins/vmodel (the reviewer's probes, re-run).
- R1 flagged the provider's own code as a patch: a class name later rebound by an import (the weak rule was not applied
  to classes) and a plain def rebound inside a function through `global` (a name the static bindings call "strict").
- The guard counted read-only commands as writes: a cmd builtin name at the end of the command or before '(' (e.g.
  `... | grep copy`, `grep -rn del( ...`), next to a .vmodel path.
Not fixed, documented (DECISIONS D48): R2 also drops a legitimate thread/process connection when an autouse fixture
starts any thread or process in the test (accepted conservative BLOCKED).
"""
from __future__ import annotations

import unittest

from g6_base import RED
from test_g6_policy import iface, level
from test_g6_review12 import R12Base
from test_guard_redirects import _Guard


def edit_report(sb, add_top: str, body_call: str) -> None:
    rp = sb.root / "src/pipeline/report.py"
    t = rp.read_text(encoding="utf-8")
    t = t.replace("from pipeline.parser import parse\n", "from pipeline.parser import parse\n" + add_top, 1)
    t = t.replace("    records = parse(text)\n", "    records = parse(text)\n" + body_call, 1)
    assert body_call in t
    rp.write_text(t, encoding="utf-8")


class Residual2ProviderRed(R12Base):
    def assert_test_level(self, r6, rec):
        self.assertEqual((r6.get("status"), level(rec, "IF-002", "TEST-012")), ("PASSED", "test_level"),
                         f"{RED} {iface(rec, 'IF-002')}")

    def test_R1b_class_fallback_rebound_by_an_import(self):
        edit_report(self.sb, "\n\nclass _Store(list):\n    pass\n\n\ntry:\n    from collections import UserList as _Store\n"
                             "except ImportError:\n    pass\n", "    _Store(records)\n")
        self.assert_test_level(*self.go(None))

    def test_R1c_plain_def_rebound_inside_a_function(self):
        edit_report(self.sb, "import operator\n\n\ndef _key(r):\n    return (r['score'], r['name'])\n\n\n"
                             "def _speedup():\n    global _key\n    _key = operator.itemgetter('score', 'name')\n",
                    "    _speedup()\n    max(records or [{'score': 0, 'name': ''}], key=lambda r: _key(r))\n")
        self.assert_test_level(*self.go(None))


class Residual2GuardRed(_Guard):
    def test_read_only_commands_naming_a_cmd_builtin(self):
        cases = [("cat .vmodel/work-items/WI-001/requirements.json | grep copy", "Bash"),
                 ("grep -rn del( .vmodel/work-items", "Bash"),
                 ("Get-Content .vmodel/work-items/WI-001/requirements.json | Select-String copy", "PowerShell")]
        denied = {c: self.decide(c, tool=tool) for c, tool in cases}
        self.assertEqual({c: r for c, r in denied.items() if r is not None}, {}, "RED-TARGET should be allowed")


if __name__ == "__main__":
    unittest.main()

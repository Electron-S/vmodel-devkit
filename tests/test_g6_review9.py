"""Ninth independent review (31ccb0d, the review-8 P1 fix only, 2026-11-10): finding as a test first.

RED target: git archive 31ccb0d plugins/vmodel. Q1: narrowing the "test patches the provider" rule to interface symbols
(P1) let a stub of the provider's own implementation helper pass as test-level (Case B). The rule now counts a patch of
any def/class (or method) defined in a provider module, and still ignores constants and imported names (P1).
"""
from __future__ import annotations

import unittest

from g6_base import RED, replace_function
from test_g6_review7 import Base


class R9HelperPatchRed(Base):
    def test_Q1_patching_the_providers_implementation_helper(self):
        """parse() is a thin entry over _parse_impl(); both IF-001 tests replace _parse_impl with a stub."""
        pp = self.sb.root / "src/pipeline/parser.py"
        text = pp.read_text(encoding="utf-8").replace("def parse(text: str) -> list[dict]:",
                                                      "def _parse_impl(text: str) -> list[dict]:", 1)
        pp.write_text(text + "\n\ndef parse(text: str) -> list[dict]:\n    return _parse_impl(text)\n", encoding="utf-8")
        for name in ("test_TEST_010_report_uses_real_parser", "test_TEST_011_parser_error_reaches_report"):
            replace_function(self.itest, name,
                             f"def {name}(monkeypatch):\n"
                             "    monkeypatch.setattr('pipeline.parser._parse_impl', lambda text: [{'name': 'z', 'score': 1}])\n"
                             "    assert summarize('anything')['top'] == 'z'\n")
        r4, r5, r6 = self.to_g6()
        self.assertEqual(r6.get("status"), "BLOCKED", f"{RED} the provider's logic is stubbed in every IF-001 test: {r6}")


if __name__ == "__main__":
    unittest.main()

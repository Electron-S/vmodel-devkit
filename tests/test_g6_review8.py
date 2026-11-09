"""Eighth independent review (953d502, 2026-11-10 final verification): findings as tests first.

RED target: git archive 953d502 plugins/vmodel. P1: the review-7 R4 rule (a test that patches the provider is not
test-level) must not fire for a harmless attribute of the provider module (a configuration constant): only a patch of
an interface symbol or one of its methods counts. P2 (a callable-class decorator in the provider module hides the
interface function) is not fixed: preferring a symbol frame would reopen review 6 M1 (a method run by the constructor);
it stays BLOCKED (conservative) and is characterised here.
"""
from __future__ import annotations

import unittest

from g6_base import RED, replace_function
from test_g6_review7 import Base


class R8HarmlessPatchRed(Base):
    def test_P1_patching_a_provider_module_constant_is_not_a_mock(self):
        """Both IF-001 tests run the real report -> parser path; they only lower a limit constant of parser.py."""
        pp = self.sb.root / "src/pipeline/parser.py"
        pp.write_text(pp.read_text(encoding="utf-8").replace(
            '"""Score record parser (DESIGN-001, provider of IF-001)."""\n',
            '"""Score record parser (DESIGN-001, provider of IF-001)."""\n\nMAX_RECORDS = 1000\n', 1).replace(
            "        records.append(", "        if len(records) >= MAX_RECORDS:\n"
            "            raise ValueError(f\"line {no}: too many records\")\n        records.append(", 1),
            encoding="utf-8")
        replace_function(self.itest, "test_TEST_010_report_uses_real_parser",
                         "def test_TEST_010_report_uses_real_parser(monkeypatch):\n"
                         "    monkeypatch.setattr('pipeline.parser.MAX_RECORDS', 5)\n"
                         "    assert summarize('kim,90\\nlee,95\\npark,70\\n') == {'count': 3, 'total': 255, 'top': 'lee'}\n")
        replace_function(self.itest, "test_TEST_011_parser_error_reaches_report",
                         "def test_TEST_011_parser_error_reaches_report(monkeypatch):\n"
                         "    monkeypatch.setattr('pipeline.parser.MAX_RECORDS', 1)\n"
                         "    with pytest.raises(ValueError):\n        summarize('kim,90\\nlee,95\\n')\n")
        r4, r5, r6 = self.to_g6()
        self.assertEqual(r6.get("status"), "PASSED", f"{RED} real connection; only a configuration constant is patched: {r6}")


class R8ClassDecoratorChar(Base):
    """P2 not fixed (documented limitation): same result on 953d502."""

    def test_P2_callable_class_decorator_in_the_provider_module(self):
        pp = self.sb.root / "src/pipeline/parser.py"
        pp.write_text(pp.read_text(encoding="utf-8").replace(
            '"""Score record parser (DESIGN-001, provider of IF-001)."""\n',
            '"""Score record parser (DESIGN-001, provider of IF-001)."""\n\n\nclass _Checked:\n'
            "    def __init__(self, fn):\n        self.fn = fn\n\n"
            "    def __call__(self, text):\n        if not isinstance(text, str):\n"
            "            raise TypeError('text must be str')\n        return self.fn(text)\n\n\n@_Checked", 1),
            encoding="utf-8")
        r4, r5, r6 = self.to_g6()
        self.assertEqual((r6.get("status"), r6.get("blocked_reason")), ("BLOCKED", "integration_evidence_insufficient"),
                         r6)


if __name__ == "__main__":
    unittest.main()

"""Independent review 26 of D48 (291d18b): a provider-module object replaced as a whole by a test-defined fake.

The provider keeps `_fmt = _Fmt()` and calls `_fmt.top(...)`; an autouse fixture runs
`monkeypatch.setattr(report, '_fmt', FakeFmt())` with FakeFmt defined in the test file. `_fmt` is neither a def nor a
class, and the fake's class is not provider-defined, so neither the static detection nor D48 R1 saw it: Test-level and
G6 PASSED (policy A false PASS, older than D48). R1 now checks every global of the provider module: a mock, a function
or class from the test tree or from a string, or an instance of a class defined in the test tree, is a patch. Plain
values (constants, configuration) stay a warning only (review 8 P1).
RED target: git archive 291d18b plugins/vmodel.
"""
from __future__ import annotations

import unittest

from g6_base import RED, replace_function
from test_g6_policy import iface, level
from test_g6_residual3 import BODY, InstanceBase


class WholeObjectRed(InstanceBase):
    def test_autouse_fixture_replaces_the_providers_object_with_a_test_fake(self):
        self.setup_fmt()
        replace_function(self.itest, "test_TEST_012_cli_main_reads_file",
                         "class FakeFmt:\n    def top(self, records):\n"
                         "        return max(records, key=lambda x: (x['score'], x['name']))\n\n\n"
                         "@pytest.fixture(autouse=True)\ndef fake(monkeypatch):\n    import pipeline.report as r\n"
                         "    monkeypatch.setattr(r, '_fmt', FakeFmt())\n\n\n"
                         "def test_TEST_012_cli_main_reads_file(tmp_path, capsys):\n" + BODY)
        r6, rec = self.go(None)
        self.assertNotEqual(level(rec, "IF-002", "TEST-012"), "test_level", f"{RED} {iface(rec, 'IF-002')}")
        self.assertEqual(r6.get("status"), "BLOCKED", f"{RED} {r6}")

    def test_a_mock_object_replaces_the_providers_object(self):
        self.setup_fmt()
        replace_function(self.itest, "test_TEST_012_cli_main_reads_file",
                         "@pytest.fixture(autouse=True)\ndef fake(monkeypatch):\n"
                         "    from unittest import mock\n    import pipeline.report as r\n"
                         "    m = mock.MagicMock()\n    m.top.side_effect = lambda records: max(records, "
                         "key=lambda x: (x['score'], x['name']))\n"
                         "    monkeypatch.setattr(r, '_fmt', m)\n\n\n"
                         "def test_TEST_012_cli_main_reads_file(tmp_path, capsys):\n" + BODY)
        r6, rec = self.go(None)
        self.assertNotEqual(level(rec, "IF-002", "TEST-012"), "test_level", f"{RED} {iface(rec, 'IF-002')}")


class WholeObjectChar(InstanceBase):
    def test_a_configuration_constant_stays_a_warning(self):
        rp = self.sb.root / "src/pipeline/report.py"
        rp.write_text(rp.read_text(encoding="utf-8").replace("\n\ndef summarize(", "\n\nLIMIT = 100\n\n\ndef summarize(", 1),
                      encoding="utf-8")
        replace_function(self.itest, "test_TEST_012_cli_main_reads_file",
                         "@pytest.fixture(autouse=True)\ndef small(monkeypatch):\n    import pipeline.report as r\n"
                         "    monkeypatch.setattr(r, 'LIMIT', 5)\n\n\n"
                         "def test_TEST_012_cli_main_reads_file(tmp_path, capsys):\n" + BODY)
        r6, rec = self.go(None)
        self.assertEqual((r6.get("status"), level(rec, "IF-002", "TEST-012")), ("PASSED", "test_level"),
                         iface(rec, "IF-002"))


if __name__ == "__main__":
    unittest.main()

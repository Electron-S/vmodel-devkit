"""A provider object's method replaced on the instance (found while classifying the D45 risks, 2026-11-11).

The provider module keeps a module-level instance of a class it defines (`_fmt = _Fmt()`) and calls `_fmt.top(...)`.
Patching the method on the instance (`monkeypatch.setattr(report._fmt, "top", fake)`) changes neither the module names
nor the class dictionary that D48 R1 checks, and the static detection only warns about it (review 8 P1 treats other
module attributes as configuration). So a fixture that did it gave Test-level Verified and G6 PASSED: policy A false
PASS. R1 now also checks module-level instances of provider-defined classes for methods shadowed on the instance.
RED target: git archive 86dbf98 plugins/vmodel.
"""
from __future__ import annotations

import unittest

from g6_base import RED, replace_function
from test_g6_policy import EXPECTED, iface, level
from test_g6_review12 import R12Base

BODY = ("    f = tmp_path / 'scores.csv'\n    f.write_text('a,1\\nb,2\\n', encoding='utf-8')\n"
        "    assert main([str(f)]) == 0\n"
        f"    assert json.loads(capsys.readouterr().out) == {EXPECTED}\n")
FAKE = "lambda records: max(records, key=lambda x: (x['score'], x['name']))"


class InstanceBase(R12Base):
    def setup_fmt(self):
        rp = self.sb.root / "src/pipeline/report.py"
        t = rp.read_text(encoding="utf-8")
        t = t.replace("\n\ndef summarize(", "\n\nclass _Fmt:\n    def top(self, records):\n"
                      "        return max(records, key=lambda r: (r['score'], r['name']))\n\n\n_fmt = _Fmt()\n\n\n"
                      "def summarize(", 1)
        t = t.replace('    top = max(records, key=lambda r: (r["score"], r["name"]))\n', "    top = _fmt.top(records)\n", 1)
        assert "_fmt.top(records)" in t
        rp.write_text(t, encoding="utf-8")


class InstancePatchRed(InstanceBase):
    def test_autouse_fixture_replaces_a_method_on_the_providers_instance(self):
        self.setup_fmt()
        replace_function(self.itest, "test_TEST_012_cli_main_reads_file",
                         "@pytest.fixture(autouse=True)\ndef fake(monkeypatch):\n    import pipeline.report as r\n"
                         f"    monkeypatch.setattr(r._fmt, 'top', {FAKE})\n\n\n"
                         "def test_TEST_012_cli_main_reads_file(tmp_path, capsys):\n" + BODY)
        r6, rec = self.go(None)
        self.assertNotEqual(level(rec, "IF-002", "TEST-012"), "test_level", f"{RED} {iface(rec, 'IF-002')}")
        self.assertEqual(r6.get("status"), "BLOCKED", f"{RED} {r6}")

    def test_the_test_replaces_a_method_on_the_providers_instance(self):
        self.setup_fmt()
        replace_function(self.itest, "test_TEST_012_cli_main_reads_file",
                         "def test_TEST_012_cli_main_reads_file(tmp_path, capsys, monkeypatch):\n"
                         "    import pipeline.report as r\n"
                         f"    monkeypatch.setattr(r._fmt, 'top', {FAKE})\n" + BODY)
        r6, rec = self.go(None)
        self.assertNotEqual(level(rec, "IF-002", "TEST-012"), "test_level", f"{RED} {iface(rec, 'IF-002')}")


class InstanceControlChar(InstanceBase):
    def test_unpatched_instance_stays_test_level(self):
        self.setup_fmt()
        replace_function(self.itest, "test_TEST_012_cli_main_reads_file",
                         "def test_TEST_012_cli_main_reads_file(tmp_path, capsys):\n" + BODY)
        r6, rec = self.go(None)
        self.assertEqual((r6.get("status"), level(rec, "IF-002", "TEST-012")), ("PASSED", "test_level"),
                         iface(rec, "IF-002"))


if __name__ == "__main__":
    unittest.main()

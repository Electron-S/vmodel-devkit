"""G4 integration readiness and the runtime integration path (T06, T07, T08, T09; REQ-G6-09-12, 29-33)."""
from __future__ import annotations

import json
import unittest

from g6_base import (API_TEST_012, RED, SUBPROCESS_TEST_012, SandboxClass, file_sha256, ledger_record,
                     replace_function)

INTEGRATION = "tests/integration/test_pipeline.py"


class WiringBase(SandboxClass):
    """pipeline, split commands, G1-G3 PASSED, code in place (not yet evaluated at G4)."""
    upto = "G3"

    @classmethod
    def build(cls, sb):
        super().build(sb)
        sb.put_code()

    @property
    def itest(self):
        return self.sb.root / INTEGRATION

    def g4(self, **review) -> tuple[int, dict]:
        self.sb.review("G4", **review)
        return self.sb.gate("G4")

    def wiring(self, res: dict) -> dict:
        return self.check(res, "G4.INTEGRATION_WIRING")

    def declare(self, tid: str, kind: str, if_id: str = "IF-002", sha: str | None = None) -> list[dict]:
        entries = self.sb.interface_review_entries()
        for e in entries:
            if e["id"] == if_id:
                e["runtime_paths"] = [{"test": tid, "kind": kind, "test_file_sha256": sha or file_sha256(self.itest),
                                       "entry": "python -m pipeline.report", "note": "harness verifier"}]
        return entries


class WiringRed(WiringBase):
    def test_T06_assert_true_placeholder_fails_g4(self):
        replace_function(self.itest, "test_TEST_012_cli_main_reads_file",
                         "def test_TEST_012_cli_main_reads_file():\n    assert True\n")
        code, res = self.g4()
        self.assertEqual(res["status"], "FAILED", f"{RED} a placeholder integration test must fail G4: {res}")
        w = self.wiring(res)
        self.assertEqual(w["status"], "fail")
        self.assertTrue(any("TEST-012" in i and "placeholder" in i for i in w["items"]), w)

    def test_T06_pass_and_docstring_placeholder_fails_g4(self):
        replace_function(self.itest, "test_TEST_010_report_uses_real_parser",
                         'def test_TEST_010_report_uses_real_parser():\n    """later"""\n    pass\n')
        code, res = self.g4()
        self.assertEqual(res["status"], "FAILED", f"{RED} {res}")
        self.assertTrue(any("TEST-010" in i and "placeholder" in i for i in self.wiring(res)["items"]))

    def test_T06_unused_nested_call_does_not_hide_a_placeholder(self):
        """Found while making the API path work: a nested def the test never calls is not a call of the test."""
        replace_function(self.itest, "test_TEST_012_cli_main_reads_file",
                         "def test_TEST_012_cli_main_reads_file():\n"
                         "    def never_called():\n"
                         "        return main(['x'])\n"
                         "    assert True\n")
        code, res = self.g4()
        self.assertEqual(res["status"], "FAILED", f"{RED} {res}")
        self.assertTrue(any("TEST-012" in i and "placeholder" in i for i in self.wiring(res)["items"]), res)

    def test_T07_interface_test_function_missing_fails_test_code(self):
        replace_function(self.itest, "test_TEST_012_cli_main_reads_file", None)
        code, res = self.g4()
        self.assertEqual(res["status"], "FAILED", f"{RED} IF-002's integration test has no function: {res}")
        tc = self.check(res, "G4.TEST_CODE")
        self.assertEqual(tc["status"], "fail")
        self.assertIn("TEST-012", tc["items"])  # same item format as a missing unit test (REQ-G6-09)

    def test_T08_import_only_test_does_not_reach_the_interface(self):
        replace_function(self.itest, "test_TEST_010_report_uses_real_parser",
                         "def test_TEST_010_report_uses_real_parser():\n"
                         "    import pipeline.parser\n"
                         "    import pipeline.report\n"
                         "    assert pipeline.report is not None\n"
                         "    assert callable(pipeline.parser.parse)\n")
        code, res = self.g4()
        self.assertEqual(res["status"], "FAILED", f"{RED} import and reference are not integration: {res}")
        w = self.wiring(res)
        self.assertTrue(any(i.startswith("TEST-010") and "IF-001" in i for i in w["items"]), w)

    def test_E2_interface_symbol_missing_from_provider(self):
        arch = self.sb.load("architecture.json")
        arch["interfaces"][0]["signature"] = "def parse_records(text: str) -> list[dict]"
        self.sb.save("architecture.json", arch)
        self.regate("G2", "G3")
        code, res = self.g4(interfaces=[{"id": "IF-001", "result": "ok", "provider_symbols": ["parse"]},
                                        {"id": "IF-002", "result": "ok", "provider_symbols": ["main"]}])
        self.assertEqual(res["status"], "FAILED", f"{RED} IF-001 symbol is not implemented: {res}")
        c = self.check(res, "G4.INTERFACE_IMPLEMENTED")
        self.assertTrue(any("IF-001" in i and "parse_records" in i for i in c["items"]), c)

    def test_E4_review_must_cover_every_interface(self):
        code, res = self.g4(interfaces=[{"id": "IF-001", "result": "ok", "provider_symbols": ["parse"]}])
        self.assertEqual(res["status"], "REVIEW_REQUIRED", f"{RED} IF-002 not reviewed: {res}")
        self.assertIn("IF-002", json.dumps(self.check(res, "G4.REVIEW")))
        code, res = self.g4(interfaces=[{"id": "IF-001", "result": "ok", "provider_symbols": ["nope"]},
                                        {"id": "IF-002", "result": "ok", "provider_symbols": ["main"]}])
        self.assertEqual(res["status"], "REVIEW_REQUIRED", res)
        self.assertIn("nope", json.dumps(self.check(res, "G4.REVIEW")))
        code, res = self.g4(interfaces=[{"id": "IF-001", "result": "issue", "provider_symbols": ["parse"],
                                         "note": "consumer swallows errors"},
                                        {"id": "IF-002", "result": "ok", "provider_symbols": ["main"]}])
        self.assertEqual(res["status"], "FAILED", res)

    def test_T09_subprocess_test_needs_a_declared_runtime_path(self):
        replace_function(self.itest, "test_TEST_012_cli_main_reads_file", SUBPROCESS_TEST_012)
        code, res = self.g4()
        self.assertEqual(res["status"], "REVIEW_REQUIRED", f"{RED} runtime path must be confirmed: {res}")
        w = self.wiring(res)
        self.assertEqual(w["status"], "pending")
        text = json.dumps(w, ensure_ascii=False)
        self.assertIn("TEST-012", text)
        self.assertIn("subprocess", text)
        self.assertIn(file_sha256(self.itest), text)

    def test_T09_declared_subprocess_path_passes_g4_and_g6_on_runtime_evidence(self):
        replace_function(self.itest, "test_TEST_012_cli_main_reads_file", SUBPROCESS_TEST_012)
        code, res = self.g4(interfaces=self.declare("TEST-012", "subprocess"))
        self.assertEqual(res["status"], "PASSED", f"{RED} declared runtime path: {res}")
        self.assertEqual(self.sb.gate("G5")[1]["status"], "PASSED")
        code, res = self.sb.gate("G6")
        self.assertEqual(res["status"], "PASSED", f"{RED} subprocess integration with runtime evidence: {res}")
        rec = ledger_record(self.sb, res["record_id"])
        if2 = [i for i in rec["interfaces"] if i["id"] == "IF-002"][0]
        self.assertTrue(if2["covered"])
        self.assertEqual(if2["tests"]["TEST-012"]["path"], "runtime")
        self.assertTrue(rec["runtime_trace"]["active"])
        self.assertGreaterEqual(rec["runtime_trace"]["processes"], 2)  # pytest + the child it started
        ev = json.loads((self.sb.root / res["evidence"][0]["path"]).read_text(encoding="utf-8"))
        self.assertTrue([f for f in ev["files"] if f.startswith("trace/")])
        self.assertEqual(self.sb.vm("verify-evidence", str(self.sb.root / res["evidence"][0]["path"]))[0], 0)

    def test_T09_declared_api_path_passes_on_runtime_evidence(self):
        replace_function(self.itest, "test_TEST_012_cli_main_reads_file", API_TEST_012)
        code, res = self.g4(interfaces=self.declare("TEST-012", "api"))
        self.assertEqual(res["status"], "PASSED", f"{RED} declared API path: {res}")
        self.assertEqual(self.sb.gate("G5")[1]["status"], "PASSED")
        res = self.sb.gate("G6")[1]
        self.assertEqual(res["status"], "PASSED", f"{RED} {res}")
        rec = ledger_record(self.sb, res["record_id"])
        if2 = [i for i in rec["interfaces"] if i["id"] == "IF-002"][0]
        self.assertEqual(if2["tests"]["TEST-012"]["path"], "runtime")

    def test_T09_stale_test_hash_in_declaration_needs_rereview(self):
        replace_function(self.itest, "test_TEST_012_cli_main_reads_file", SUBPROCESS_TEST_012)
        code, res = self.g4(interfaces=self.declare("TEST-012", "subprocess", sha="sha256:" + "0" * 64))
        self.assertEqual(res["status"], "REVIEW_REQUIRED", f"{RED} declaration for other test source: {res}")
        self.assertIn("test_file_sha256", json.dumps(self.wiring(res)))

    def test_T09_declared_path_without_provider_execution_blocks_g6(self):
        replace_function(self.itest, "test_TEST_012_cli_main_reads_file",
                         "def test_TEST_012_cli_main_reads_file():\n"
                         "    import subprocess\n"
                         "    import sys\n"
                         "    res = subprocess.run([sys.executable, '-c', 'print(1)'], capture_output=True, check=True)\n"
                         "    assert res.stdout.strip() == b'1'\n")
        code, res = self.g4(interfaces=self.declare("TEST-012", "subprocess"))
        self.assertEqual(res["status"], "PASSED", f"{RED} G4 accepts the declaration (verifier's judgement): {res}")
        self.assertEqual(self.sb.gate("G5")[1]["status"], "PASSED")
        code, res = self.sb.gate("G6")
        self.assertEqual((res["status"], res.get("blocked_reason")), ("BLOCKED", "integration_evidence_insufficient"),
                         f"{RED} no runtime proof that the provider ran: {res}")
        self.assertEqual(code, 3)
        cov = self.check(res, "G6.IF_COVERAGE")
        self.assertTrue(any("IF-002" in i and "TEST-012" in i for i in cov["items"]), cov)

    def test_E3_patched_provider_warns_at_g4_and_g6(self):
        replace_function(self.itest, "test_TEST_010_report_uses_real_parser",
                         "def test_TEST_010_report_uses_real_parser(monkeypatch):\n"
                         "    monkeypatch.setattr('pipeline.report.parse', lambda text: [{'name': 'x', 'score': 1}])\n"
                         "    assert summarize('ignored')['top'] == 'x'\n")
        code, res = self.g4()
        self.assertEqual(res["status"], "PASSED", res)
        w = self.wiring(res)
        self.assertEqual(w["status"], "warn", f"{RED} patched provider: {w}")
        self.assertTrue(any("TEST-010" in i and "patch" in i for i in w["items"]), w)
        self.assertEqual(self.sb.gate("G5")[1]["status"], "PASSED")
        res = self.sb.gate("G6")[1]
        self.assertEqual(res["status"], "PASSED", res)  # IF-001 is still covered by TEST-011
        cov = self.check(res, "G6.IF_COVERAGE")
        self.assertEqual(cov["status"], "warn", cov)
        self.assertTrue(any("TEST-010" in i and "did not run" in i for i in cov["items"]), cov)


class WiringChar(WiringBase):
    def test_E1_helper_and_fixture_reach_is_accepted(self):
        replace_function(self.itest, "test_TEST_010_report_uses_real_parser",
                         "def _summary(text):\n    return summarize(text)\n\n\n"
                         "def test_TEST_010_report_uses_real_parser():\n"
                         "    assert _summary('kim,90\\nlee,95\\n')['top'] == 'lee'\n")
        (self.sb.root / "tests/integration/conftest.py").write_text(
            "import pytest\n\nfrom pipeline.report import main\n\n\n@pytest.fixture\ndef report_main():\n"
            "    return main\n", encoding="utf-8")
        replace_function(self.itest, "test_TEST_012_cli_main_reads_file",
                         "def test_TEST_012_cli_main_reads_file(tmp_path, capsys, report_main):\n"
                         "    f = tmp_path / 'scores.csv'\n"
                         "    f.write_text('a,1\\nb,2\\n', encoding='utf-8')\n"
                         "    assert report_main([str(f)]) == 0\n"
                         "    assert json.loads(capsys.readouterr().out)['top'] == 'b'\n")
        code, res = self.g4()
        self.assertEqual(res["status"], "PASSED", res)


if __name__ == "__main__":
    unittest.main()

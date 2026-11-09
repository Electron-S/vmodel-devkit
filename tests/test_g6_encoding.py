"""Windows paths and encodings on the G6 path (T19). The sandbox path has Korean characters and spaces (T18 style);
on Windows (cp949 console) the same tests run in the regression copy."""
from __future__ import annotations

import json
import unittest

from g6_base import (RED, SUBPROCESS_TEST_012, SandboxClass, file_sha256, ledger_record, replace_function)


class EncodingRed(SandboxClass):
    def test_T19_cp949_output_and_korean_data_in_integration_run(self):
        t = self.sb.root / "tests/integration/test_pipeline.py"
        replace_function(t, "test_TEST_010_report_uses_real_parser",
                         "def test_TEST_010_report_uses_real_parser():\n"
                         "    import sys\n"
                         "    sys.stdout.buffer.write('한글 출력 확인\\n'.encode('cp949'))\n"
                         "    sys.stdout.flush()\n"
                         "    assert summarize('김철수,90\\n이영희,95\\n')['top'] == '이영희'\n")
        self.regate("G4", "G5")
        res = self.g6()
        self.assertEqual(res["status"], "PASSED", f"{RED} {res}")
        ev_path = self.sb.root / res["evidence"][0]["path"]
        self.assertIn("한글 경로", str(ev_path))
        ev = json.loads(ev_path.read_text(encoding="utf-8"))
        self.assertTrue(ev["runtime_trace"]["active"])
        self.assertEqual(self.sb.vm("verify-evidence", str(ev_path))[0], 0)
        self.assertEqual(self.sb.vm("audit")[0], 0)
        code, text = self.sb.vm("status")
        self.assertEqual(code, 0, text)
        self.assertIn("G6", text)

    def test_T19_subprocess_path_in_a_korean_path(self):
        t = self.sb.root / "tests/integration/test_pipeline.py"
        replace_function(t, "test_TEST_012_cli_main_reads_file", SUBPROCESS_TEST_012)
        entries = self.sb.interface_review_entries()
        for e in entries:
            if e["id"] == "IF-002":
                e["runtime_paths"] = [{"test": "TEST-012", "kind": "subprocess", "test_file_sha256": file_sha256(t)}]
        self.sb.review("G4", interfaces=entries)
        self.assertEqual(self.sb.gate("G4")[1]["status"], "PASSED")
        self.assertEqual(self.sb.gate("G5")[1]["status"], "PASSED")
        res = self.g6()
        self.assertEqual(res["status"], "PASSED", f"{RED} {res}")
        rec = ledger_record(self.sb, res["record_id"])
        if2 = [i for i in rec["interfaces"] if i["id"] == "IF-002"][0]
        self.assertEqual(if2["tests"]["TEST-012"]["path"], "runtime")


if __name__ == "__main__":
    unittest.main()

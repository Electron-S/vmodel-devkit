"""Encoding robustness and low-level modules (T18 parts that run on any OS)."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import unittest

from helpers import PLUGIN, Sandbox, has_pytest

sys.path.insert(0, str(PLUGIN / "validator"))
sys.dont_write_bytecode = True

from vmodel_validator import schema_lite, textio  # noqa: E402
from vmodel_validator.trace import test_ids_in_text  # noqa: E402


class TextIO(unittest.TestCase):
    def test_bom_tolerated(self):
        self.assertEqual(textio.decode_utf8("﻿{}".encode("utf-8"), "x"), "{}")

    def test_cp949_reported_not_crash(self):
        with self.assertRaises(textio.ArtifactError) as cm:
            textio.decode_utf8("요구사항".encode("cp949"), "requirements.json")
        self.assertIn("CP949", str(cm.exception))

    def test_utf16_reported(self):
        with self.assertRaises(textio.ArtifactError) as cm:
            textio.decode_utf8("{}".encode("utf-16"), "a.json")
        self.assertIn("UTF-16", str(cm.exception))

    def test_display_decode_never_raises(self):
        self.assertEqual(textio.display_decode("한글".encode("cp949")), "한글")
        self.assertTrue(textio.display_decode(b"\xff\xfe\xfa bad"))

    def test_test_id_tokens(self):
        self.assertEqual(test_ids_in_text("test_TEST_001_x tests.test_a::TEST-0002 xTEST_003"),
                         {"TEST-001", "TEST-0002"})

    def test_schema_lite(self):
        schema = {"type": "object", "required": ["a"], "properties": {"a": {"type": "string", "pattern": "^R"},
                                                                      "b": {"type": "array", "minItems": 1}}}
        self.assertEqual(schema_lite.validate({"a": "R1", "b": [1]}, schema), [])
        errs = schema_lite.validate({"a": "x", "b": []}, schema)
        self.assertEqual(len(errs), 2)
        self.assertEqual(schema_lite.validate(True, {"type": "integer"}), ["$: expected integer, got boolean"])


class ArtifactEncoding(unittest.TestCase):
    def test_cp949_artifact_fails_gate_cleanly(self):
        sb = Sandbox()
        try:
            sb.init()
            sb.new_wi()
            data = json.dumps({"work_item": "WI-001", "requirements": []}, ensure_ascii=False)
            (sb.wi_dir / "requirements.json").write_bytes((data + "한글").encode("cp949"))
            code, res = sb.gate("G1")
            self.assertEqual(res["status"], "FAILED")
            schema = [c for c in res["checks"] if c["id"] == "G1.SCHEMA"][0]
            self.assertTrue(any("CP949" in i for i in schema["items"]), schema)
        finally:
            sb.cleanup()


@unittest.skipUnless(has_pytest(), "pytest not installed for this interpreter")
class ProcessOutputBytes(unittest.TestCase):
    def test_non_utf8_test_output_hashed_raw(self):
        sb = Sandbox()
        try:
            sb.init()
            sb.new_wi()
            sb.advance("G4")
            t = sb.root / "tests" / "test_bytes.py"
            t.write_text("import sys\n\ndef test_emit():\n"
                         "    sys.stdout.buffer.write('한글 CP949 출력'.encode('cp949') + b'\\xff\\xfe')\n"
                         "    sys.stdout.flush()\n", encoding="utf-8")
            (sb.root / "pytest.ini").write_text("[pytest]\naddopts = -s\npythonpath = src\n", encoding="utf-8")
            sb.review("G4")
            self.assertEqual(sb.gate("G4")[1]["status"], "PASSED")
            code, res = sb.gate("G5")
            self.assertEqual(res["status"], "PASSED", res)
            ev = sb.root / res["evidence"][0]["path"]
            rec = json.loads(ev.read_text(encoding="utf-8"))
            raw = (ev.parent / "stdout.bin").read_bytes()
            self.assertIn("한글 CP949 출력".encode("cp949") + b"\xff\xfe", raw)
            self.assertEqual(rec["files"]["stdout.bin"]["sha256"], "sha256:" + hashlib.sha256(raw).hexdigest())
            self.assertEqual(rec["exit_code"], 0)
        finally:
            sb.cleanup()


class StdioRobustness(unittest.TestCase):
    def test_cli_without_stdout(self):
        """pythonw-like environment: sys.stdout/sys.stderr are None."""
        code = ("import sys; sys.stdout=None; sys.stderr=None; sys.path.insert(0, %r); "
                "sys.dont_write_bytecode=True; from vmodel_validator.cli import main; "
                "raise SystemExit(main(['version']))") % str(PLUGIN / "validator")
        r = subprocess.run([sys.executable, "-c", code], capture_output=True)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_cp949_console_encoding_does_not_crash(self):
        sb = Sandbox()
        try:
            sb.init()
            sb.new_wi(title="한글 제목 ✓ emoji 🚀")
            env = {**sb.env, "PYTHONIOENCODING": "cp949"}
            r = subprocess.run([sys.executable, str(sb.entry), "status"], cwd=sb.root, env=env, capture_output=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("한글 제목".encode("utf-8"), r.stdout)  # pipes are forced to UTF-8
            env["VMODEL_OUTPUT_ENCODING"] = "cp949"
            r = subprocess.run([sys.executable, str(sb.entry), "status"], cwd=sb.root, env=env, capture_output=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("한글 제목".encode("cp949"), r.stdout)
        finally:
            sb.cleanup()


if __name__ == "__main__":
    unittest.main()

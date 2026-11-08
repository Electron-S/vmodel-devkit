"""Evidence trust: forged PASS data, ledger tampering, validator core tampering (T07, T12, T17)."""
from __future__ import annotations

import json
import shutil
import unittest

from helpers import Sandbox, copy_plugin, has_pytest


@unittest.skipUnless(has_pytest(), "pytest not installed for this interpreter")
class ForgedResults(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox()
        self.sb.init()
        self.sb.new_wi()
        self.sb.advance("G4")

    def tearDown(self):
        self.sb.cleanup()

    def test_T07_pass_report_without_execution_is_rejected(self):
        # The "agent" fabricates every artefact a naive tool might trust.
        fake_dir = self.sb.root / ".vmodel/evidence/WI-001/G5/20261108T000000Z-unit-fake"
        fake_dir.mkdir(parents=True)
        (fake_dir / "record.json").write_text(json.dumps({
            "schema": "vmodel.evidence/1", "work_item": "WI-001", "gate": "G5", "exit_code": 0,
            "junit_summary": {"tests": 9, "failures": 0}, "sig": "hmac-sha256:" + "0" * 64}), encoding="utf-8")
        (self.sb.wi_dir / "test-results.json").write_text('{"G5": "PASSED", "tests": 9, "failures": 0}',
                                                          encoding="utf-8")
        (self.sb.wi_dir / "reviews" / "G5.json").write_text('{"gate": "G5", "verdict": "approve"}', encoding="utf-8")
        self.assertEqual(self.sb.gate_status("G5"), "IN_PROGRESS")
        self.assertNotEqual(self.sb.status()["work_items"][0]["status"], "PARTIALLY_VERIFIED")
        code, out = self.sb.vm("verify-evidence", str(fake_dir / "record.json"))
        self.assertEqual(code, 1)
        self.assertIn("invalid signature", out)
        self.assertIn("not referenced by the signed ledger", out)
        code, out = self.sb.vm("audit")
        self.assertEqual(code, 1)
        self.assertIn("not referenced by the ledger", out)

    def test_T17_injected_ledger_record_detected(self):
        ledger = self.sb.root / ".vmodel/state/ledger.jsonl"
        lines = ledger.read_text(encoding="utf-8").splitlines()
        last = json.loads(lines[-1])
        forged = {"seq": last["seq"] + 1, "prev": "sha256:" + "a" * 64,
                  "record": {"type": "gate", "work_item": "WI-001", "gate": "G5", "status": "PASSED",
                             "manifest": {"hash": "x", "files": {}}, "validator": {}, "record_id": "R99999"},
                  "sig": "hmac-sha256:" + "b" * 64}
        ledger.write_text("\n".join(lines + [json.dumps(forged)]) + "\n", encoding="utf-8")
        st = self.sb.status()
        self.assertFalse(st["ledger"]["ok"])
        self.assertTrue(all(g["status"] in ("BLOCKED", "NOT_IMPLEMENTED") for g in st["work_items"][0]["gates"]))
        code, res = self.sb.gate("G5")
        self.assertEqual((code, res["status"]), (3, "BLOCKED"))
        self.assertIn("ledger integrity", res["reasons"][0])

    def test_T17_modified_record_detected(self):
        ledger = self.sb.root / ".vmodel/state/ledger.jsonl"
        text = ledger.read_text(encoding="utf-8")
        tampered = text.replace('"status":"REVIEW_REQUIRED"', '"status":"PASSED"', 1)
        if tampered == text:  # no REVIEW_REQUIRED in this history: flip a PASS to FAILED instead
            tampered = text.replace('"status":"PASSED"', '"status":"FAILED"', 1)
        ledger.write_text(tampered, encoding="utf-8")
        st = self.sb.status()
        self.assertFalse(st["ledger"]["ok"])
        self.assertIn("invalid signature", st["ledger"]["error"])

    def test_T17_truncated_ledger_detected(self):
        ledger = self.sb.root / ".vmodel/state/ledger.jsonl"
        lines = ledger.read_text(encoding="utf-8").splitlines()
        ledger.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")
        st = self.sb.status()
        self.assertFalse(st["ledger"]["ok"])
        self.assertIn("head mismatch", st["ledger"]["error"])

    def test_missing_signing_key_blocks(self):
        shutil.rmtree(self.sb.home / "keys")
        code, res = self.sb.gate("G5")
        self.assertEqual(res["status"], "BLOCKED")
        self.assertIn("signing key not found", res["reasons"][0])

    def test_tampered_evidence_detected_by_audit(self):
        code, res = self.sb.gate("G5")
        self.assertEqual(res["status"], "PASSED")
        ev = self.sb.root / res["evidence"][0]["path"]
        (ev.parent / "stdout.bin").write_bytes(b"edited output")
        code, out = self.sb.vm("audit")
        self.assertEqual(code, 1)
        self.assertIn("stdout.bin content differs", out)


class CoreTamper(unittest.TestCase):
    def test_T12_validator_core_modification_blocks(self):
        sb = Sandbox()
        try:
            sb.plugin = copy_plugin(sb.tmp)
            sb.entry = sb.plugin / "validator" / "vmodel.py"
            sb.init()
            sb.new_wi()
            sb.put_artifact("requirements.json")
            sb.review("G1")
            self.assertEqual(sb.gate("G1")[1]["status"], "PASSED")
            gates_py = sb.plugin / "validator" / "vmodel_validator" / "gates.py"
            gates_py.write_text(gates_py.read_text(encoding="utf-8").replace(
                'return {4: "BLOCKED", 3: "FAILED", 2: "REVIEW_REQUIRED"}.get(worst, "PASSED")',
                'return "PASSED"'), encoding="utf-8")
            st = sb.status()
            self.assertFalse(st["validator"]["ok"])
            self.assertTrue(any("core hash does not match" in p for p in st["validator"]["problems"]))
            self.assertEqual(sb.gate_status("G1"), "BLOCKED")
            code, res = sb.gate("G2")
            self.assertEqual((code, res["status"], res["recorded"]), (3, "BLOCKED", False))
            code, out = sb.vm("audit")
            self.assertEqual(code, 1)
        finally:
            sb.cleanup()

    def test_release_manifest_detects_modified_file(self):
        import subprocess
        import sys
        from helpers import REPO
        sb = Sandbox()
        try:
            out = sb.tmp / "dist"
            r = subprocess.run([sys.executable, str(REPO / "scripts" / "release.py"), "--out", str(out),
                                "--no-record"], capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            from vmodel_version import VERSION
            rel = out / f"vmodel-{VERSION}"
            sb.plugin = rel
            sb.entry = rel / "validator" / "vmodel.py"
            code, out_text = sb.vm("version")
            self.assertEqual(code, 0, out_text)
            self.assertIn('"mode": "release"', out_text)
            import os
            import stat
            hj = rel / "hooks" / "hooks.json"
            os.chmod(hj, stat.S_IREAD | stat.S_IWRITE)
            hj.write_text("{}", encoding="utf-8")
            code, out_text = sb.vm("version")
            self.assertEqual(code, 3)
            self.assertIn("modified release file: hooks/hooks.json", out_text)
        finally:
            import os
            import stat
            for f in (sb.tmp / "dist").rglob("*"):
                os.chmod(f, stat.S_IRWXU)
            sb.cleanup()



class Upgrade(unittest.TestCase):
    @unittest.skipUnless(__import__("sys").platform != "win32", "pty is POSIX only")
    def test_upgrade_requires_user_repin_and_stales_previous_passes(self):
        import os
        import pty
        import sys
        sb = Sandbox()
        try:
            sb.plugin = copy_plugin(sb.tmp)
            sb.entry = sb.plugin / "validator" / "vmodel.py"
            sb.init()
            sb.new_wi()
            sb.put_artifact("requirements.json")
            sb.review("G1")
            self.assertEqual(sb.gate("G1")[1]["status"], "PASSED")
            # "new version": a changed validator core
            init_py = sb.plugin / "validator" / "vmodel_validator" / "__init__.py"
            init_py.write_text(init_py.read_text(encoding="utf-8") + "# 0.1.0+upgrade\n", encoding="utf-8")
            self.assertEqual(sb.gate_status("G1"), "BLOCKED")
            code, out = sb.vm("lock", "--accept-current", "--reason", "agent")  # no TTY -> refused
            self.assertEqual(code, 3)
            buf = sb.run_tty("lock", "--accept-current", "--reason", "upgrade")
            self.assertIn(b"re-pinned", buf)
            st = sb.status()
            self.assertTrue(st["validator"]["ok"])
            g1 = [g for g in st["work_items"][0]["gates"] if g["gate"] == "G1"][0]
            self.assertEqual(g1["status"], "STALE")
            self.assertIn("validator core changed since this PASS", g1["notes"])
            self.assertEqual(sb.gate("G1")[1]["status"], "PASSED")  # re-verified with the new core
        finally:
            sb.cleanup()


if __name__ == "__main__":
    unittest.main()

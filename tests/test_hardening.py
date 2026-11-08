"""Regression tests for the independent review findings (2026-11-08): bypasses of the evidence model."""
from __future__ import annotations

import json
import os
import shutil
import sys
import unittest

from helpers import PLUGIN, Sandbox, has_pytest


def _ids(res: dict, cid: str) -> dict:
    return [c for c in res.get("checks") or [] if c["id"] == cid][0]


class HookHardening(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sb = Sandbox()
        cls.sb.init()
        cls.sb.new_wi()

    @classmethod
    def tearDownClass(cls):
        cls.sb.cleanup()

    def deny(self, cmd: str, agent_type: str | None = None, tool: str = "Bash") -> bool:
        payload = {"tool_name": tool, "tool_input": {"command": cmd}, "cwd": str(self.sb.root)}
        if agent_type:
            payload["agent_type"] = agent_type
        code, out = self.sb.hook("guard", payload)
        self.assertEqual(code, 0, out)
        return '"deny"' in out

    def test_C1_wiping_vmodel_denied(self):
        for cmd in ("rm -rf .vmodel", "rm -rf .vmodel/st*", "cd .vmodel && rm -r state", "mv .vmodel /tmp/x",
                    "git clean -fdx", "find . -name '*.jsonl' -delete"):
            self.assertTrue(self.deny(cmd), cmd)

    def test_C1_user_only_lifecycle_commands_denied(self):
        vm = str(PLUGIN / "bin" / "vmodel")
        for sub in ("uninstall --purge", "init --project .", "install --project .", "unblock WI-001 G5 --reason x",
                    "lock --accept-current"):
            self.assertTrue(self.deny(f'"{vm}" {sub}'), sub)

    def test_C2_review_forgery_through_bash_denied(self):
        cmd = "cat > .vmodel/work-items/WI-001/reviews/G1.json <<'EOF'\n{}\nEOF"
        self.assertTrue(self.deny(cmd))
        vm = str(PLUGIN / "bin" / "vmodel")
        self.assertTrue(self.deny(f'"{vm}" review-submit WI-001 G1'))  # main session
        self.assertFalse(self.deny(f'"{vm}" review-submit WI-001 G1', agent_type="vmodel:verifier"))

    def test_powershell_tool_is_guarded(self):
        self.assertTrue(self.deny("Remove-Item -Recurse .vmodel", tool="PowerShell"))

    def test_M5_no_false_positives(self):
        for cmd in ("python3 -m pytest tests/test_vmodel_validator.py 2>&1 | tail -20", "git add plugins/vmodel",
                    "cat .vmodel/work-items/WI-001/requirements.json", "git status", "git diff --stat"):
            self.assertFalse(self.deny(cmd), cmd)


class LifecycleAnchors(unittest.TestCase):
    def test_C1_reinit_after_wipe_refused_and_rollback_detected(self):
        sb = Sandbox()
        try:
            sb.init()
            sb.new_wi()
            sb.put_artifact("requirements.json")
            sb.review("G1")
            self.assertEqual(sb.gate("G1")[1]["status"], "PASSED")
            ledger = sb.root / ".vmodel/state/ledger.jsonl"
            head = sb.root / ".vmodel/state/head.json"
            old_l, old_h = ledger.read_bytes(), head.read_bytes()
            sb.gate("G1")  # one more record
            ledger.write_bytes(old_l)  # roll back both files to an earlier, validly signed state
            head.write_bytes(old_h)
            st = sb.status()
            self.assertFalse(st["ledger"]["ok"])
            self.assertIn("anchor", st["ledger"]["error"])
            shutil.rmtree(sb.root / ".vmodel")  # simulated wipe (bypassing the hook)
            code, out = sb.vm("init", "--project", str(sb.root), "--lint", "none", "--allow-syntax-only")
            self.assertEqual(code, 2, out)
            self.assertIn("was a VModel project", out)
        finally:
            sb.cleanup()


@unittest.skipUnless(has_pytest(), "pytest not installed for this interpreter")
class ExecutionHardening(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox()
        self.sb.init()
        self.sb.new_wi()

    def tearDown(self):
        self.sb.cleanup()

    def g4(self) -> dict:
        self.sb.review("G4")
        return self.sb.gate("G4")[1]

    def test_C3_root_level_module_outside_configured_paths_fails_g4(self):
        self.sb.advance("G3")
        self.sb.put_code()
        (self.sb.root / "pytest.py").write_text("raise SystemExit(0)\n", encoding="utf-8")
        res = self.g4()
        self.assertEqual(res["status"], "FAILED")
        self.assertIn("pytest.py", " ".join(_ids(res, "G4.UNEXPECTED_CODE")["items"]))

    def test_C3_python_file_hidden_in_pycache_fails_g4(self):
        self.sb.advance("G3")
        self.sb.put_code()
        (self.sb.root / "tests/__pycache__").mkdir(exist_ok=True)
        (self.sb.root / "tests/__pycache__/test_hidden.py").write_text("def test_x():\n    pass\n", encoding="utf-8")
        self.assertEqual(self.g4()["status"], "FAILED")

    @unittest.skipIf(sys.platform == "win32", "symlinks need privileges on Windows")
    def test_C3_symlink_in_tree_fails_g4(self):
        self.sb.advance("G3")
        self.sb.put_code()
        outside = self.sb.tmp / "outside"
        outside.mkdir()
        os.symlink(outside, self.sb.root / "src" / "textstats" / "linked")
        self.assertIn("symlink", " ".join(_ids(self.g4(), "G4.UNEXPECTED_CODE")["items"]).lower())

    def test_M2_test_data_change_makes_stale(self):
        self.sb.advance("G5")
        (self.sb.root / "tests" / "expected.txt").write_text("golden", encoding="utf-8")
        self.assertEqual(self.sb.gate_status("G5"), "STALE")

    def test_C3_ambient_pytest_env_is_scrubbed(self):
        self.sb.advance("G4")
        env = {**self.sb.env, "PYTEST_ADDOPTS": "--collect-only -q", "PYTHONPATH": str(self.sb.tmp)}
        code, out = self.sb.vm("gate", "WI-001", "G5", "--json", env=env)
        res = json.loads(out)
        self.assertEqual(res["status"], "PASSED", out[:3000])
        rec = json.loads((self.sb.root / res["evidence"][0]["path"]).read_text(encoding="utf-8"))
        self.assertIn("PYTEST_ADDOPTS", rec["environment"]["scrubbed"])

    def test_C4_result_tampering_conftest_fails_g4(self):
        self.sb.advance("G3")
        self.sb.put_code()
        (self.sb.root / "tests/conftest.py").write_text(
            "import pytest\n\n@pytest.hookimpl(trylast=True)\ndef pytest_sessionfinish(session):\n"
            "    session.exitstatus = 0\n", encoding="utf-8")
        res = self.g4()
        self.assertEqual(res["status"], "FAILED")
        self.assertTrue(_ids(res, "G4.TEST_INTEGRITY")["items"])

    def test_H1_one_test_cannot_claim_many_ids(self):
        self.sb.advance("G3")
        self.sb.put_code()
        t = self.sb.root / "tests/test_wordfreq.py"
        t.write_text(t.read_text(encoding="utf-8").replace("def test_TEST_001_tokenize_lowercases",
                                                           "def test_TEST_001_TEST_002_tokenize_lowercases"),
                     encoding="utf-8")
        res = self.g4()
        self.assertEqual(res["status"], "FAILED")
        self.assertIn("more than one TEST id", " ".join(_ids(res, "G4.TEST_CODE")["items"]))

    def test_H1_comment_does_not_count_as_test_code(self):
        self.sb.advance("G3")
        self.sb.put_code()
        t = self.sb.root / "tests/test_wordfreq.py"
        src = t.read_text(encoding="utf-8")
        cut, end = src.index("def test_TEST_009"), src.index("def test_TEST_010")
        t.write_text(src[:cut] + "# TEST_009 covered elsewhere\n\n\n" + src[end:], encoding="utf-8")
        self.assertEqual(_ids(self.g4(), "G4.TEST_CODE")["items"], ["TEST-009"])

    def test_upstream_failure_invalidates_downstream_pass(self):
        self.sb.advance("G2")
        self.sb.review("G1", verdict="reject", findings=[{"id": "F", "severity": "major", "description": "x",
                                                          "status": "open"}])
        self.assertEqual(self.sb.gate("G1")[1]["status"], "FAILED")
        self.assertEqual(self.sb.gate_status("G2"), "STALE")


class StatusRobustness(unittest.TestCase):
    def test_H2_lite_profile_never_completed(self):
        sb = Sandbox()
        try:
            sb.init()
            code, out = sb.vm("new-wi", "--title", "x", "--request", "y", "--profile", "LITE")
            self.assertEqual(code, 2, out)
            self.assertIn("not implemented", out)
            sb.new_wi()
            wi = sb.load("workitem.json")
            wi["profile"] = "LITE"
            sb.save("workitem.json", wi)
            self.assertNotEqual(sb.status()["work_items"][0]["status"], "COMPLETED")
            wi["profile"] = "BOGUS"
            sb.save("workitem.json", wi)
            self.assertEqual(sb.status()["work_items"][0]["status"], "BLOCKED")
        finally:
            sb.cleanup()

    def test_M4_malformed_json_shapes_do_not_crash(self):
        sb = Sandbox()
        try:
            sb.init()
            sb.new_wi()
            sb.put_artifact("requirements.json")
            (sb.wi_dir / "defects.json").write_text("[1]", encoding="utf-8")
            (sb.wi_dir / "change-requests.json").write_text('{"change_requests": [1, "x"]}', encoding="utf-8")
            sb.review("G1")
            code, out = sb.vm("gate", "WI-001", "G1")
            self.assertIn(code, (1, 3, 4), out)
            self.assertNotIn("Traceback", out)
            (sb.wi_dir / "workitem.json").write_text("[]", encoding="utf-8")
            code, out = sb.vm("status")
            self.assertNotIn("Traceback", out)
            code, out = sb.vm("report", "WI-001")
            self.assertNotIn("Traceback", out)
        finally:
            sb.cleanup()


if __name__ == "__main__":
    unittest.main()

"""Project install / uninstall, existing Claude settings preservation (T15, T16)."""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import Sandbox, has_pytest


class Install(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox()

    def tearDown(self):
        self.sb.cleanup()

    def write_existing_claude_config(self):
        (self.sb.root / ".claude").mkdir()
        self.settings = {"permissions": {"allow": ["Bash(npm test)", "Edit(.vmodel/state/**)"],
                                         "deny": ["Read(./.env)"]},
                         "hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command",
                                                                                 "command": "echo user-hook"}]}]},
                         "env": {"FOO": "bar"}}
        (self.sb.root / ".claude/settings.json").write_text(json.dumps(self.settings, indent=2), encoding="utf-8")
        self.claude_md = "# 우리 프로젝트 규칙\n\n- 테스트는 pytest로\n"
        (self.sb.root / "CLAUDE.md").write_text(self.claude_md, encoding="utf-8")

    def test_T16_existing_settings_preserved_and_conflicts_reported(self):
        self.write_existing_claude_config()
        code, out = self.sb.vm("install", "--project", str(self.sb.root), "--lint", "none", "--allow-syntax-only")
        self.assertEqual(code, 0, out)
        self.assertIn("CONFLICT: permissions.allow has 'Edit(.vmodel/state/**)'", out)
        self.assertIn("CONFLICT: project settings already define PreToolUse hooks", out)
        merged = json.loads((self.sb.root / ".claude/settings.json").read_text(encoding="utf-8"))
        self.assertEqual(merged["hooks"], self.settings["hooks"])
        self.assertEqual(merged["env"], self.settings["env"])
        self.assertEqual(merged["permissions"]["deny"][0], "Read(./.env)")
        self.assertIn("Edit(/.vmodel/state/**)", merged["permissions"]["deny"])
        self.assertEqual(merged["permissions"]["allow"][:2], self.settings["permissions"]["allow"])
        self.assertIn("Bash(vmodel *)", merged["permissions"]["allow"])
        self.assertEqual((self.sb.root / "CLAUDE.md").read_text(encoding="utf-8"), self.claude_md)  # untouched
        backups = list((self.sb.root / ".vmodel/install/backup").iterdir())
        self.assertEqual(json.loads(backups[0].read_text(encoding="utf-8")), self.settings)
        # uninstall restores exactly what was there
        code, out = self.sb.vm("uninstall", "--project", str(self.sb.root))
        self.assertEqual(code, 0, out)
        self.assertEqual(json.loads((self.sb.root / ".claude/settings.json").read_text(encoding="utf-8")),
                         self.settings)
        self.assertTrue((self.sb.root / ".vmodel/config.json").exists())  # data kept without --purge

    def test_claude_md_import_is_optional_and_reversible(self):
        self.write_existing_claude_config()
        code, out = self.sb.vm("install", "--project", str(self.sb.root), "--lint", "none", "--allow-syntax-only",
                               "--claude-md-import")
        self.assertEqual(code, 0, out)
        text = (self.sb.root / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertTrue(text.startswith(self.claude_md))
        self.assertTrue(text.rstrip().endswith("@.vmodel/VMODEL.md"))
        self.assertTrue((self.sb.root / ".vmodel/VMODEL.md").exists())
        self.sb.vm("uninstall", "--project", str(self.sb.root))
        self.assertEqual((self.sb.root / "CLAUDE.md").read_text(encoding="utf-8"), self.claude_md)

    def test_no_prior_settings_created_and_removed(self):
        code, out = self.sb.vm("install", "--project", str(self.sb.root), "--lint", "none", "--allow-syntax-only",
                               "--enable-plugin", str(self.sb.tmp / "dist"))
        self.assertEqual(code, 0, out)
        s = json.loads((self.sb.root / ".claude/settings.json").read_text(encoding="utf-8"))
        self.assertEqual(s["enabledPlugins"], {"vmodel@vmodel-devkit": True})
        self.assertEqual(s["extraKnownMarketplaces"]["vmodel-devkit"]["source"]["source"], "directory")
        code, out = self.sb.vm("uninstall", "--project", str(self.sb.root), "--purge")
        self.assertEqual(code, 3, out)  # purge is user-only (TTY)
        self.assertTrue((self.sb.root / ".vmodel").exists())
        code, out = self.sb.vm("uninstall", "--project", str(self.sb.root))
        self.assertEqual(code, 0, out)
        self.assertFalse((self.sb.root / ".claude").exists())
        if sys.platform != "win32":
            out = self.sb.run_tty("uninstall", "--project", str(self.sb.root), "--purge")
            self.assertIn(b"purged", out)
            self.assertFalse((self.sb.root / ".vmodel").exists())
            self.assertFalse(any((self.sb.home / "keys").iterdir()))
            self.assertFalse(any((self.sb.home / "anchors").iterdir()))

    def test_invalid_existing_settings_not_touched(self):
        (self.sb.root / ".claude").mkdir()
        (self.sb.root / ".claude/settings.json").write_text("{ broken", encoding="utf-8")
        code, out = self.sb.vm("install", "--project", str(self.sb.root), "--lint", "none", "--allow-syntax-only")
        self.assertEqual(code, 2)
        self.assertIn("not valid JSON", out)
        self.assertEqual((self.sb.root / ".claude/settings.json").read_text(encoding="utf-8"), "{ broken")

    def test_init_refuses_to_overwrite(self):
        self.sb.init()
        code, out = self.sb.vm("init", "--project", str(self.sb.root))
        self.assertEqual(code, 2)
        self.assertIn("refusing to overwrite", out)


@unittest.skipUnless(has_pytest(), "pytest not installed for this interpreter")
class OtherProject(unittest.TestCase):
    def test_T15_apply_to_a_different_project(self):
        """A second, unrelated project (flat layout, different package) gets its own key and ledger."""
        tmp = Path(tempfile.mkdtemp(prefix="vmodel-other-"))
        try:
            other = tmp / "다른 프로젝트"
            (other / "calc").mkdir(parents=True)
            (other / "tests").mkdir()
            (other / "calc" / "__init__.py").write_text("", encoding="utf-8")
            (other / "calc" / "ops.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
            (other / "tests" / "test_ops.py").write_text(
                "import sys, pathlib\nsys.path.insert(0, str(pathlib.Path(__file__).parents[1]))\n"
                "from calc.ops import add\n\n\ndef test_TEST_001_add():\n    assert add(1, 2) == 3\n",
                encoding="utf-8")
            sb = Sandbox(sample=other)
            try:
                code, out = sb.vm("install", "--project", str(sb.root), "--source", "calc/**/*.py", "--lint", "none",
                                  "--allow-syntax-only")
                self.assertEqual(code, 0, out)
                wi = sb.new_wi("덧셈", "두 수를 더하는 add 함수")
                sb.wi = wi
                sb.save("requirements.json", {
                    "work_item": wi, "conflict_analysis": {"performed": True, "conflicts": []}, "open_issues": [],
                    "requirements": [{"id": "REQ-001", "type": "functional", "title": "덧셈", "priority": "must",
                                      "status": "active", "description": "add(a, b)는 a+b를 반환한다",
                                      "acceptance_criteria": [{"id": "AC-001-1", "criterion": "add(1,2)==3"}]}]})
                sb.save("architecture.json", {
                    "work_item": wi, "components": [{"id": "ARCH-001", "name": "calc", "responsibility": "연산",
                                                     "requirements": ["REQ-001"]}],
                    "interfaces": [], "data_flows": [], "nfr_mapping": [], "tradeoffs": [],
                    "integration_test_strategy": {"approach": "단일 컴포넌트라 통합 대상 없음", "interfaces_covered": []}})
                sb.save("design.json", {"work_item": wi, "units": [{
                    "id": "DESIGN-001", "component": "ARCH-001", "module": "calc/ops.py", "name": "add",
                    "kind": "function", "signature": "def add(a, b)", "description": "합", "requirements": ["REQ-001"],
                    "contract": {"preconditions": [], "postconditions": ["a+b 반환"]}, "errors": [],
                    "boundary_conditions": ["0을 더하면 그대로"]}]})
                sb.save("tests.json", {"work_item": wi, "tests": [
                    {"id": "TEST-001", "level": "unit", "title": "add", "category": "normal",
                     "verifies": ["DESIGN-001"], "procedure": "add(1,2)", "expected": "3"},
                    {"id": "TEST-002", "level": "unit", "title": "add zero", "category": "boundary",
                     "verifies": ["DESIGN-001"], "procedure": "add(0,5)", "expected": "5"},
                    {"id": "TEST-003", "level": "system", "title": "AC", "category": "normal", "verifies": ["REQ-001"],
                     "acceptance_criteria": ["AC-001-1"], "procedure": "add(1,2)", "expected": "3"}]})
                t = sb.root / "tests" / "test_ops.py"
                t.write_text(t.read_text(encoding="utf-8") + "\n\ndef test_TEST_002_add_zero():\n"
                             "    assert add(0, 5) == 5\n", encoding="utf-8")
                for g in ("G1", "G2", "G3", "G4", "G5"):
                    if g != "G5":
                        sb.review(g)
                    code, res = sb.gate(g)
                    self.assertEqual(res["status"], "PASSED", json.dumps(res, indent=1, ensure_ascii=False))
                self.assertEqual(len(list((sb.home / "keys").iterdir())), 1)
            finally:
                sb.cleanup()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()

"""integration_test configuration, init registration and migration (T03, T20; REQ-G6-01, 02, 27, 28)."""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import unittest

from g6_base import RED, SandboxClass, check, wi_status
from helpers import PIPELINE, PLUGIN, Sandbox, has_pytest


def plugin_schema_errors(cfg: dict) -> list[str]:
    spec = importlib.util.spec_from_file_location(
        "plugin_schema_lite", PLUGIN / "validator/vmodel_validator/schema_lite.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    schema = json.loads((PLUGIN / "validator/vmodel_validator/data/schemas/config.schema.json")
                        .read_text(encoding="utf-8"))
    return mod.validate(cfg, schema)


class ConfigRed(SandboxClass):
    """pipeline whose unit command already excludes tests/integration, but no integration_test (G1-G5 PASSED)."""
    split = False

    @classmethod
    def build(cls, sb):
        sb.init()
        sb.new_wi("G6 기능", "통합 검증 대상 기능을 개발해줘")
        cfg = sb.config()
        cfg["unit_test"]["argv"] = ["{python}", "-m", "pytest", "-q", "-p", "no:cacheprovider",
                                    "--ignore=tests/integration", "--junitxml={junit}"]
        sb.set_config(cfg)
        from g6_base import advance
        advance(sb, "G5")

    def test_T03_missing_integration_test_blocks_without_running_anything(self):
        code, res = self.sb.gate("G6")
        self.assertEqual((res["status"], res.get("blocked_reason")), ("BLOCKED", "misconfigured"),
                         f"{RED} interfaces exist but no integration_test: {res}")
        self.assertEqual(code, 3)
        self.assertTrue(res["recorded"])
        self.assertEqual(res["evidence"], [])
        self.assertFalse((self.sb.root / ".vmodel/evidence/WI-001/G6").exists())  # the unit command was not run
        self.assertIn("integration_test", check(self, res, "G6.CONFIG")["detail"])
        nxt = wi_status(self.sb)["next_action"]
        self.assertIn("integration_test", nxt)
        self.assertIn("user", nxt.lower())

    def _set(self, integ: object) -> dict:
        cfg = self.sb.config()
        cfg["integration_test"] = integ
        self.sb.set_config(cfg)
        self.regate("G4", "G5")
        return self.sb.gate("G6")

    def test_A2_integration_argv_without_junit_is_misconfigured(self):
        code, res = self._set({"argv": ["{python}", "-m", "pytest", "tests/integration"], "timeout_s": 60})
        self.assertEqual((res["status"], res.get("blocked_reason")), ("BLOCKED", "misconfigured"), f"{RED} {res}")
        self.assertEqual(res["evidence"], [])

    def test_A3_invalid_integration_test_object_is_misconfigured_not_a_crash(self):
        for bad in ({"argv": "pytest tests/integration --junitxml={junit}", "timeout_s": 60},
                    {"argv": ["{python}", "-m", "pytest", "--junitxml={junit}"]},
                    {"argv": ["{python}", "-m", "pytest", "--junitxml={junit}"], "timeout_s": 0},
                    "pytest"):
            self.sb.restore()
            code, res = self._set(bad)
            self.assertEqual((code, res["status"], res.get("blocked_reason")), (3, "BLOCKED", "misconfigured"),
                             f"{RED} {bad!r}: {res}")


class ConfigChar(unittest.TestCase):
    def test_A5_015_config_without_integration_test_is_valid(self):
        sb = Sandbox()
        try:
            sb.init()
            cfg = sb.config()
            self.assertNotIn("integration_test", cfg)  # no tests/integration in the sample: nothing registered
            self.assertEqual(plugin_schema_errors(cfg), [])
        finally:
            sb.cleanup()


@unittest.skipUnless(has_pytest(), "pytest not installed")
class InitRed(unittest.TestCase):
    """REQ-G6-27: only an existing integration test path with test functions is registered; scopes never overlap."""

    def setUp(self):
        self.sb = Sandbox(fixture=PIPELINE)

    def tearDown(self):
        self.sb.cleanup()

    def init(self, *extra: str) -> tuple[int, str]:
        return self.sb.vm("init", "--project", str(self.sb.root), "--lint", "none", "--allow-syntax-only", *extra)

    def test_T20_existing_integration_dir_is_registered_and_excluded_from_unit(self):
        self.sb.put_code()
        code, out = self.init()
        self.assertEqual(code, 0, out)
        cfg = self.sb.config()
        self.assertIn("integration_test", cfg, f"{RED} tests/integration exists with tests: {out}")
        self.assertIn("tests/integration", cfg["integration_test"]["argv"])
        self.assertIn("{junit}", " ".join(cfg["integration_test"]["argv"]))
        self.assertIn("--ignore=tests/integration", cfg["unit_test"]["argv"])
        self.assertNotIn("tests/integration", cfg["unit_test"]["argv"])
        self.assertEqual(plugin_schema_errors(cfg), [])

    def test_T20_no_integration_dir_registers_nothing_and_says_so(self):
        code, out = self.init()
        self.assertEqual(code, 0, out)
        self.assertNotIn("integration_test", self.sb.config())
        self.assertNotIn("--ignore=tests/integration", self.sb.config()["unit_test"]["argv"])
        self.assertIn("integration_test: not configured", out, f"{RED} init must say G6 needs it: {out}")

    def test_T20_explicit_missing_path_is_refused(self):
        code, out = self.init("--integration-tests", "tests/it")
        self.assertNotEqual(code, 0)
        self.assertIn("does not exist", out, f"{RED} {out}")
        self.assertFalse((self.sb.root / ".vmodel").exists())
        self.assertFalse((self.sb.root / "tests/it").exists())  # never created

    def test_T20_explicit_path_without_test_functions_is_refused(self):
        d = self.sb.root / "tests/it"
        d.mkdir(parents=True)
        (d / "test_nothing.py").write_text("X = 1\n", encoding="utf-8")
        code, out = self.init("--integration-tests", "tests/it")
        self.assertNotEqual(code, 0)
        self.assertIn("no test function", out, f"{RED} {out}")
        self.assertFalse((self.sb.root / ".vmodel").exists())

    def test_T20_whole_unit_scope_is_refused(self):
        self.sb.put_code()
        code, out = self.init("--integration-tests", "tests")
        self.assertNotEqual(code, 0)
        self.assertIn("same scope", out, f"{RED} {out}")
        self.assertFalse((self.sb.root / ".vmodel").exists())

    def test_T20_explicit_existing_path_is_registered(self):
        self.sb.put_code()
        shutil.move(str(self.sb.root / "tests/integration"), str(self.sb.root / "tests/it"))
        code, out = self.init("--integration-tests", "tests/it")
        self.assertEqual(code, 0, f"{RED} {out}")
        cfg = self.sb.config()
        self.assertIn("tests/it", cfg["integration_test"]["argv"])
        self.assertIn("--ignore=tests/it", cfg["unit_test"]["argv"])


@unittest.skipUnless(has_pytest() and os.name == "posix", "pytest and a POSIX pty are needed")
class MigrationRed(unittest.TestCase):
    """REQ-G6-28: an existing project adds integration_test with a user-only command."""

    def setUp(self):
        self.sb = Sandbox(fixture=PIPELINE)
        self.sb.init()
        self.sb.put_code()

    def tearDown(self):
        self.sb.cleanup()

    def test_T20_configure_tests_needs_a_terminal(self):
        before = (self.sb.root / ".vmodel/config.json").read_bytes()
        code, out = self.sb.vm("configure-tests", "--integration", "tests/integration")
        self.assertEqual(code, 3, f"{RED} user-only command without a TTY: {out}")
        self.assertIn("interactive terminal", out)
        self.assertEqual((self.sb.root / ".vmodel/config.json").read_bytes(), before)

    def test_T20_configure_tests_on_a_terminal_updates_config_and_ledger(self):
        out = self.sb.run_tty("configure-tests", "--integration", "tests/integration").decode("utf-8", "replace")
        cfg = self.sb.config()
        self.assertIn("integration_test", cfg, f"{RED} {out}")
        self.assertIn("--ignore=tests/integration", cfg["unit_test"]["argv"])
        self.assertIn("tests/integration", cfg["integration_test"]["argv"])
        recs = [json.loads(ln)["record"] for ln in
                (self.sb.root / ".vmodel/state/ledger.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual([r["type"] for r in recs if r["type"] == "config"], ["config"])
        self.assertEqual(self.sb.vm("audit")[0], 0)

    def test_T20_configure_tests_refuses_a_missing_path(self):
        before = (self.sb.root / ".vmodel/config.json").read_bytes()
        out = self.sb.run_tty("configure-tests", "--integration", "tests/nope").decode("utf-8", "replace")
        self.assertIn("does not exist", out, f"{RED} {out}")
        self.assertEqual((self.sb.root / ".vmodel/config.json").read_bytes(), before)

    def test_T20_guard_blocks_the_agent(self):
        code, out = self.sb.hook("guard", {"hook_event_name": "PreToolUse", "tool_name": "Bash", "cwd": str(self.sb.root),
                                           "tool_input": {"command": "vmodel configure-tests --integration tests/integration"}})
        self.assertIn('"deny"', out, f"{RED} configure-tests is user-only: {out}")


if __name__ == "__main__":
    unittest.main()

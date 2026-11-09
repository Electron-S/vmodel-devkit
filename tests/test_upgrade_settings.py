"""v0.1.5: project permission rules follow the release on upgrade (docs/v0.1.5/WORKITEM.md, DECISIONS D38).

`vmodel install` writes rules with the release's absolute path into .claude/settings.json (deny on the plugin
root, allow for its bin/vmodel). Up to 0.1.4 the upgrade step (`lock --accept-current` with the new release) left
them pointing at the old release. Each test installs with an older immutable release (dist/vmodel-0.1.3, or the git
tag) into a project that already has user settings, switches to the plugin under test and re-pins as a user at a
terminal (pty).

Class suffixes (scripts/red_green.py): ...Red must fail on the 0.1.4 release and pass on the fix; ...Char and
...Invariant pass on both; ...Accept is checked on the fix only.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import unittest
from pathlib import Path

from helpers import PLUGIN, Sandbox, has_pytest, old_release

POSIX = sys.platform != "win32"
OLD_VERSION = "0.1.3"


def plugin_version(plugin: Path) -> str:
    text = (plugin / "validator" / "vmodel_validator" / "__init__.py").read_text(encoding="utf-8")
    m = re.search(r'VERSION = "([^"]+)"', text)
    assert m, plugin
    return m.group(1)


def abs_rule(tool: str, path: Path, suffix: str = "/**") -> str:
    """Independent restatement of the documented rule format ('//' anchors at the filesystem root)."""
    s = path.resolve().as_posix()
    if s.startswith("/"):
        return f"{tool}(/{s}{suffix})"
    return f"{tool}(//{s[0].lower()}{s[2:]}{suffix})"


def core_deny(plugin: Path) -> str:
    return abs_rule("Edit", plugin)


def cli_allow(plugin: Path) -> list[str]:
    vm = (plugin / "bin" / "vmodel").resolve().as_posix()
    return [f"Bash({vm} *)", f'Bash("{vm}" *)']


def user_settings(old: Path) -> dict:
    return {"permissions": {"allow": ["Bash(npm test)", f"Read(/{old.resolve().as_posix()}/README.md)"],
                            "deny": ["Read(./.env)"]},
            "hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "echo user-hook"}]}]},
            "env": {"FOO": "bar"}}


class Base(unittest.TestCase):
    old_version = OLD_VERSION

    def setUp(self):
        old = old_release(self.old_version)
        if old is None:
            self.skipTest(f"{self.old_version} release not available")
        self.old: Path = old
        self.sbs: list[Sandbox] = []

    def tearDown(self):
        for sb in self.sbs:
            for p in (sb.root / ".claude", sb.root / ".vmodel" / "state"):
                if p.exists():
                    os.chmod(p, 0o755)
            sb.cleanup()

    # ------------------------------------------------------------ helpers
    def installed(self, settings: dict | None = None, *, user: bool = True) -> Sandbox:
        """A project installed by the old release (with user settings), then switched to the plugin under test."""
        sb = Sandbox(plugin=self.old)
        self.sbs.append(sb)
        if user:
            settings = settings or user_settings(self.old)
            (sb.root / ".claude").mkdir()
            (sb.root / ".claude" / "settings.json").write_text(json.dumps(settings, indent=2), encoding="utf-8")
        code, out = sb.vm("install", "--project", str(sb.root), "--lint", "none", "--allow-syntax-only")
        self.assertEqual(code, 0, out)
        self.use(sb, PLUGIN)
        return sb

    @staticmethod
    def use(sb: Sandbox, plugin: Path) -> None:
        sb.plugin, sb.entry = plugin, plugin / "validator" / "vmodel.py"

    @staticmethod
    def settings(sb: Sandbox) -> dict:
        return json.loads((sb.root / ".claude" / "settings.json").read_text(encoding="utf-8"))

    @staticmethod
    def record(sb: Sandbox) -> dict:
        return json.loads((sb.root / ".vmodel" / "install-record.json").read_text(encoding="utf-8"))

    @staticmethod
    def snapshot(sb: Sandbox) -> dict:
        files = [".claude/settings.json", ".vmodel/install-record.json", ".vmodel/devkit.lock.json",
                 ".vmodel/state/ledger.jsonl", ".vmodel/state/head.json"]
        return {f: (sb.root / f).read_bytes() if (sb.root / f).exists() else None for f in files}

    def upgrade(self, sb: Sandbox, answer: bytes = b"yes\n") -> str:
        return sb.run_tty("lock", "--accept-current", "--reason", "upgrade", answer=answer).decode("utf-8", "replace")

    def assert_rules_on(self, sb: Sandbox, plugin: Path, old: Path) -> None:
        s = self.settings(sb)
        deny, allow = s["permissions"]["deny"], s["permissions"]["allow"]
        self.assertIn(core_deny(plugin), deny)
        for r in cli_allow(plugin):
            self.assertIn(r, allow)
        self.assertNotIn(core_deny(old), deny)
        for r in cli_allow(old):
            self.assertNotIn(r, allow)


@unittest.skipUnless(POSIX, "re-pinning needs a pty (POSIX only)")
class UpgradeSettingsRed(Base):
    def test_rules_follow_the_new_release_after_repin(self):
        sb = self.installed()
        out = self.upgrade(sb)
        self.assertIn("re-pinned", out)
        self.assert_rules_on(sb, PLUGIN, self.old)
        # a user rule that mentions the old release path is the user's, not the DevKit's
        self.assertIn(f"Read(/{self.old.resolve().as_posix()}/README.md)", self.settings(sb)["permissions"]["allow"])

    def test_install_record_tracks_the_new_release(self):
        sb = self.installed()
        self.upgrade(sb)
        rec, s = self.record(sb), self.settings(sb)
        self.assertEqual(Path(rec["plugin_root"]).resolve(), PLUGIN.resolve())
        self.assertEqual(rec["validator_version"], plugin_version(PLUGIN))
        user = user_settings(self.old)["permissions"]
        self.assertEqual(rec["added_deny"], [r for r in s["permissions"]["deny"] if r not in user["deny"]])
        self.assertEqual(rec["added_allow"], [r for r in s["permissions"]["allow"] if r not in user["allow"]])
        old_path = self.old.resolve().as_posix()
        self.assertFalse([r for r in rec["added_deny"] + rec["added_allow"] if old_path in r])

    def test_user_rule_equal_to_a_devkit_rule_stays_user_owned(self):
        base = user_settings(self.old)
        base["permissions"]["deny"].append("Edit(/.vmodel/state/**)")
        base["permissions"]["allow"].append("Bash(vmodel *)")
        sb = self.installed(base)
        rec = self.record(sb)
        self.assertNotIn("Edit(/.vmodel/state/**)", rec["added_deny"])
        self.assertNotIn("Bash(vmodel *)", rec["added_allow"])
        self.upgrade(sb)
        rec, s = self.record(sb), self.settings(sb)
        self.assertNotIn("Edit(/.vmodel/state/**)", rec["added_deny"])
        self.assertNotIn("Bash(vmodel *)", rec["added_allow"])
        self.assertEqual(s["permissions"]["deny"].count("Edit(/.vmodel/state/**)"), 1)
        self.assertIn(core_deny(PLUGIN), s["permissions"]["deny"])
        code, out = sb.vm("uninstall", "--project", str(sb.root))
        self.assertEqual(code, 0, out)
        self.assertEqual(self.settings(sb), base)

    def test_failed_repin_restores_settings_record_and_lock(self):
        sb = self.installed()
        before = self.snapshot(sb)
        lock_file = sb.root / ".vmodel" / "state" / ".ledger.lock"
        lock_file.write_text("held by another process", encoding="utf-8")  # the ledger append times out (30 s)
        try:
            out = self.upgrade(sb)
        finally:
            lock_file.unlink()
        self.assertNotIn("re-pinned core", out)
        self.assertEqual(self.snapshot(sb), before)
        self.assertIn("re-pinned", self.upgrade(sb))  # the next attempt goes through
        self.assert_rules_on(sb, PLUGIN, self.old)

    def test_unwritable_settings_aborts_without_repinning(self):
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            self.skipTest("root ignores directory permissions")
        sb = self.installed()
        before = self.snapshot(sb)
        os.chmod(sb.root / ".claude", 0o555)
        try:
            out = self.upgrade(sb)
        finally:
            os.chmod(sb.root / ".claude", 0o755)
        self.assertNotIn("re-pinned core", out)
        self.assertEqual(self.snapshot(sb), before)

    def test_interrupted_upgrade_superset_is_completed_on_rerun(self):
        sb = self.installed()
        s, rec = self.settings(sb), self.record(sb)
        s["permissions"]["deny"].append(core_deny(PLUGIN))
        s["permissions"]["allow"].extend(cli_allow(PLUGIN))
        rec["added_deny"].append(core_deny(PLUGIN))
        rec["added_allow"].extend(cli_allow(PLUGIN))
        (sb.root / ".claude" / "settings.json").write_text(json.dumps(s, indent=2), encoding="utf-8")
        (sb.root / ".vmodel" / "install-record.json").write_text(json.dumps(rec, indent=2), encoding="utf-8")
        self.assertIn("re-pinned", self.upgrade(sb))
        self.assert_rules_on(sb, PLUGIN, self.old)
        s = self.settings(sb)
        self.assertEqual(s["permissions"]["deny"].count(core_deny(PLUGIN)), 1)
        user = user_settings(self.old)["permissions"]
        self.assertEqual([r for r in s["permissions"]["allow"] if r in user["allow"]], user["allow"])
        self.assertEqual([r for r in s["permissions"]["deny"] if r in user["deny"]], user["deny"])

    def test_interrupted_after_the_record_write_is_completed_on_rerun(self):
        """The record already owns the new rules, settings do not have them yet (the process died in between)."""
        sb = self.installed()
        rec = self.record(sb)
        rec["added_deny"].append(core_deny(PLUGIN))
        rec["added_allow"].extend(cli_allow(PLUGIN))
        (sb.root / ".vmodel" / "install-record.json").write_text(json.dumps(rec, indent=2), encoding="utf-8")
        self.assertIn("re-pinned", self.upgrade(sb))
        self.assert_rules_on(sb, PLUGIN, self.old)
        rec = self.record(sb)
        self.assertIn(core_deny(PLUGIN), rec["added_deny"])
        code, out = sb.vm("uninstall", "--project", str(sb.root))
        self.assertEqual(code, 0, out)
        self.assertEqual(self.settings(sb), user_settings(self.old))

    def test_plan_is_shown_before_confirmation_and_backup_is_kept(self):
        sb = self.installed()
        before = self.snapshot(sb)
        out = self.upgrade(sb, answer=b"no\n")
        self.assertEqual(self.snapshot(sb), before)
        prompt = out.find("Type 'yes'")
        self.assertGreater(prompt, 0, out)
        for text in (core_deny(PLUGIN), core_deny(self.old), *cli_allow(PLUGIN), *cli_allow(self.old)):
            self.assertIn(text, out[:prompt])
        out = self.upgrade(sb)
        self.assertIn("re-pinned", out)
        backups = sorted((sb.root / ".vmodel" / "install" / "backup").glob("upgrade-*"))
        self.assertEqual(len(backups), 1, out)
        self.assertIn(str(backups[0]), out.replace("\r\n", "\n").replace("\n", ""))
        for rel, name in ((".claude/settings.json", "settings.json"), (".vmodel/install-record.json",
                                                                        "install-record.json"),
                          (".vmodel/devkit.lock.json", "devkit.lock.json")):
            self.assertEqual((backups[0] / name).read_bytes(), before[rel], name)

    def test_install_over_another_release_points_to_the_upgrade(self):
        sb = self.installed()
        before = self.snapshot(sb)
        code, out = sb.vm("install", "--project", str(sb.root), "--lint", "none", "--allow-syntax-only")
        self.assertEqual(code, 2, out)
        self.assertIn("lock --accept-current", out)
        self.assertNotIn("uninstall", out)
        self.assertEqual(self.snapshot(sb), before)

    def test_invalid_settings_aborts_before_repin(self):
        sb = self.installed()
        (sb.root / ".claude" / "settings.json").write_text("{ broken", encoding="utf-8")
        before = self.snapshot(sb)
        out = self.upgrade(sb)
        self.assertIn("not valid JSON", out)
        self.assertNotIn("re-pinned core", out)
        self.assertEqual(self.snapshot(sb), before)


@unittest.skipUnless(POSIX, "re-pinning needs a pty (POSIX only)")
class UpgradeSettingsChar(Base):
    def test_user_settings_survive_upgrade_and_uninstall(self):
        sb = self.installed()
        self.upgrade(sb)
        s, user = self.settings(sb), user_settings(self.old)
        self.assertEqual(s["hooks"], user["hooks"])
        self.assertEqual(s["env"], user["env"])
        for kind in ("allow", "deny"):
            self.assertEqual([r for r in s["permissions"][kind] if r in user["permissions"][kind]],
                             user["permissions"][kind])
        code, out = sb.vm("uninstall", "--project", str(sb.root))
        self.assertEqual(code, 0, out)
        self.assertEqual(self.settings(sb), user)

    def test_repin_without_tty_or_without_yes_changes_nothing(self):
        sb = self.installed()
        before = self.snapshot(sb)
        code, out = sb.vm("lock", "--accept-current", "--reason", "agent")
        self.assertEqual(code, 3, out)
        self.assertEqual(self.snapshot(sb), before)
        out = self.upgrade(sb, answer=b"no\n")
        self.assertNotIn("re-pinned core", out)
        self.assertEqual(self.snapshot(sb), before)

    def test_second_install_and_second_uninstall_change_nothing(self):
        sb = Sandbox()
        self.sbs.append(sb)
        (sb.root / ".claude").mkdir()
        user = user_settings(self.old)
        (sb.root / ".claude" / "settings.json").write_text(json.dumps(user, indent=2), encoding="utf-8")
        code, out = sb.vm("install", "--project", str(sb.root), "--lint", "none", "--allow-syntax-only")
        self.assertEqual(code, 0, out)
        before = self.snapshot(sb)
        code, out = sb.vm("install", "--project", str(sb.root), "--lint", "none", "--allow-syntax-only")
        self.assertEqual(code, 2, out)
        self.assertIn("already installed", out)
        self.assertEqual(self.snapshot(sb), before)
        self.assertEqual(sb.vm("uninstall", "--project", str(sb.root))[0], 0)
        self.assertEqual(self.settings(sb), user)
        after_first = self.snapshot(sb)
        code, out = sb.vm("uninstall", "--project", str(sb.root))
        self.assertEqual(code, 0, out)
        self.assertIn("nothing to do", out)
        self.assertEqual(self.snapshot(sb), after_first)

    def test_repin_of_init_only_project_leaves_settings_alone(self):
        sb = Sandbox(plugin=self.old)
        self.sbs.append(sb)
        sb.init()
        self.use(sb, PLUGIN)
        self.assertIn("re-pinned", self.upgrade(sb))
        self.assertFalse((sb.root / ".claude").exists())
        self.assertTrue(self.status_ok(sb))

    @staticmethod
    def status_ok(sb: Sandbox) -> bool:
        return sb.status()["validator"]["ok"]


class UpgradeSettingsInvariant(Base):
    def decide(self, sb: Sandbox, tool: str, tool_input: dict) -> str:
        code, out = sb.hook("guard", {"tool_name": tool, "tool_input": tool_input, "cwd": str(sb.root)})
        self.assertEqual(code, 0, out)
        return out

    def test_guard_still_blocks_agents_and_protects_the_running_core(self):
        sb = self.installed()
        if POSIX:
            self.upgrade(sb)
        vm = str(PLUGIN / "bin" / "vmodel")
        for cmd in (f'"{vm}" lock --accept-current --reason x', "vmodel lock --accept-current",
                    f'"{vm}" install --project .', "vmodel uninstall", f'"{vm}" uninstall --purge',
                    f'"{vm}" configure-tests --integration tests/integration'):  # 0.2.0 user-only command
            self.assertIn("user-only", self.decide(sb, "Bash", {"command": cmd}), cmd)
        for target in (PLUGIN / "validator" / "vmodel_validator" / "gates.py", PLUGIN / "hooks" / "hooks.json",
                       sb.root / ".vmodel" / "install-record.json", sb.root / ".vmodel" / "devkit.lock.json",
                       sb.root / ".vmodel" / "state" / "ledger.jsonl"):
            self.assertIn('"deny"', self.decide(sb, "Edit", {"file_path": str(target)}), target)
        self.assertIn('"deny"', self.decide(sb, "Bash", {"command": f"echo x >> {PLUGIN / 'bin' / 'vmodel'}"}))
        # the guard itself is unchanged since the 0.1.4 release, except that 0.2.0 adds the user-only
        # 'configure-tests' command (REQ-G6-28, D42) to USER_ONLY and its deny message
        rel = "validator/vmodel_validator/hook.py"
        base = old_release("0.1.4")
        if base is not None:
            now = (PLUGIN / rel).read_text(encoding="utf-8")
            if "configure-tests" in now:
                now = now.replace('|unblock|configure-tests)\\b|accept-current",\n                       re.IGNORECASE)',
                                  '|unblock)\\b|accept-current", re.IGNORECASE)')
                now = now.replace("init/install/uninstall/unblock/configure-tests and", "init/install/uninstall/unblock and")
            self.assertEqual(now, (base / rel).read_text(encoding="utf-8"))


@unittest.skipUnless(POSIX, "re-pinning needs a pty (POSIX only)")
class UpgradeSettingsAccept(Base):
    def test_second_upgrade_is_a_no_op_for_settings(self):
        sb = self.installed()
        self.assertIn("re-pinned", self.upgrade(sb))
        backups = lambda: sorted((sb.root / ".vmodel" / "install" / "backup").glob("upgrade-*"))  # noqa: E731
        first = self.snapshot(sb)
        n = len(backups())
        out = self.upgrade(sb)
        self.assertIn("re-pinned", out)
        second = self.snapshot(sb)
        for rel in (".claude/settings.json", ".vmodel/install-record.json"):
            self.assertEqual(second[rel], first[rel], rel)
        self.assertEqual(len(backups()), n)

    def test_upgrade_from_014_release_then_014_uninstall(self):
        old14 = old_release("0.1.4")
        if old14 is None:
            self.skipTest("0.1.4 release not available")
        self.old = old14
        sb = self.installed()
        self.assertEqual(Path(self.record(sb)["plugin_root"]).resolve(), old14.resolve())
        self.assertIn("re-pinned", self.upgrade(sb))
        self.assert_rules_on(sb, PLUGIN, old14)
        self.use(sb, old14)  # the previous release's uninstall reads the updated record
        code, out = sb.vm("uninstall", "--project", str(sb.root))
        self.assertEqual(code, 0, out)
        self.assertEqual(self.settings(sb), user_settings(old14))

    @unittest.skipUnless(has_pytest(), "pytest not installed")
    def test_gates_still_pass_after_upgrade(self):
        sb = Sandbox(plugin=self.old)
        self.sbs.append(sb)
        code, out = sb.vm("install", "--project", str(sb.root), "--lint", "none", "--allow-syntax-only")
        self.assertEqual(code, 0, out)
        sb.new_wi()
        sb.advance("G5")
        ledger = (sb.root / ".vmodel" / "state" / "ledger.jsonl").read_bytes()
        self.use(sb, PLUGIN)
        self.assertIn("re-pinned", self.upgrade(sb))
        self.assertTrue((sb.root / ".vmodel" / "state" / "ledger.jsonl").read_bytes().startswith(ledger))
        gates = {g["gate"]: g["status"] for g in sb.status()["work_items"][0]["gates"]}
        self.assertEqual(set(gates[g] for g in ("G1", "G2", "G3", "G4", "G5")), {"STALE"})
        for g in ("G1", "G2", "G3", "G4", "G5"):
            if g != "G5":
                sb.review(g)
            self.assertEqual(sb.gate(g)[1]["status"], "PASSED", g)
        self.assertEqual(sb.vm("audit")[0], 0)


class UpgradeSettingsInProcessAccept(Base):
    """The plan/transaction API without a terminal, so that the settings rewrite also runs on Windows paths."""

    DRIVER = r"""
import json, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from vmodel_validator.project import Project
from vmodel_validator.setup_project import plan_settings_sync, upgrade_project
root = Path(sys.argv[2])
plan = plan_settings_sync(root)
res = upgrade_project(Project(root), "in-process upgrade", plan)
sys.stdout.write(json.dumps({"plan": plan, "result": res}, default=str))
"""

    def run_driver(self, sb: Sandbox) -> dict:
        r = subprocess.run([sys.executable, "-I", "-B", "-c", self.DRIVER, str(PLUGIN / "validator"), str(sb.root)],
                           cwd=str(sb.root), env=sb.env, capture_output=True, timeout=300)
        self.assertEqual(r.returncode, 0, r.stderr.decode("utf-8", "replace"))
        return json.loads(r.stdout.decode("utf-8"))

    def test_plan_and_transaction_in_process(self):
        sb = self.installed()
        self.run_driver(sb)
        self.assert_rules_on(sb, PLUGIN, self.old)
        user = user_settings(self.old)
        s = self.settings(sb)
        for kind in ("allow", "deny"):
            self.assertEqual([r for r in s["permissions"][kind] if r in user["permissions"][kind]],
                             user["permissions"][kind])
        self.assertTrue(sb.status()["validator"]["ok"])
        first = self.snapshot(sb)
        time.sleep(0.01)
        self.run_driver(sb)
        second = self.snapshot(sb)
        for rel in (".claude/settings.json", ".vmodel/install-record.json"):
            self.assertEqual(second[rel], first[rel], rel)
        code, out = sb.vm("uninstall", "--project", str(sb.root))
        self.assertEqual(code, 0, out)
        self.assertEqual(self.settings(sb), user)


if __name__ == "__main__":
    unittest.main()

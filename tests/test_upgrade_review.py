"""v0.1.5 upgrade: findings of the independent review of the first fix (0e691d0), reproduced before fixing.

docs/v0.1.5/WORKITEM.md section 7. RED target: a plugin copy of commit 0e691d0 (scripts/red_green.py --plugin);
...Red must fail there and pass on the fix, ...Char passes on both. The installed-by-an-older-release setup is the one
of tests/test_upgrade_settings.py.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import unittest

from helpers import PLUGIN, Sandbox
from test_upgrade_settings import Base, cli_allow, core_deny, user_settings

POSIX = sys.platform != "win32"
PROMPT = b"Type 'yes'"


def pty_run(sb: Sandbox, args: list[str], driver) -> tuple[str, int]:
    """Run the CLI on a pseudo terminal; `driver(fd, read_until)` plays the user."""
    import pty
    import select
    pid, fd = pty.fork()
    if pid == 0:
        os.chdir(sb.root)
        os.environ.clear()
        os.environ.update(sb.env)
        os.execv(sys.executable, [sys.executable, "-I", "-B", str(sb.entry), *args])
    buf = bytearray()

    def read_until(pattern: bytes, timeout: float = 60) -> bool:
        end = time.time() + timeout
        while pattern not in buf and time.time() < end:
            ready, _, _ = select.select([fd], [], [], 0.2)
            if ready:
                try:
                    chunk = os.read(fd, 4096)
                except OSError:
                    return False
                if not chunk:
                    return False
                buf.extend(chunk)
        return pattern in buf

    try:
        driver(fd, read_until)
    finally:
        while True:
            try:
                chunk = os.read(fd, 4096)
            except OSError:
                break
            if not chunk:
                break
            buf.extend(chunk)
        _, status = os.waitpid(pid, 0)
    return bytes(buf).decode("utf-8", "replace"), os.waitstatus_to_exitcode(status)


def maybe_answer(text: bytes):
    """Answer the prompt if one comes (the fixed CLI rejects the command before asking)."""
    def driver(fd, read_until):
        if read_until(PROMPT, timeout=20):
            os.write(fd, text)
    return driver


def answer(text: bytes, before=None):
    def driver(fd, read_until):
        assert read_until(PROMPT), "no confirmation prompt"
        if before:
            before()
        os.write(fd, text)
    return driver


@unittest.skipUnless(POSIX, "needs a pty (POSIX only)")
class UpgradeReviewRed(Base):
    def test_ctrl_c_while_waiting_for_the_ledger_rolls_everything_back(self):
        """Finding 1: an interrupt during the re-pin skipped the rollback and left the lock re-pinned without a
        ledger record."""
        sb = self.installed()
        before = self.snapshot(sb)
        held = sb.root / ".vmodel" / "state" / ".ledger.lock"
        held.write_text("held by another process", encoding="utf-8")

        def driver(fd, read_until):
            assert read_until(PROMPT)
            os.write(fd, b"yes\n")
            time.sleep(2.5)
            os.write(fd, b"\x03")  # Ctrl-C while the ledger lock is awaited

        try:
            out, code = pty_run(sb, ["lock", "--accept-current", "--reason", "upgrade"], driver)
        finally:
            held.unlink()
        self.assertNotEqual(code, 0, out)
        self.assertEqual(self.snapshot(sb), before, out)
        self.assertIn("Rolled back", out)

    def test_plan_check_covers_a_project_installed_while_the_prompt_was_open(self):
        """Finding 2: no plan at display time (init only) let a later install's settings change through unseen."""
        sb = Sandbox(plugin=self.old)
        self.sbs.append(sb)
        (sb.root / ".claude").mkdir()
        (sb.root / ".claude" / "settings.json").write_text(json.dumps(user_settings(self.old)), encoding="utf-8")
        sb.init()
        self.use(sb, PLUGIN)
        lock = (sb.root / ".vmodel" / "devkit.lock.json").read_bytes()

        def install_old():
            self.use(sb, self.old)
            code, out = sb.vm("install", "--project", str(sb.root))
            self.use(sb, PLUGIN)
            assert code == 0, out

        out, code = pty_run(sb, ["lock", "--accept-current"], answer(b"yes\n", install_old))
        self.assertNotEqual(code, 0, out)
        self.assertIn("changed after the plan was shown", out)
        self.assertEqual((sb.root / ".vmodel" / "devkit.lock.json").read_bytes(), lock)
        self.assertIn(core_deny(self.old), self.settings(sb)["permissions"]["deny"])

    def test_unreadable_settings_is_reported_not_a_crash(self):
        """Finding 7: an unreadable settings.json ended in 'internal error' with a traceback."""
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            self.skipTest("root ignores file permissions")
        sb = self.installed()
        path = sb.root / ".claude" / "settings.json"
        before = {k: v for k, v in self.snapshot(sb).items() if k != ".claude/settings.json"}
        os.chmod(path, 0)
        try:
            out, code = pty_run(sb, ["lock", "--accept-current"], lambda fd, ru: None)
        finally:
            os.chmod(path, 0o644)
        self.assertNotIn("internal error", out)
        self.assertIn("cannot read", out)
        self.assertEqual(code, 2, out)
        self.assertEqual({k: v for k, v in self.snapshot(sb).items() if k != ".claude/settings.json"}, before)

    def test_install_over_an_older_version_at_the_same_path_points_to_the_upgrade(self):
        """Finding 6: same plugin root, older recorded version (a dev checkout after git pull)."""
        sb = Sandbox()
        self.sbs.append(sb)
        code, out = sb.vm("install", "--project", str(sb.root), "--lint", "none", "--allow-syntax-only")
        self.assertEqual(code, 0, out)
        rec = self.record(sb)
        rec["validator_version"] = "0.1.3"
        (sb.root / ".vmodel" / "install-record.json").write_text(json.dumps(rec), encoding="utf-8")
        before = self.snapshot(sb)
        code, out = sb.vm("install", "--project", str(sb.root), "--lint", "none", "--allow-syntax-only")
        self.assertEqual(code, 2, out)
        self.assertIn("lock --accept-current", out)
        self.assertNotIn("uninstall", out)
        self.assertEqual(self.snapshot(sb), before)

    def test_abbreviated_accept_option_is_rejected(self):
        """Finding 11: argparse accepted '--accept', which the guard's user-only pattern does not match."""
        sb = self.installed()
        before = self.snapshot(sb)
        out, code = pty_run(sb, ["lock", "--accept", "--reason", "x"], maybe_answer(b"yes\n"))
        self.assertNotIn("re-pinned", out)
        self.assertEqual(self.snapshot(sb), before)

    def test_devkit_allow_rules_the_user_removed_stay_removed(self):
        """Finding 5: the upgrade re-granted allow rules the user had deliberately removed."""
        sb = self.installed()
        s = self.settings(sb)
        removed_allow = ["Bash(vmodel *)", *cli_allow(self.old)]
        s["permissions"]["allow"] = [r for r in s["permissions"]["allow"] if r not in removed_allow]
        s["permissions"]["deny"].remove("Edit(/.vmodel/evidence/**)")
        (sb.root / ".claude" / "settings.json").write_text(json.dumps(s, indent=2), encoding="utf-8")
        self.assertIn("re-pinned", self.upgrade(sb))
        s, rec = self.settings(sb), self.record(sb)
        for r in ("Bash(vmodel *)", *cli_allow(PLUGIN)):
            self.assertNotIn(r, s["permissions"]["allow"])
        self.assertIn("Edit(/.vmodel/evidence/**)", s["permissions"]["deny"])  # protection is restored
        self.assertIn(core_deny(PLUGIN), s["permissions"]["deny"])
        self.assertNotIn(core_deny(self.old), s["permissions"]["deny"])
        self.assertFalse([r for r in rec["added_allow"] if r not in s["permissions"]["allow"]])
        code, out = sb.vm("uninstall", "--project", str(sb.root))
        self.assertEqual(code, 0, out)
        self.assertEqual(self.settings(sb), user_settings(self.old))

    def test_upgrade_backups_are_covered_by_a_deny_rule(self):
        """Finding 8: .vmodel/install/backup (the copies the docs tell the user to restore from) was writable."""
        sb = self.installed()
        self.assertIn("re-pinned", self.upgrade(sb))
        self.assertIn("Edit(/.vmodel/install/**)", self.settings(sb)["permissions"]["deny"])
        self.assertIn("Edit(/.vmodel/install/**)", self.record(sb)["added_deny"])

    def test_no_tty_is_refused_before_settings_are_read(self):
        """Finding 9: without a TTY a broken settings.json gave exit 2 instead of the user-only refusal (3)."""
        sb = self.installed()
        (sb.root / ".claude" / "settings.json").write_text("{ broken", encoding="utf-8")
        before = self.snapshot(sb)
        code, out = sb.vm("lock", "--accept-current")
        self.assertEqual(code, 3, out)
        self.assertEqual(self.snapshot(sb), before)

    def test_failure_after_the_ledger_record_is_not_reported_as_rolled_back(self):
        """Finding 4: the anchor write failed after the ledger line was signed; the message said 'Rolled back'."""
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            self.skipTest("root ignores directory permissions")
        sb = self.installed()
        ledger = (sb.root / ".vmodel" / "state" / "ledger.jsonl").read_bytes()
        lock = (sb.root / ".vmodel" / "devkit.lock.json").read_bytes()
        anchors = sb.home / "anchors"
        os.chmod(anchors, 0o555)
        try:
            out, code = pty_run(sb, ["lock", "--accept-current"], answer(b"yes\n"))
        finally:
            os.chmod(anchors, 0o755)
        self.assertNotEqual(code, 0, out)
        self.assertNotIn("Rolled back", out)
        self.assertIn("ledger", out)
        grew = (sb.root / ".vmodel" / "state" / "ledger.jsonl").read_bytes() != ledger
        self.assertTrue(grew)  # the signed lock record is there (the anchor only lags)
        self.assertEqual((sb.root / ".vmodel" / "devkit.lock.json").read_bytes(), lock)
        deny = self.settings(sb)["permissions"]["deny"]
        self.assertIn(core_deny(self.old), deny)  # old + new: no gap whichever core is pinned
        self.assertIn(core_deny(PLUGIN), deny)
        self.assertIn("re-pinned", self.upgrade(sb))  # the next run finishes
        self.assert_rules_on(sb, PLUGIN, self.old)


@unittest.skipUnless(POSIX, "needs a pty (POSIX only)")
class UpgradeReviewChar(Base):
    def test_plan_check_refuses_when_settings_change_while_the_prompt_is_open(self):
        sb = self.installed()
        lock = (sb.root / ".vmodel" / "devkit.lock.json").read_bytes()
        path = sb.root / ".claude" / "settings.json"

        def edit():
            s = json.loads(path.read_text(encoding="utf-8"))
            s["permissions"]["allow"].append("Bash(make test)")
            path.write_text(json.dumps(s), encoding="utf-8")

        out, code = pty_run(sb, ["lock", "--accept-current"], answer(b"yes\n", edit))
        self.assertNotEqual(code, 0, out)
        self.assertIn("changed after the plan was shown", out)
        self.assertEqual((sb.root / ".vmodel" / "devkit.lock.json").read_bytes(), lock)
        self.assertIn("Bash(make test)", self.settings(sb)["permissions"]["allow"])


DRIVER = r"""
import json, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from vmodel_validator import setup_project as sp
from vmodel_validator.project import Project
root, mode = Path(sys.argv[2]), sys.argv[3]
settings = (root / ".claude" / "settings.json").resolve()
if mode == "restore-fails":
    def append(self, record):
        raise OSError("injected ledger failure")
    sp.Ledger.append = append
    real_wb = sp.write_bytes
    def write_bytes(path, data):
        if Path(path).resolve() == settings:
            raise OSError("injected restore failure")
        return real_wb(path, data)
    sp.write_bytes = write_bytes
elif mode == "remove-fails":
    real_wj, n = sp.write_json, [0]
    def write_json(path, obj):
        if Path(path).resolve() == settings:
            n[0] += 1
            if n[0] == 2:
                raise OSError("injected removal failure")
        return real_wj(path, obj)
    sp.write_json = write_json
plan = sp.plan_settings_sync(root)
try:
    res = sp.upgrade_project(Project(root), "in-process", plan)
    out = {"ok": True, "complete": res["complete"], "error": res["error"]}
except sp.SetupError as exc:
    out = {"ok": False, "error": str(exc)}
sys.stdout.write(json.dumps(out))
"""


class InProcess(Base):
    def drive(self, sb: Sandbox, mode: str) -> dict:
        r = subprocess.run([sys.executable, "-I", "-B", "-c", DRIVER, str(PLUGIN / "validator"), str(sb.root), mode],
                           cwd=str(sb.root), env=sb.env, capture_output=True, timeout=300)
        self.assertEqual(r.returncode, 0, r.stderr.decode("utf-8", "replace"))
        return json.loads(r.stdout.decode("utf-8"))

    def devkit_rules_unowned(self, sb: Sandbox) -> list[str]:
        s, rec, user = self.settings(sb), self.record(sb), user_settings(self.old)["permissions"]
        return [r for kind in ("deny", "allow") for r in s["permissions"][kind]
                if r not in user[kind] and r not in rec[f"added_{kind}"]]


class UpgradeReviewInProcessRed(InProcess):
    def test_failed_settings_restore_keeps_devkit_ownership(self):
        """Finding 3: with the settings restore failing, the record went back to the old ownership and the new
        DevKit rules left in settings looked user-owned (uninstall left them behind)."""
        sb = self.installed()
        lock = (sb.root / ".vmodel" / "devkit.lock.json").read_bytes()
        res = self.drive(sb, "restore-fails")
        self.assertFalse(res["ok"], res)
        self.assertIn("injected restore failure", res["error"])
        self.assertEqual((sb.root / ".vmodel" / "devkit.lock.json").read_bytes(), lock)
        self.assertEqual(self.devkit_rules_unowned(sb), [])
        code, out = sb.vm("uninstall", "--project", str(sb.root))
        self.assertEqual(code, 0, out)
        self.assertEqual(self.settings(sb), user_settings(self.old))


class UpgradeReviewInProcessChar(InProcess):
    def test_removal_step_failure_leaves_a_superset_and_a_rerun_finishes(self):
        """AC-U6c: the re-pin is recorded, removing the old rules fails -> old + new rules, then a re-run."""
        sb = self.installed()
        res = self.drive(sb, "remove-fails")
        self.assertTrue(res["ok"], res)
        self.assertFalse(res["complete"], res)
        self.assertIn("again", res["error"])
        deny = self.settings(sb)["permissions"]["deny"]
        self.assertIn(core_deny(self.old), deny)
        self.assertIn(core_deny(PLUGIN), deny)
        self.assertEqual(self.devkit_rules_unowned(sb), [])
        self.assertTrue(sb.status()["validator"]["ok"])
        res = self.drive(sb, "normal")
        self.assertTrue(res["ok"] and res["complete"], res)
        self.assert_rules_on(sb, PLUGIN, self.old)


if __name__ == "__main__":
    unittest.main()

"""v0.1.5 upgrade: findings of the independent re-review of c57f7c5, reproduced before fixing.

docs/v0.1.5/WORKITEM.md section 7. RED target: a plugin copy of commit c57f7c5; ...Red fails there and passes on the
fix, ...Char passes on both.
"""
from __future__ import annotations

import json
import subprocess
import sys
import unittest

from helpers import PLUGIN, Sandbox
from test_upgrade_review import POSIX, pty_run
from test_upgrade_settings import Base, cli_allow, core_deny

DRIVER = r"""
import json, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from vmodel_validator import setup_project as sp
from vmodel_validator.project import Project
root = Path(sys.argv[2])
real_append = sp.Ledger.append
def append(self, record):
    if record.get("type") == "lock":  # another process appends first, then our own append fails
        real_append(self, {"type": "concurrent-test-record", "at": "2026-11-09T00:00:00Z"})
        raise OSError("injected ledger failure")
    return real_append(self, record)
sp.Ledger.append = append
plan = sp.plan_settings_sync(root)
try:
    sp.upgrade_project(Project(root), "in-process", plan)
    out = {"ok": True}
except sp.SetupError as exc:
    out = {"ok": False, "error": str(exc)}
sys.stdout.write(json.dumps(out))
"""


def strip_allow(sb: Sandbox, old) -> None:
    """Make the project look like a 0.1.0/0.1.1 install: no CLI allow rules and no added_allow in the record."""
    path = sb.root / ".claude" / "settings.json"
    s = json.loads(path.read_text(encoding="utf-8"))
    s["permissions"]["allow"] = [r for r in s["permissions"]["allow"] if r not in ("Bash(vmodel *)", *cli_allow(old))]
    path.write_text(json.dumps(s, indent=2), encoding="utf-8")
    rp = sb.root / ".vmodel" / "install-record.json"
    rec = json.loads(rp.read_text(encoding="utf-8"))
    rec.pop("added_allow")
    rp.write_text(json.dumps(rec, indent=2), encoding="utf-8")


@unittest.skipUnless(POSIX, "needs a pty (POSIX only)")
class UpgradeReview2Red(Base):
    def test_install_that_never_had_allow_rules_gets_them(self):
        """Re-review: a pre-0.1.2 record (no added_allow, no CLI allow rules) was read as 'the user removed them'."""
        sb = self.installed()
        strip_allow(sb, self.old)
        out = self.upgrade(sb)
        self.assertIn("re-pinned", out)
        self.assertNotIn("you removed", out)
        allow, rec = self.settings(sb)["permissions"]["allow"], self.record(sb)
        for r in ("Bash(vmodel *)", *cli_allow(PLUGIN)):
            self.assertIn(r, allow)
            self.assertIn(r, rec["added_allow"])


@unittest.skipUnless(POSIX, "needs a pty (POSIX only)")
class UpgradeReview2Char(Base):
    def test_removing_one_previous_allow_rule_withholds_only_its_counterpart(self):
        sb = self.installed()
        path = sb.root / ".claude" / "settings.json"
        s = self.settings(sb)
        s["permissions"]["allow"].remove(cli_allow(self.old)[1])  # the quoted form only
        path.write_text(json.dumps(s, indent=2), encoding="utf-8")
        self.assertIn("re-pinned", self.upgrade(sb))
        allow = self.settings(sb)["permissions"]["allow"]
        self.assertIn(cli_allow(PLUGIN)[0], allow)
        self.assertNotIn(cli_allow(PLUGIN)[1], allow)
        self.assertIn("Bash(vmodel *)", allow)
        first = path.read_bytes()
        self.upgrade(sb)
        self.assertEqual(path.read_bytes(), first)

    def test_interrupt_message_names_the_step(self):
        sb = self.installed()
        held = sb.root / ".vmodel" / "state" / ".ledger.lock"
        held.write_text("held", encoding="utf-8")
        import os
        import time

        def driver(fd, read_until):
            assert read_until(b"Type 'yes'")
            os.write(fd, b"yes\n")
            time.sleep(2.5)
            os.write(fd, b"\x03")

        try:
            out, code = pty_run(sb, ["lock", "--accept-current"], driver)
        finally:
            held.unlink()
        self.assertIn("re-pin step", out)
        self.assertIn("Rolled back", out)
        self.assertIn(core_deny(self.old), self.settings(sb)["permissions"]["deny"])
        self.assertNotIn(core_deny(PLUGIN), self.settings(sb)["permissions"]["deny"])

    def test_abbreviated_option_is_an_argument_error(self):
        sb = self.installed()
        out, code = pty_run(sb, ["lock", "--accept", "--reason", "x"], lambda fd, ru: None)
        self.assertEqual(code, 2, out)
        self.assertIn("unrecognized arguments", out)


class UpgradeReview2InProcessRed(Base):
    def test_a_concurrent_ledger_record_is_not_mistaken_for_our_re_pin(self):
        """Re-review nit: 'did the ledger grow' counted entries, so another process's record looked like ours."""
        sb = self.installed()
        before = self.snapshot(sb)
        r = subprocess.run([sys.executable, "-I", "-B", "-c", DRIVER, str(PLUGIN / "validator"), str(sb.root)],
                           cwd=str(sb.root), env=sb.env, capture_output=True, timeout=300)
        self.assertEqual(r.returncode, 0, r.stderr.decode("utf-8", "replace"))
        res = json.loads(r.stdout.decode("utf-8"))
        self.assertFalse(res["ok"], res)
        self.assertIn("Rolled back", res["error"])
        after = self.snapshot(sb)
        for rel in (".claude/settings.json", ".vmodel/install-record.json", ".vmodel/devkit.lock.json"):
            self.assertEqual(after[rel], before[rel], rel)


if __name__ == "__main__":
    unittest.main()

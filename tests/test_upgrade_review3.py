"""v0.1.5 upgrade: findings of the third review pass on be372f4 (declined_allow), reproduced before fixing.

docs/v0.1.5/WORKITEM.md section 7. RED target: a plugin copy of commit be372f4; ...Red fails there and passes on the
fix, ...Char passes on both. A third release path is a copy of the plugin under test (same core, other directory).
"""
from __future__ import annotations

import json
import shutil
import unittest

from helpers import PLUGIN, Sandbox
from test_upgrade_review import POSIX
from test_upgrade_settings import Base, cli_allow, user_settings


class ThreeReleases(Base):
    """A = old release, B = plugin under test, C = a copy of B at another path."""

    def setUp(self):
        super().setUp()
        self.c = None

    def release_c(self, sb: Sandbox):
        if self.c is None:
            self.c = sb.tmp / "release C" / "vmodel"
            shutil.copytree(PLUGIN, self.c, ignore=shutil.ignore_patterns("__pycache__"))
        return self.c

    def declined_on_b(self) -> Sandbox:
        """Install with A, the user deletes A's unquoted CLI rule, upgrade to B (B's counterpart is withheld)."""
        sb = self.installed()
        path = sb.root / ".claude" / "settings.json"
        s = self.settings(sb)
        s["permissions"]["allow"].remove(cli_allow(self.old)[0])
        path.write_text(json.dumps(s, indent=2), encoding="utf-8")
        self.assertIn("re-pinned", self.upgrade(sb))
        self.assertNotIn(cli_allow(PLUGIN)[0], self.settings(sb)["permissions"]["allow"])
        self.assertEqual(self.record(sb).get("declined_allow"), [cli_allow(PLUGIN)[0]])
        return sb


@unittest.skipUnless(POSIX, "needs a pty (POSIX only)")
class UpgradeReview3Red(ThreeReleases):
    def test_a_declined_rule_the_user_added_back_is_not_withheld_on_the_next_release(self):
        """Third pass, problem 1: a stale declined_allow withheld C's rule although the user had re-added B's."""
        sb = self.declined_on_b()
        path = sb.root / ".claude" / "settings.json"
        s = self.settings(sb)
        s["permissions"]["allow"].append(cli_allow(PLUGIN)[0])  # the user grants it again by hand
        path.write_text(json.dumps(s, indent=2), encoding="utf-8")
        c = self.release_c(sb)
        self.use(sb, c)
        out = self.upgrade(sb)
        self.assertIn("re-pinned", out)
        self.assertNotIn("you removed", out)
        self.assertIn(cli_allow(c)[0], self.settings(sb)["permissions"]["allow"])
        self.assertNotIn("declined_allow", self.record(sb))

    def test_same_release_re_pin_after_a_decline_shows_no_change_block(self):
        """Third pass, problem 2: nothing changes, but the plan block and 'update the rules' prompt were shown."""
        sb = self.declined_on_b()
        before = {k: v for k, v in self.snapshot(sb).items() if k.startswith(".claude") or "install" in k}
        out = self.upgrade(sb)
        self.assertIn("re-pinned", out)
        self.assertNotIn("will follow this release", out)
        self.assertNotIn("update the DevKit permission rules", out)
        self.assertEqual({k: v for k, v in self.snapshot(sb).items() if k in before}, before)


@unittest.skipUnless(POSIX, "needs a pty (POSIX only)")
class UpgradeReview3Char(ThreeReleases):
    def test_a_decline_carries_over_two_release_changes_and_uninstall_restores(self):
        sb = self.declined_on_b()
        c = self.release_c(sb)
        self.use(sb, c)
        self.assertIn("re-pinned", self.upgrade(sb))
        allow = self.settings(sb)["permissions"]["allow"]
        self.assertNotIn(cli_allow(c)[0], allow)
        self.assertIn(cli_allow(c)[1], allow)
        self.assertEqual(self.record(sb).get("declined_allow"), [cli_allow(c)[0]])
        for p in (PLUGIN,):
            for r in cli_allow(p):
                self.assertNotIn(r, allow)
        code, out = sb.vm("uninstall", "--project", str(sb.root))
        self.assertEqual(code, 0, out)
        self.assertEqual(self.settings(sb), user_settings(self.old))


if __name__ == "__main__":
    unittest.main()

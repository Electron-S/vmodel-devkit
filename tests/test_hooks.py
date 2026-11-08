"""Guard / SessionStart hook decisions, driven through the real CLI with JSON on stdin."""
from __future__ import annotations

import json
import unittest

from helpers import PLUGIN, Sandbox


class GuardHook(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sb = Sandbox()
        cls.sb.init()
        cls.sb.new_wi()
        cls.root = cls.sb.root

    @classmethod
    def tearDownClass(cls):
        cls.sb.cleanup()

    def decide(self, tool: str, tool_input: dict, agent_type: str | None = None, cwd=None) -> str | None:
        payload = {"session_id": "s", "hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": tool_input,
                   "cwd": str(cwd or self.root)}
        if agent_type:
            payload["agent_type"] = agent_type
        code, out = self.sb.hook("guard", payload)
        self.assertEqual(code, 0, out)
        if not out.strip():
            return None
        d = json.loads(out)["hookSpecificOutput"]
        self.assertEqual(d["permissionDecision"], "deny")
        return d["permissionDecisionReason"]

    def test_protected_writes_denied(self):
        for rel in (".vmodel/state/ledger.jsonl", ".vmodel/evidence/WI-001/x.json", ".vmodel/config.json",
                    ".vmodel/devkit.lock.json"):
            self.assertIsNotNone(self.decide("Write", {"file_path": str(self.root / rel), "content": "{}"}), rel)
            self.assertIsNotNone(self.decide("Edit", {"file_path": rel, "old_string": "a", "new_string": "b"}), rel)

    def test_validator_core_write_denied(self):
        target = PLUGIN / "validator" / "vmodel_validator" / "gates.py"
        self.assertIn("Validator Core", self.decide("Edit", {"file_path": str(target)}))

    def test_keys_read_denied(self):
        key = self.sb.home / "keys" / "x.key"
        self.assertIn("signing keys", self.decide("Read", {"file_path": str(key)}))

    def test_normal_source_write_allowed(self):
        self.assertIsNone(self.decide("Write", {"file_path": str(self.root / "src/textstats/x.py")}))
        self.assertIsNone(self.decide("Write", {"file_path": str(self.root / ".vmodel/work-items/WI-001/design.json")}))

    def test_reviews_only_by_verifier(self):
        review = str(self.root / ".vmodel/work-items/WI-001/reviews/G1.json")
        self.assertIn("vmodel:verifier", self.decide("Write", {"file_path": review}))
        self.assertIn("vmodel:verifier", self.decide("Write", {"file_path": review}, agent_type="general-purpose"))
        self.assertIsNone(self.decide("Write", {"file_path": review}, agent_type="vmodel:verifier"))

    def test_verifier_is_read_only_elsewhere(self):
        self.assertIn("read-only", self.decide("Edit", {"file_path": str(self.root / "src/textstats/__init__.py")},
                                               agent_type="vmodel:verifier"))
        self.assertIsNotNone(self.decide("Bash", {"command": "rm -rf src"}, agent_type="vmodel:verifier"))
        self.assertIsNone(self.decide("Bash", {"command": "git diff --stat"}, agent_type="vmodel:verifier"))

    def test_bash_touching_protected_data(self):
        for cmd in ("echo '{}' > .vmodel/state/ledger.jsonl",
                    "python3 -c \"open('.vmodel/evidence/x','w')\"",
                    "cat ~/.vmodel-devkit/keys/abc.key",
                    "sed -i s/FAILED/PASSED/ .vmodel/state/ledger.jsonl",
                    "cp fake.json .vmodel\\evidence\\x.json"):
            self.assertIsNotNone(self.decide("Bash", {"command": cmd}), cmd)

    def test_bash_validator_calls_allowed(self):
        vm = str(PLUGIN / "bin" / "vmodel")
        for cmd in (f'"{vm}" gate WI-001 G1', f'"{vm}" status 2>&1 | tail -40',
                    f'"{vm}" verify-evidence .vmodel/evidence/WI-001/G5/x/record.json', "ls -la", "python3 -m pytest -q"):
            self.assertIsNone(self.decide("Bash", {"command": cmd}), cmd)

    def test_bash_chained_with_protected_data_denied(self):
        vm = str(PLUGIN / "bin" / "vmodel")
        self.assertIsNotNone(self.decide("Bash", {"command": f'"{vm}" status; rm .vmodel/state/head.json'}))

    def test_bash_core_modification_denied(self):
        core = PLUGIN / "validator" / "vmodel_validator" / "gates.py"
        self.assertIsNotNone(self.decide("Bash", {"command": f"sed -i 's/a/b/' '{core}'"}))
        self.assertIsNone(self.decide("Bash", {"command": f"cat '{core}'"}))

    def test_user_only_actions_denied(self):
        self.assertIn("user-only", self.decide("Bash", {"command": "vmodel unblock WI-001 G5 --reason x"}))
        self.assertIn("user-only", self.decide("Bash", {"command": "vmodel lock --accept-current"}))

    def test_outside_vmodel_project_allowed(self):
        self.assertIsNone(self.decide("Write", {"file_path": str(self.sb.tmp / "elsewhere.txt")}, cwd=self.sb.tmp))

    def test_invalid_json_is_denied(self):
        import subprocess
        import sys
        r = subprocess.run([sys.executable, str(self.sb.entry), "hook", "guard"], input=b"not json",
                           capture_output=True, cwd=self.root, env=self.sb.env)
        self.assertEqual(r.returncode, 0)
        self.assertIn(b'"deny"', r.stdout)

    def test_guide_prints_plugin_docs_without_reading_outside_files(self):
        code, out = self.sb.vm("guide", "artifacts")
        self.assertEqual(code, 0, out)
        self.assertIn("requirements.json (P1)", out)
        code, out = self.sb.vm("guide", "tests")
        self.assertEqual(code, 0, out)
        self.assertNotIn("name: test-designer", out)  # frontmatter stripped

    def test_session_start_restores_context(self):
        code, out = self.sb.hook("session-start", {"hook_event_name": "SessionStart", "cwd": str(self.root),
                                                   "source": "startup"})
        self.assertEqual(code, 0, out)
        self.assertIn("VModel DevKit active", out)
        self.assertIn("WI-001", out)
        self.assertIn("/vmodel:start", out)
        code, out = self.sb.hook("session-start", {"cwd": str(self.sb.tmp)})
        self.assertEqual((code, out.strip()), (0, ""))



class GuardWithSpacedPluginPath(unittest.TestCase):
    """Regression (found on Windows): quoted CLI paths containing spaces must be recognised."""

    def test_validator_call_with_spaces_in_plugin_path(self):
        from helpers import copy_plugin
        sb = Sandbox()
        try:
            sb.plugin = copy_plugin(sb.tmp)  # ".../plugin copy" contains a space
            sb.entry = sb.plugin / "validator" / "vmodel.py"
            sb.init()
            vm = str(sb.plugin / "bin" / "vmodel")
            for cmd in (f'"{vm}" status 2>&1 | tail -40', f'"{vm}" gate WI-001 G1',
                        f'"{vm}" verify-evidence .vmodel/evidence/a/record.json'):
                code, out = sb.hook("guard", {"tool_name": "Bash", "tool_input": {"command": cmd},
                                              "cwd": str(sb.root)})
                self.assertEqual((code, out.strip()), (0, ""), cmd)
            code, out = sb.hook("guard", {"tool_name": "Bash", "cwd": str(sb.root), "tool_input": {
                "command": f'echo x > "{sb.plugin / "validator" / "vmodel.py"}"'}})
            self.assertIn("deny", out)
        finally:
            sb.cleanup()


if __name__ == "__main__":
    unittest.main()

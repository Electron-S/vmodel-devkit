"""v0.1.4 F2: guard false positives on /dev/null redirections, without weakening write detection (D34, D36).

Class suffixes (scripts/red_green.py): ...Red must FAIL on the 0.1.3 core and pass after the fix; ...Char must pass on
both (current behaviour that the fix must keep).
bash facts behind the cases (measured 2026-11-08): `&> f`, `&>> f`, `>& f`, `>&f`, `1>&f` create f; `2>&f` is an
"ambiguous redirect"; `2>/dev/null"x"`, `` 2>/dev/null`printf y` `` and `>/dev/null#c` target other paths than /dev/null.
"""
from __future__ import annotations

import json
import unittest

from helpers import PLUGIN, Sandbox

VERIFIER = "vmodel:verifier"


class _Guard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sb = Sandbox()
        cls.sb.init()
        cls.sb.new_wi()

    @classmethod
    def tearDownClass(cls):
        cls.sb.cleanup()

    def decide(self, cmd: str, agent_type: str | None = None, tool: str = "Bash") -> str | None:
        payload = {"session_id": "s", "hook_event_name": "PreToolUse", "tool_name": tool,
                   "tool_input": {"command": cmd}, "cwd": str(self.sb.root)}
        if agent_type:
            payload["agent_type"] = agent_type
        code, out = self.sb.hook("guard", payload)
        self.assertEqual(code, 0, out)
        if not out.strip():
            return None
        d = json.loads(out)["hookSpecificOutput"]
        self.assertEqual(d["permissionDecision"], "deny")
        return d["permissionDecisionReason"]

    def assert_allowed(self, cmds, agent_type=None):
        denied = {c: self.decide(c, agent_type) for c in cmds}
        self.assertEqual({c: r for c, r in denied.items() if r is not None}, {}, "should be allowed")

    def assert_denied(self, cmds, agent_type=None):
        allowed = [c for c in cmds if self.decide(c, agent_type) is None]
        self.assertEqual(allowed, [], "should be denied")


class GuardDevNullRed(_Guard):
    """Read-only commands whose only redirection discards output to /dev/null (denied by 0.1.3)."""

    def test_main_session_reads_with_output_discarded(self):
        self.assert_allowed([
            "cat .vmodel/work-items/WI-001/defects.json 2>/dev/null",
            "cat .vmodel/work-items/WI-001/requirements.json 2> /dev/null",
            "ls .vmodel/work-items >/dev/null 2>&1 && echo ok",
            "ls .vmodel &>/dev/null",
            "ls .vmodel &>> /dev/null",
            "cat .vmodel/work-items/WI-001/workitem.json >>/dev/null",
            "grep -c TEST .vmodel/work-items/WI-001/workitem.json 1>/dev/null",
            "ls .vmodel >& /dev/null",
            "test -d .vmodel/work-items 2>/dev/null; echo $?",
            "cat .vmodel/work-items/WI-001/workitem.json 2>\t/dev/null",
            "cat .vmodel/work-items/WI-001/workitem.json 2>>/dev/null",
            "(cat .vmodel/work-items/WI-001/workitem.json 2>/dev/null)",
            "echo $(cat .vmodel/work-items/WI-001/workitem.json 2>/dev/null)",
        ])

    def test_verifier_reads_with_output_discarded(self):
        self.assert_allowed([
            "cat src/textstats/wordfreq.py 2>/dev/null",
            "grep -rn TEST_ tests 2>/dev/null | head -20",
            "ls src >/dev/null 2>&1 && echo ok",
            "cat .vmodel/work-items/WI-001/workitem.json 2>/dev/null",
        ], agent_type=VERIFIER)


class GuardFileRedirectRed(_Guard):
    """'&>', '>&word' and 'N>&word' write files in bash, but the 0.1.3 guard did not see a write."""

    def test_ampersand_redirects_into_protected_paths_denied(self):
        self.assert_denied([
            "echo x &> .vmodel/state/ledger.jsonl",
            "echo x >& .vmodel/state/ledger.jsonl",
            "echo x >&.vmodel/evidence/WI-001/a.txt",
            "echo x 1>&.vmodel/state/head.json",
            "echo x&&>.vmodel/state/ledger.jsonl",
            "echo x2>&.vmodel/state/x",
        ])

    def test_redirection_between_verb_and_flag_denied(self):
        """A non-writing redirection between a write verb and its flag hid the write from 0.1.3 (review finding)."""
        self.assert_denied([
            "sed 2>&1 -i s/a/b/ .vmodel/state/ledger.jsonl",
            "git 2>&1 checkout -- .vmodel/state",
            "python3 2>&1 -c \"open('.vmodel/state/x','w')\"",
            "find .vmodel/state 2>&1 -delete",
            "find . 2>&1 -delete",
        ])
        self.assert_denied(["sed <list.txt -i s/a/b/ src/textstats/wordfreq.py", "git 2>&- checkout -- src",
                            "find src 2>&1 -delete"], agent_type=VERIFIER)

    def test_verifier_ampersand_redirects_to_files_denied(self):
        self.assert_denied([
            "cat src/textstats/wordfreq.py &> notes.txt",
            "cat src/textstats/wordfreq.py >& notes.txt",
            "cat src/textstats/wordfreq.py >&notes.txt",
            "cat src/textstats/wordfreq.py2>&notes.txt",
        ], agent_type=VERIFIER)


class GuardWritesChar(_Guard):
    """Writes stay denied when a /dev/null redirection is added; fd duplication stays allowed (0.1.3 behaviour)."""

    def test_writes_into_protected_paths_stay_denied(self):
        self.assert_denied([
            "echo x > .vmodel/state/ledger.jsonl",
            "echo x 2> .vmodel/evidence/a.txt",
            "echo x &>> .vmodel/state/ledger.jsonl",
            "cat a >/dev/null > .vmodel/state/x",
            "cat a 2>/dev/null >> .vmodel/evidence/x",
            "cat a >/dev/null; echo y > .vmodel/state/x",
            "cat a >/dev/null && echo y > .vmodel/state/x",
            "cat a >/dev/null | tee .vmodel/state/x",
            "echo y >/dev/nullx .vmodel/state/x",
            "echo y >/dev/null/../x .vmodel/state",
            'echo y 2>/dev/null"x" .vmodel/state',
            "echo y 2>/dev/null`printf x` .vmodel/state",
            "echo y >/dev/null#c .vmodel/state",
            'echo y > "/dev/null" > .vmodel/state/x',
            "echo y >| .vmodel/state/x",
            "tee .vmodel/state/x >/dev/null",
            "cp a .vmodel/state/x 2>/dev/null",
            "rm .vmodel/state/head.json 2>/dev/null",
            "sed -i s/a/b/ .vmodel/state/ledger.jsonl 2>/dev/null",
            "python3 -c \"open('.vmodel/evidence/x','w')\" 2>/dev/null",
            "cat > .vmodel/work-items/WI-001/reviews/G1.json 2>/dev/null <<'EOF'\n{}\nEOF",
        ])

    def test_devnull_between_verb_and_flag_stays_denied(self):
        """0.1.3 denied these only because '>/dev/null' counted as a write; removing it must not expose the verb."""
        self.assert_denied([
            "find .vmodel/state >/dev/null 2>&1 -delete",
            "sed >/dev/null 2>&1 -i s/a/b/ .vmodel/state/ledger.jsonl",
            "git >/dev/null 2>&1 checkout -- .vmodel/state",
            "python3 >/dev/null 2>&1 -c \"open('.vmodel/state/x','w')\"",
            "find . >/dev/null -delete",
        ])
        self.assert_denied(["find src >/dev/null 2>&1 -delete", "git >/dev/null 2>&1 checkout -- src",
                            "sed 2>/dev/null -i s/a/b/ src/textstats/wordfreq.py"], agent_type=VERIFIER)

    def test_non_bash_tools_keep_the_old_rule(self):
        """PowerShell resolves /dev/null to a real path (C:\\dev\\null); $null and NUL are out of scope (REQ-F2-5)."""
        for cmd in ("Get-Content src/textstats/wordfreq.py 2>/dev/null", "Get-Content src/textstats/wordfreq.py 2>$null",
                    "Get-Content src/textstats/wordfreq.py *>/dev/null"):
            self.assertIsNotNone(self.decide(cmd, VERIFIER, tool="PowerShell"), cmd)
        for cmd in ("Get-Content .vmodel/state/ledger.jsonl 2>$null", "type .vmodel\\state\\ledger.jsonl 2>NUL"):
            self.assertIsNotNone(self.decide(cmd, tool="PowerShell"), cmd)
        self.assert_denied(["cat src/textstats/wordfreq.py 2>$null", "cat src/textstats/wordfreq.py 2>NUL",
                            "cat src/textstats/wordfreq.py >/dev/null\r"], agent_type=VERIFIER)

    def test_verifier_writes_stay_denied(self):
        self.assert_denied([
            "sed -i s/a/b/ src/textstats/wordfreq.py 2>/dev/null",
            "rm src/textstats/wordfreq.py 2>/dev/null",
            "echo x > src/textstats/wordfreq.py 2>/dev/null",
            "cat src/textstats/wordfreq.py 2>/dev/null > notes.txt",
            "echo x >/dev/nullx",
            "cp src/a src/b >/dev/null 2>&1",
            "git checkout -- src >/dev/null 2>&1",
        ], agent_type=VERIFIER)

    def test_other_rules_ignore_devnull_suffix(self):
        vm = str(PLUGIN / "bin" / "vmodel")
        core = PLUGIN / "validator" / "vmodel_validator" / "gates.py"
        self.assert_denied([
            "cat ~/.vmodel-devkit/keys/a.key 2>/dev/null",
            "rm -rf . 2>/dev/null",
            "git clean -fdx >/dev/null 2>&1",
            f'"{vm}" unblock WI-001 G5 --reason x 2>/dev/null',
            f'"{vm}" review-submit WI-001 G1 2>/dev/null',
            f"sed -i s/a/b/ '{core}' 2>/dev/null",
        ])

    def test_fd_duplication_is_not_a_write(self):
        self.assert_allowed([
            "cat src/textstats/wordfreq.py 2>&1 | head",
            "echo note >&2",
            "cat src/textstats/wordfreq.py 2>&-",
            "ls src 1>&2",
            "echo note >& 2",
            "sh -c 'ls src 2>&1'",
            "echo `ls src 2>&1`",
            "bash -c \"cat src/textstats/wordfreq.py 2>&1\" | head",
            "wc -l < src/textstats/wordfreq.py",
        ], agent_type=VERIFIER)


_PROBE = r"""
import json, sys
sys.path.insert(0, sys.argv[1])
from vmodel_validator import hook
cmds = json.loads(sys.stdin.read())
f = getattr(hook, "shell_writes", None) or (lambda c: bool(hook.WRITE_VERBS.search(c)))
print(json.dumps([bool(f(c)) for c in cmds]))
"""


class GuardDifferentialAccept(unittest.TestCase):
    """Generated corpus, 0.1.3 release vs this core: nothing that 0.1.3 treated as a write stops being one, unless every
    redirection in it targets exactly /dev/null (REQ-F2-3, REQ-F2-4). Needs the 0.1.3 release (dist/ or the git tag)."""

    def writes(self, plugin, cmds):
        import subprocess
        import sys
        r = subprocess.run([sys.executable, "-I", "-B", "-c", _PROBE, str(plugin / "validator")],
                           input=json.dumps(cmds).encode("utf-8"), capture_output=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stderr.decode("utf-8", "replace"))
        return json.loads(r.stdout)

    def test_no_write_detection_is_lost_except_pure_devnull_redirections(self):
        import itertools
        import re
        from helpers import old_release
        old = old_release("0.1.3")
        if old is None:
            self.skipTest("0.1.3 release not available (no dist/vmodel-0.1.3 and no git tag v0.1.3)")
        ops = [">", ">>", "1>", "2>", "2>>", "&>", "&>>", ">&", "1>&", "2>&", ">|", "<>", "3>"]
        targets = ["/dev/null", "/dev/nullx", "/dev/null/../x", '"/dev/null"', "'/dev/null'", '/dev/null"x"',
                   "/dev/null`x`", "/dev/null$X", "/dev/null#c", "/dev/null{,x}", "/dev/null\\x", "/DEV/NULL",
                   "//dev/null", "/dev//null", ".vmodel/x", "1", "2", "-", "2x", "f"]
        tails = ["", " ", ";", " ;rm x", "&", " && echo y > .vmodel/x", "|", " | tee q", ")", ">x", "<y", " 2>&1",
                 "\r"]
        cmds = [f"cat a {op}{sp}{t}{tail}" for op, sp, t, tail in itertools.product(ops, ["", " ", "\t"], targets, tails)]
        # write verbs whose flag follows the verb: no redirection placed in between may hide them
        between = ["", ">/dev/null", "2>/dev/null", "&>/dev/null", "2>&1", ">&2", "2>&-", "<f", "1>&2"]
        verbs = [("sed", "-i s/a/b/ x"), ("git", "checkout -- x"), ("python3", "-c 'open(1)'"), ("find x", "-delete")]
        writing = [f"{v} {r1} {r2} {flag}" for (v, flag), r1, r2 in itertools.product(verbs, between, between)]
        before = self.writes(old, cmds + writing)
        after = self.writes(PLUGIN, cmds + writing)
        lost = [c for c, b, a in zip(cmds, before, after) if b and not a]
        pure = re.compile(r"cat a <?(?:&>>?|>&|[0-9]*>>?)[ \t]*/dev/null(?:| |;|&|\||\)| 2>&1)")
        self.assertEqual([c for c in lost if not pure.fullmatch(c)], [])
        self.assertTrue(lost)  # the fix does allow the /dev/null forms
        self.assertEqual([c for c, a in zip(writing, after[len(cmds):]) if not a], [])  # every verb form is a write
        gained = [c for c, b, a in zip(cmds, before, after) if a and not b]
        self.assertIn("cat a &> .vmodel/x", gained)
        self.assertIn("cat a >&.vmodel/x", gained)


if __name__ == "__main__":
    unittest.main()

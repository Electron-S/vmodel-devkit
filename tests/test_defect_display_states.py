"""v0.1.4 (2nd pass, 2026-11-09): defect display states OPEN / FIX_APPLIED / REVERIFY_REQUIRED / VERIFICATION_FAILED /
CLOSED / UNKNOWN (DECISIONS D37).

The first 0.1.4 build showed "VERIFIED" whenever a past `verified_by` existed but its gate was no longer PASSED, which
still reads as "done" while the gate is STALE or has FAILED again. The state is derived from the signed ledger and the
current gate state only; defects.json keeps `open` / `fixed`, `verified_by` keeps the past PASS (history), and gate
decisions, ledger records and manifests do not change.

RED target: the first 0.1.4 build (core b1fee43f..., kept outside the repo before the change). Class suffixes follow
scripts/red_green.py (...Red fails on that build, ...Char / ...Invariant pass on both).
"""
from __future__ import annotations

import os
import unittest

from helpers import PLUGIN, Sandbox, copy_plugin, fail_g5, has_pytest
from rework_case import FailedG5Case

V013_DEFECT_KEYS = {"id", "gate", "claimed_status", "root_cause_phase", "found_in_records", "unknown_records",
                    "failing_tests_by_record", "failing_tests", "unlinked_failing_tests", "verified_by"}
V014_DEFECT_KEYS = {"citations", "unknown_tests", "closure_gate", "verification_withheld", "errors", "warnings",
                    "closure_state", "closure_gate_status", "closure_gate_record", "claim_note"}
ALL_STATES = {"OPEN", "FIX_APPLIED", "REVERIFY_REQUIRED", "VERIFICATION_FAILED", "CLOSED", "UNKNOWN"}


class DisplayStateRed(FailedG5Case):
    def assert_state(self, expected: str) -> dict:
        d = self.defect()
        self.assertEqual(d.get("closure_state"), expected, d)
        self.assertTrue(self.defect_line().startswith(f"DEFECT-001 {expected} "), self.defect_line())
        return d

    def assert_not_done(self, line: str) -> None:
        """A non-closed defect never shows a 'done' state word (VERIFIED / CLOSED) in its status line."""
        state_and_bracket = line.split("]", 1)[0]
        self.assertNotIn(" VERIFIED ", f" {state_and_bracket} ")
        self.assertNotIn("CLOSED", state_and_bracket)

    def bug(self) -> None:
        self.s["wf"].write_text(self.s["good"].replace("if n <= 0:", "if n < 0:"), encoding="utf-8")

    def test_stale_gate_after_closure_is_reverify_required(self):
        """drill-3 P-F1: G4/G5 STALE after the closure -> REVERIFY_REQUIRED, never VERIFIED or CLOSED."""
        res = self.close_defect()
        wf = self.s["wf"]
        wf.write_bytes(wf.read_bytes() + b"\n")
        self.assertEqual((self.gates()["G4"], self.gates()["G5"]), ("STALE", "STALE"))
        d = self.assert_state("REVERIFY_REQUIRED")
        self.assertEqual((d.get("closure_gate_status"), d["verified_by"]), ("STALE", res["record_id"]))
        self.assertEqual(d.get("verification_history"), [res["record_id"]])  # past success kept separately
        line = self.defect_line()
        self.assert_not_done(line)
        self.assertIn(f"previously passed in {res['record_id']}", line)
        self.assertIn("G5 is now STALE", line)
        self.assertIn("re-verify", line)

    def test_upstream_change_after_closure_is_reverify_required(self):
        self.close_defect()
        tests = self.sb.load("tests.json")
        tests["tests"][0]["title"] += " (edited)"
        self.sb.save("tests.json", tests)
        self.assertEqual((self.gates()["G3"], self.gates()["G5"]), ("STALE", "STALE"))
        d = self.assert_state("REVERIFY_REQUIRED")
        self.assertEqual(d.get("closure_gate_status"), "STALE")

    def test_failure_after_the_closure_is_verification_failed(self):
        res = self.close_defect()
        self.bug()
        self.gate_g4()
        again = self.sb.gate("G5")[1]
        self.assertEqual(again["status"], "FAILED")
        d = self.assert_state("VERIFICATION_FAILED")
        self.assertEqual((d.get("closure_gate_status"), d.get("closure_gate_record"), d["verified_by"]),
                         ("FAILED", again["record_id"], res["record_id"]))
        self.assertEqual(d.get("verification_history"), [res["record_id"]])
        self.assertEqual((d.get("last_verification") or {}).get("record"), again["record_id"])
        self.assertEqual((d.get("last_verification") or {}).get("status"), "FAILED")
        line = self.defect_line()
        self.assert_not_done(line)
        self.assertIn(again["record_id"], line)
        self.assertIn(f"previously passed in {res['record_id']}", line)

    def test_failed_fix_attempt_is_verification_failed_until_a_pass(self):
        """Claimed fixed, re-evaluated, FAILED again: not FIX_APPLIED (that reads as 'awaiting verification')."""
        self.sb.add_defect(self.failed, "G5", related=["REQ-002", *self.failing], status="fixed")
        self.gate_g4()  # the claimed fix did not change the bug
        second = self.sb.gate("G5")[1]
        self.assertEqual(second["status"], "FAILED")
        d = self.assert_state("VERIFICATION_FAILED")
        self.assertEqual((d["verified_by"], d.get("verification_history"), d.get("closure_gate_record")),
                         (None, [], second["record_id"]))
        # the rework loop cites the new failure in the same DEFECT: still not verified
        self.sb.add_defect(second["record_id"], "G5")
        self.assert_state("VERIFICATION_FAILED")
        self.s["wf"].write_text(self.s["good"], encoding="utf-8")
        self.gate_g4()
        self.assertEqual(self.gates()["G5"], "FAILED")  # re-reviewed, not re-verified yet
        self.assert_state("VERIFICATION_FAILED")
        passed = self.sb.gate("G5")[1]
        self.assertEqual(passed["status"], "PASSED")
        d = self.assert_state("CLOSED")
        self.assertEqual(d["verified_by"], passed["record_id"])

    def test_three_identical_failures_after_the_fix_is_verification_failed(self):
        self.sb.add_defect(self.failed, "G5", related=["REQ-002", *self.failing], status="fixed")
        last: dict = {}
        for _ in range(2):
            self.gate_g4()
            last = self.sb.gate("G5")[1]
            self.sb.add_defect(last["record_id"], "G5")
        self.assertEqual(last["status"], "BLOCKED")
        self.assertEqual(last.get("blocked_reason"), "three_consecutive_identical_failures")
        d = self.assert_state("VERIFICATION_FAILED")
        self.assertEqual((d.get("closure_gate_status"), (d.get("last_verification") or {}).get("status")),
                         ("BLOCKED", "BLOCKED"))
        self.assert_not_done(self.defect_line())

    def test_withheld_verification_is_unknown(self):
        """The signed ledger shows a PASS but its evidence does not match: do not guess 'not verified' either."""
        res = self.close_defect()
        ev = self.sb.root / res["evidence"][0]["path"]
        (ev.parent / "stdout.bin").write_bytes(b"edited output")
        d = self.assert_state("UNKNOWN")
        self.assertEqual((d["verified_by"], d.get("verification_withheld")), (None, res["record_id"]))
        line = self.defect_line()
        self.assertIn("cannot be determined", line)
        self.assertIn(f"{res['record_id']} withheld", line)
        self.assertNotIn("not verified yet", line)

    def test_report_and_session_start_use_the_same_states(self):
        res = self.close_defect()
        wf = self.s["wf"]
        wf.write_bytes(wf.read_bytes() + b"\n")
        report = self.report()
        self.assertIn("closure: REVERIFY_REQUIRED", report)
        self.assertIn(f"DEFECT-001 [fixed — previously passed in {res['record_id']}", report)
        self.assertNotIn("closure: VERIFIED", report)
        self.assertNotIn("closure: CLOSED", report)
        code, out = self.sb.hook("session-start", {"hook_event_name": "SessionStart", "cwd": str(self.sb.root)})
        self.assertEqual(code, 0, out)
        self.assertIn("DEFECT-001 REVERIFY_REQUIRED", out)
        self.bug()
        self.gate_g4()
        self.assertEqual(self.sb.gate("G5")[1]["status"], "FAILED")
        report = self.report()
        self.assertIn("closure: VERIFICATION_FAILED", report)
        self.assertNotIn("closure: CLOSED", report)

    def test_json_keeps_old_keys_and_adds_the_history(self):
        self.close_defect()
        d = self.defect()
        missing = (V013_DEFECT_KEYS | V014_DEFECT_KEYS) - set(d)
        self.assertEqual(missing, set())
        self.assertIn("verification_history", d)
        self.assertIn("last_verification", d)
        self.assertIn(d["closure_state"], ALL_STATES)


@unittest.skipUnless(has_pytest(), "pytest not installed")
class DisplayStateBlockedRed(unittest.TestCase):
    def test_validator_core_change_after_closure_is_reverify_required(self):
        """Gates BLOCKED by validator integrity (core changed, not re-pinned): the past PASS needs re-verification."""
        sb = Sandbox()
        try:
            sb.plugin = copy_plugin(sb.tmp)
            sb.entry = sb.plugin / "validator" / "vmodel.py"
            s = fail_g5(sb)
            sb.add_defect(s["failed"], "G5", related=["REQ-002", *s["failing"]], status="fixed")
            s["wf"].write_text(s["good"], encoding="utf-8")
            sb.regate_g4()
            passed = sb.gate("G5")[1]
            self.assertEqual(passed["status"], "PASSED")
            init_py = sb.plugin / "validator" / "vmodel_validator" / "__init__.py"
            os.chmod(init_py, 0o644)  # a release copy is read-only
            init_py.write_text(init_py.read_text(encoding="utf-8") + "# changed core\n", encoding="utf-8")
            d = sb.status()["work_items"][0]["defects"][0]
            self.assertEqual((d.get("closure_state"), d.get("closure_gate_status"), d["verified_by"]),
                             ("REVERIFY_REQUIRED", "BLOCKED", passed["record_id"]))
            line = [ln.strip() for ln in sb.vm("status", "WI-001")[1].splitlines()
                    if ln.strip().startswith("DEFECT-001")][0]
            self.assertTrue(line.startswith("DEFECT-001 REVERIFY_REQUIRED "), line)
            self.assertIn("resolve the block", line)
            self.assertNotIn("re-verify", line)  # impossible until the block is resolved
        finally:
            sb.cleanup()


class DisplayStateSkillWordingRed(unittest.TestCase):
    def test_skills_name_the_states_that_are_not_closed(self):
        for name in ("start", "rework"):
            text = (PLUGIN / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
            for state in ("CLOSED", "REVERIFY_REQUIRED", "VERIFICATION_FAILED", "UNKNOWN"):
                self.assertIn(state, text, f"{name}: {state}")
            self.assertNotRegex(text, r"\bVERIFIED means\b", name)


class DisplayStateReviewRed(FailedG5Case):
    """Findings of the independent review of 73d158e (2026-11-09), reproduced before the fix (they also fail there)."""

    def state(self) -> str:
        return self.defect().get("closure_state")

    def reject_g4(self) -> str:
        self.sb.review("G4", verdict="reject")
        res = self.sb.gate("G4")[1]
        self.assertEqual(res["status"], "FAILED", res)
        return res["record_id"]

    def test_upstream_failure_cited_after_the_closure_is_verification_failed(self):
        """Finding 1: the defect itself cites a later G4 failure -> the fix no longer verifies, not 'not verified yet'."""
        res = self.close_defect()
        g4_fail = self.reject_g4()
        self.sb.add_defect(g4_fail, "G4")
        d = self.defect()
        self.assertEqual(d.get("closure_state"), "VERIFICATION_FAILED")
        self.assertEqual(((d.get("last_verification") or {}).get("record"), (d.get("last_verification") or {}).get("gate")),
                         (g4_fail, "G4"))
        line = self.defect_line()
        self.assertIn(f"G4 re-verification {g4_fail} FAILED", line)
        self.assertIn(f"previously passed in {res['record_id']}", line)

    def test_claimed_fix_rejected_at_g4_is_verification_failed_until_it_passes(self):
        """Finding 1: the claimed fix is rejected by the G4 review and that failure is cited."""
        self.sb.add_defect(self.failed, "G5", related=["REQ-002", *self.failing], status="fixed")
        self.s["wf"].write_text(self.s["good"], encoding="utf-8")
        g4_fail = self.reject_g4()
        self.sb.add_defect(g4_fail, "G4")
        self.assertEqual(self.state(), "VERIFICATION_FAILED")
        self.gate_g4()
        self.assertEqual(self.state(), "FIX_APPLIED")  # the re-verification moved past G4; G5 not re-run yet
        self.assertEqual(self.sb.gate("G5")[1]["status"], "PASSED")
        self.assertEqual(self.state(), "CLOSED")

    def test_review_required_after_a_failed_reverification_does_not_reset_it(self):
        """Finding 4: REVIEW_REQUIRED is neutral (as for the 3-strike counter); the last decisive result is the failure."""
        self.s["wf"].write_text(self.s["good"], encoding="utf-8")
        first = self.reject_g4()
        self.sb.add_defect(first, "G4", status="fixed")
        second = self.reject_g4()
        self.assertEqual(self.state(), "VERIFICATION_FAILED")
        self.sb.add_defect(second, "G4")  # changes defects.json, so the next G4 run lacks a matching review
        res = self.sb.gate("G4")[1]
        self.assertEqual(res["status"], "REVIEW_REQUIRED", res)
        d = self.defect()
        self.assertEqual((d.get("closure_state"), (d.get("last_verification") or {}).get("record")),
                         ("VERIFICATION_FAILED", second))

    def test_withheld_pass_is_not_shown_as_a_past_success(self):
        """Finding 3: a PASS whose evidence does not match the ledger is named as withheld, not as 'previously ...'."""
        res = self.close_defect()
        ev = self.sb.root / res["evidence"][0]["path"]
        (ev.parent / "stdout.bin").write_bytes(b"edited output")
        self.s["wf"].write_text(self.s["good"].replace("if n <= 0:", "if n < 0:"), encoding="utf-8")
        self.gate_g4()
        self.assertEqual(self.sb.gate("G5")[1]["status"], "FAILED")
        self.assertEqual(self.state(), "VERIFICATION_FAILED")
        line = self.defect_line()
        self.assertNotIn(f"previously verified by {res['record_id']}", line)
        self.assertNotIn(f"previously passed in {res['record_id']}", line)
        self.assertIn(f"{res['record_id']} withheld", line)
        details = [ln for ln in self.report().splitlines() if "closure: VERIFICATION_FAILED" in ln][0]
        self.assertNotIn(f"previously verified by {res['record_id']}", details)
        self.assertNotIn(f"previously passed in {res['record_id']}", details)

    def test_verified_by_wording_is_reserved_for_closed(self):
        """'verified by R...' must mean 'verified now': a past PASS of a STALE gate is worded differently."""
        res = self.close_defect()
        self.assertIn(f"verified by {res['record_id']}", self.defect_line())
        wf = self.s["wf"]
        wf.write_bytes(wf.read_bytes() + b"\n")
        self.assertEqual(self.state(), "REVERIFY_REQUIRED")
        self.assertNotIn("verified by", self.defect_line())
        lines = [ln for ln in self.report().splitlines() if "DEFECT-001" in ln or "closure:" in ln]
        self.assertTrue(lines)
        for ln in lines:
            self.assertNotIn("verified by", ln)
        self.set_defect(status="open")  # claim note in a non-closed state
        self.assertNotIn("verified by", self.status_text().split("DEFECT-001", 1)[1])

    def test_upstream_repass_does_not_hide_a_downstream_failure(self):
        """Re-review of c4e4da5: after G5 failed again, a G4 re-pass must not turn VERIFICATION_FAILED into FIX_APPLIED
        while G5 still stands FAILED (a DEFECT citing only G5 already stayed VERIFICATION_FAILED)."""
        self.sb.add_defect(self.failed, "G5", related=["REQ-002", *self.failing], status="fixed")
        self.sb.add_defect(self.reject_g4(), "G4")  # the claimed fix is rejected (the bug is still there)
        self.gate_g4()
        self.assertEqual(self.state(), "FIX_APPLIED")
        again = self.sb.gate("G5")[1]
        self.assertEqual(again["status"], "FAILED")
        self.assertEqual(self.state(), "VERIFICATION_FAILED")
        self.sb.add_defect(again["record_id"], "G5")
        self.gate_g4()  # re-reviewed, G5 not re-run
        self.assertEqual(self.gates()["G5"], "FAILED")
        d = self.defect()
        self.assertEqual((d.get("closure_state"), (d.get("last_verification") or {}).get("record"),
                          d.get("closure_action")), ("VERIFICATION_FAILED", again["record_id"], "rework"))
        self.s["wf"].write_text(self.s["good"], encoding="utf-8")
        self.gate_g4()
        self.assertEqual(self.sb.gate("G5")[1]["status"], "PASSED")
        self.assertEqual(self.state(), "CLOSED")

    def test_three_strike_then_user_unblock_says_rework(self):
        if os.name != "posix":
            self.skipTest("the user unblock needs a pseudo terminal (POSIX)")
        self.sb.add_defect(self.failed, "G5", related=["REQ-002", *self.failing], status="fixed")
        for _ in range(2):
            self.gate_g4()
            last = self.sb.gate("G5")[1]
            self.sb.add_defect(last["record_id"], "G5")
        self.assertIn("the user must unblock", self.defect_line())
        out = self.sb.run_tty("unblock", "WI-001", "G5", "--reason", "user reviewed")
        self.assertIn(b"unblocked", out)
        self.assertEqual(self.state(), "VERIFICATION_FAILED")
        line = self.defect_line()
        self.assertNotIn("unblock", line)
        self.assertIn("rework", line)
        self.s["wf"].write_text(self.s["good"], encoding="utf-8")
        self.gate_g4()
        self.assertEqual(self.sb.gate("G5")[1]["status"], "PASSED")
        self.assertEqual(self.state(), "CLOSED")


@unittest.skipUnless(has_pytest(), "pytest not installed")
class DisplayStateReviewBlockedRed(unittest.TestCase):
    def test_integrity_block_after_a_failed_reverification_does_not_say_unblock(self):
        """Finding 2: `vmodel unblock` only lifts a 3-strike block; an integrity block must be resolved instead."""
        sb = Sandbox()
        try:
            sb.plugin = copy_plugin(sb.tmp)
            sb.entry = sb.plugin / "validator" / "vmodel.py"
            s = fail_g5(sb)
            sb.add_defect(s["failed"], "G5", related=["REQ-002", *s["failing"]], status="fixed")
            sb.regate_g4()
            self.assertEqual(sb.gate("G5")[1]["status"], "FAILED")
            init_py = sb.plugin / "validator" / "vmodel_validator" / "__init__.py"
            os.chmod(init_py, 0o644)
            init_py.write_text(init_py.read_text(encoding="utf-8") + "# changed core\n", encoding="utf-8")
            d = sb.status()["work_items"][0]["defects"][0]
            self.assertEqual((d.get("closure_state"), d.get("closure_gate_status")), ("VERIFICATION_FAILED", "BLOCKED"))
            line = [ln.strip() for ln in sb.vm("status", "WI-001")[1].splitlines()
                    if ln.strip().startswith("DEFECT-001")][0]
            self.assertNotIn("unblock", line)
            self.assertIn("resolve the block", line)
            sb.vm("report", "WI-001")
            report = (sb.root / ".vmodel/reports/WI-001.md").read_text(encoding="utf-8")
            details = [ln for ln in report.splitlines() if "closure: VERIFICATION_FAILED" in ln][0]
            self.assertNotIn("unblock", details)
        finally:
            sb.cleanup()


class DisplayStateChar(FailedG5Case):
    """Behaviour that the first 0.1.4 build already had and the new states must keep."""

    def test_states_before_verification_and_after_closure(self):
        self.sb.add_defect(self.failed, "G5", related=["REQ-002", *self.failing])
        self.assertEqual(self.defect().get("closure_state"), "OPEN")
        self.set_defect(status="fixed")
        self.assertEqual(self.defect().get("closure_state"), "FIX_APPLIED")
        self.s["wf"].write_text(self.s["good"], encoding="utf-8")
        self.gate_g4()
        res = self.sb.gate("G5")[1]
        d = self.defect()
        self.assertEqual((d.get("closure_state"), d["verified_by"], d.get("closure_gate_status")),
                         ("CLOSED", res["record_id"], "PASSED"))
        self.assertIn(f"DEFECT-001 [fixed — verified by {res['record_id']}]", self.report())  # 0.1.3 wording

    def test_verified_by_keeps_the_past_pass_when_stale(self):
        res = self.close_defect()
        wf = self.s["wf"]
        wf.write_bytes(wf.read_bytes() + b"\n")
        d = self.defect()
        self.assertEqual((d["verified_by"], d["claimed_status"]), (res["record_id"], "fixed"))
        self.assertNotEqual(d.get("closure_state"), "CLOSED")

    def test_another_defects_failure_on_the_closure_gate_is_not_closed(self):
        """Per gate, not per DEFECT (conservative): a later G5 failure owned by another DEFECT reopens the display."""
        self.close_defect()
        self.s["wf"].write_text(self.s["good"].replace("if n <= 0:", "if n < 0:"), encoding="utf-8")
        self.gate_g4()
        other = self.sb.gate("G5")[1]
        self.assertEqual(other["status"], "FAILED")
        self.sb.add_defect(other["record_id"], "G5", did="DEFECT-002")
        self.assertNotEqual(self.defect().get("closure_state"), "CLOSED")

    def test_ledger_failure_after_a_failed_reverification_is_unknown(self):
        self.sb.add_defect(self.failed, "G5", related=["REQ-002", *self.failing], status="fixed")
        self.gate_g4()
        self.assertEqual(self.sb.gate("G5")[1]["status"], "FAILED")
        ledger = self.sb.root / ".vmodel/state/ledger.jsonl"
        ledger.write_text(ledger.read_text(encoding="utf-8").replace('"status":"FAILED"', '"status":"PASSED"', 1),
                          encoding="utf-8")
        d = self.defect()
        self.assertEqual((d.get("closure_state"), d["verified_by"]), ("UNKNOWN", None))

    def test_json_keeps_the_0_1_3_and_0_1_4_keys(self):
        self.sb.add_defect(self.failed, "G5", related=["REQ-002", *self.failing])
        self.assertEqual((V013_DEFECT_KEYS | V014_DEFECT_KEYS) - set(self.defect()), set())


class DisplayStateInvariant(FailedG5Case):
    def test_display_commands_do_not_touch_ledger_or_manifests(self):
        """Display only: status/lint/report/trace/impact/SessionStart in the REVERIFY_REQUIRED and
        VERIFICATION_FAILED situations write no ledger record and change no manifest or gate state."""
        self.close_defect()
        wf = self.s["wf"]

        def snapshot():
            state = self.sb.root / ".vmodel/state"
            hashes = {g: self.sb.vm("hash", "WI-001", g)[1].strip() for g in ("G1", "G2", "G3", "G4", "G5")}
            return {"ledger": (state / "ledger.jsonl").read_bytes(), "head": (state / "head.json").read_bytes(),
                    "hashes": hashes, "gates": self.gates()}

        def display():
            for args in (("status",), ("status", "WI-001", "--json"), ("lint", "WI-001"), ("report", "WI-001"),
                         ("trace", "WI-001"), ("impact", "WI-001")):
                self.sb.vm(*args)
            self.sb.hook("session-start", {"hook_event_name": "SessionStart", "cwd": str(self.sb.root)})

        wf.write_bytes(wf.read_bytes() + b"\n")  # STALE
        before = snapshot()
        display()
        self.assertEqual(snapshot(), before)
        wf.write_text(self.s["good"].replace("if n <= 0:", "if n < 0:"), encoding="utf-8")
        self.gate_g4()
        self.assertEqual(self.sb.gate("G5")[1]["status"], "FAILED")
        before = snapshot()
        display()
        self.assertEqual(snapshot(), before)


if __name__ == "__main__":
    unittest.main()

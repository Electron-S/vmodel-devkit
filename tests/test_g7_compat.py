"""0.2.0 compatibility: G1-G6 decisions, manifests, signed evidence, upgrade (T14, T17, T20; REQ-G7-22, 23)."""
from __future__ import annotations

import json
import os
import shutil
import unittest

from g7_base import (GATES7, GRADECALC, PIPELINE_SYSTEM, G7Class, applicability, gate_view, ledger_records,
                     set_test_commands, states, wi_status)
from helpers import PIPELINE, PLUGIN, Sandbox, copy_plugin, has_pytest, old_release

GATES6 = GATES7[:6]
GC_ENDPOINTS = ["CLI 사용자", "HTTP 클라이언트"]


def build(plugin, fixture, mode: str, integration: str | None = None, overlay=None, na=None,
          upto: str = "G6") -> Sandbox:
    sb = Sandbox(fixture=fixture, plugin=plugin)
    sb.init()
    sb.new_wi()
    set_test_commands(sb, mode, integration=integration)
    for g in GATES7[: GATES7.index(upto) + 1]:
        sb.prepare(g)
        if g == "G4" and overlay is not None:
            shutil.copytree(overlay, sb.root, dirs_exist_ok=True)
        if g in ("G1", "G2", "G3", "G4"):
            sb.review(g, extra=applicability(na) if (na and g in ("G2", "G3")) else None)
        res = sb.gate(g)[1]
        assert res["status"] == "PASSED", json.dumps(res, indent=1, ensure_ascii=False)[:3000]
    return sb


def projection(sb: Sandbox) -> list:
    return [(r["gate"], r["status"], r.get("failure_signature"), r.get("blocked_reason"),
             tuple((c["id"], c["status"]) for c in r["checks"]),
             tuple(sorted((r.get("executed_tests") or {}).items())), r.get("applicability"))
            for r in ledger_records(sb) if r.get("type") == "gate" and r["gate"] in GATES6]


@unittest.skipUnless(has_pytest(), "pytest not installed")
class CompatInvariant(unittest.TestCase):
    """C1/C2 and T17: without system_test, the 0.2.0 release and this core agree on G1-G6 decisions and manifests."""

    def setUp(self):
        self.old = old_release("0.2.0")
        if self.old is None:
            self.skipTest("0.2.0 release not available")

    def compare(self, run) -> None:
        new_proj, sb = run(PLUGIN)
        try:
            old_proj, sb_old = run(self.old)
            sb_old.cleanup()
            self.assertEqual(new_proj, old_proj)  # same history, same G1-G6 decisions
            for g in GATES6:  # the same project hashed by both cores gives the same G1-G6 manifests
                files = {}
                for plugin in (PLUGIN, self.old):
                    sb.entry = plugin / "validator" / "vmodel.py"
                    code, out = sb.vm("hash", "WI-001", g, "--json")
                    files[str(plugin)] = json.loads(out)["files"]
                self.assertEqual(files[str(PLUGIN)], files[str(self.old)], g)
        finally:
            sb.cleanup()

    def test_C1_C2_gradecalc_mixed_unit_command_with_a_rework(self):
        def run(plugin) -> tuple[list, Sandbox]:
            sb = build(plugin, GRADECALC, "mixed", na=GC_ENDPOINTS)
            p = sb.root / "src/gradecalc/grading.py"
            p.write_text(p.read_text(encoding="utf-8").replace("if score >= 90:", "if score > 90:"), encoding="utf-8")
            sb.review("G4")
            sb.gate("G4")
            failed = sb.gate("G5")[1]
            sb.add_defect(failed.get("record_id") or "R00000", "G5", fix_scope=["src/gradecalc/grading.py"])
            return projection(sb), sb
        self.compare(run)

    def test_C1_C2_pipeline_split_integration_unit_command_also_runs_system_tests(self):
        def run(plugin) -> tuple[list, Sandbox]:
            sb = build(plugin, PIPELINE, "mixed", integration="tests/integration", overlay=PIPELINE_SYSTEM)
            return projection(sb), sb
        self.compare(run)


@unittest.skipUnless(has_pytest(), "pytest not installed")
class CompatAccept(unittest.TestCase):
    def setUp(self):
        self.old = old_release("0.2.0")
        if self.old is None:
            self.skipTest("0.2.0 release not available")

    def test_T17_020_signed_ledger_and_evidence_verify_with_this_core(self):
        sb = build(self.old, GRADECALC, "mixed", na=GC_ENDPOINTS)
        try:
            sb.entry = PLUGIN / "validator" / "vmodel.py"
            recs = [r for r in ledger_records(sb) if r.get("type") == "gate"]
            self.assertTrue(recs and all(r["validator"]["version"] == "0.2.0" for r in recs))
            for r in recs:
                for ev in r.get("evidence") or []:
                    code, out = sb.vm("verify-evidence", str(sb.root / ev["path"]))
                    self.assertEqual(code, 0, out)
            out = sb.vm("audit")[1]
            self.assertIn("ledger entries", out)
            self.assertNotIn("evidence not referenced", out)
            self.assertNotIn("signature", out)
        finally:
            sb.cleanup()

    @unittest.skipUnless(os.name == "posix", "a POSIX pty is needed")
    def test_T20_020_project_upgrades_configures_system_test_and_completes(self):
        sb = build(self.old, GRADECALC, "mixed", na=GC_ENDPOINTS)  # a 0.2.0 project: unit command runs everything
        try:
            old_records = ledger_records(sb)
            ledger_bytes = (sb.root / ".vmodel/state/ledger.jsonl").read_bytes()
            sb.entry = PLUGIN / "validator" / "vmodel.py"
            self.assertFalse(sb.status()["validator"]["ok"])
            sb.run_tty("lock", "--accept-current", "--reason", "upgrade to 0.3.0")
            self.assertTrue((sb.root / ".vmodel/state/ledger.jsonl").read_bytes().startswith(ledger_bytes))
            self.assertEqual(ledger_records(sb)[:len(old_records)], old_records)
            self.assertEqual(sb.vm("audit")[0], 0)
            st = states(sb)
            self.assertEqual([st[g] for g in GATES6], ["STALE"] * 6)  # core change (existing rule), not G7
            self.assertTrue(gate_view(sb, "G7").get("not_evaluated"))
            self.assertEqual(wi_status(sb)["status"], "IN_PROGRESS")
            out = sb.run_tty("configure-tests", "--system", "tests/system").decode("utf-8", "replace")
            self.assertIn("system_test", sb.config(), out)
            for g in GATES6:  # G1-G3 reviews are reused as they are; G4 needs a review (config changed)
                if g == "G4":
                    sb.review("G4")
                res = sb.gate(g)[1]
                self.assertEqual(res["status"], "PASSED", json.dumps(res, ensure_ascii=False)[:3000])
            res = sb.gate("G7")[1]
            self.assertEqual(res["status"], "PASSED", res)
            self.assertEqual(wi_status(sb)["status"], "COMPLETED")
        finally:
            sb.cleanup()


@unittest.skipUnless(has_pytest() and os.name == "posix", "pytest and a POSIX pty are needed")
class CoreChangeAccept(G7Class):
    def test_T14_core_change_stales_every_pass_including_g7(self):
        res = self.g7()
        self.assertEqual(res["status"], "PASSED", res)
        copy = copy_plugin(self.sb.tmp)
        (copy / "RELEASE_MANIFEST.json").unlink(missing_ok=True)
        gp = copy / "validator/vmodel_validator/gates.py"
        gp.write_text(gp.read_text(encoding="utf-8") + "\n# local core change\n", encoding="utf-8")
        self.sb.entry = copy / "validator" / "vmodel.py"
        try:
            self.sb.run_tty("lock", "--accept-current", "--reason", "core change test")
            self.assertEqual(states(self.sb), {g: "STALE" for g in GATES7})
            self.assertEqual(wi_status(self.sb)["status"], "IN_PROGRESS")
        finally:
            self.sb.entry = PLUGIN / "validator" / "vmodel.py"
            shutil.rmtree(copy, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()

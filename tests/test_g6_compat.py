"""Staleness, preservation of G1-G5 evidence and 0.1.5 compatibility (T14-T17, T20; REQ-G6-22, 26)."""
from __future__ import annotations

import json
import os
import shutil
import unittest

from g6_base import RED, SandboxClass, advance, gate_view, ledger_records, wi_status
from helpers import PIPELINE, PLUGIN, SINGLE, Sandbox, copy_plugin, has_pytest, old_release

GATES5 = ("G1", "G2", "G3", "G4", "G5")


def states(sb: Sandbox) -> dict:
    return {g["gate"]: g["status"] for g in wi_status(sb)["gates"]}


class CompatRed(SandboxClass):
    """pipeline, split commands, G1-G5 PASSED."""

    def test_T15_g6_keeps_g1_g5_records_and_evidence(self):
        ledger = self.sb.root / ".vmodel/state/ledger.jsonl"
        before = ledger.read_bytes()
        ev_before = {p: p.read_bytes() for p in (self.sb.root / ".vmodel/evidence").rglob("*") if p.is_file()}
        self.assertTrue(gate_view(self.sb, "G6").get("not_evaluated"), f"{RED} G6 not evaluated yet")
        res = self.g6()
        self.assertEqual(res["status"], "PASSED", f"{RED} {res}")
        self.assertTrue(ledger.read_bytes().startswith(before))  # append-only: nothing rewritten
        for p, b in ev_before.items():
            self.assertEqual(p.read_bytes(), b, p)
        self.assertEqual({g: s for g, s in states(self.sb).items() if g in GATES5}, {g: "PASSED" for g in GATES5})
        self.assertEqual(self.sb.vm("audit")[0], 0)

    def test_T14_interface_test_and_review_changes_stale_the_right_gates(self):
        res = self.g6()
        self.assertEqual(res["status"], "PASSED", f"{RED} {res}")
        # (1) a G2 review replaced and re-evaluated: only G6 depends on review files
        self.sb.review("G2", extra={"summary": "G2 re-reviewed"})
        self.assertEqual(self.sb.gate("G2")[1]["status"], "PASSED")
        self.assertEqual(states(self.sb), {"G1": "PASSED", "G2": "PASSED", "G3": "PASSED", "G4": "PASSED",
                                           "G5": "PASSED", "G6": "STALE",
                                           "G7": "IN_PROGRESS"})  # 0.3.0 REQ-G7-17 (0.2.0: NOT_IMPLEMENTED)
        self.assertEqual(self.g6()["status"], "PASSED")
        # (2) an integration test file change: G4, G5 and G6
        t = self.sb.root / "tests/integration/test_pipeline.py"
        t.write_bytes(t.read_bytes() + b"\n")
        st = states(self.sb)
        self.assertEqual((st["G3"], st["G4"], st["G5"], st["G6"]), ("PASSED", "STALE", "STALE", "STALE"))
        t.write_bytes(t.read_bytes()[:-1])
        self.assertEqual(states(self.sb)["G6"], "PASSED")
        # (3) an interface change: G2 and everything after it
        arch = self.sb.load("architecture.json")
        arch["interfaces"][0]["description"] += " (변경)"
        self.sb.save("architecture.json", arch)
        st = states(self.sb)
        self.assertEqual([st[g] for g in ("G1", "G2", "G3", "G4", "G5", "G6")],
                         ["PASSED", "STALE", "STALE", "STALE", "STALE", "STALE"])

    def test_T14_g4_review_file_change_stales_g6(self):
        res = self.g6()
        self.assertEqual(res["status"], "PASSED", f"{RED} {res}")
        path = self.sb.wi_dir / "reviews/G4.json"
        doc = json.loads(path.read_text(encoding="utf-8"))
        doc["summary"] += " (edited)"
        path.write_text(json.dumps(doc), encoding="utf-8")
        self.assertEqual(states(self.sb)["G6"], "STALE")
        self.assertEqual(states(self.sb)["G4"], "PASSED")


@unittest.skipUnless(has_pytest() and os.name == "posix", "pytest and a POSIX pty are needed")
class CompatAccept(SandboxClass):
    def test_T16_core_change_stales_every_pass_including_g6(self):
        res = self.g6()
        self.assertEqual(res["status"], "PASSED", res)
        copy = copy_plugin(self.sb.tmp)
        # a different core build: a released copy's file list would (rightly) keep integrity BLOCKED after the edit
        (copy / "RELEASE_MANIFEST.json").unlink(missing_ok=True)
        gp = copy / "validator/vmodel_validator/gates.py"
        gp.write_text(gp.read_text(encoding="utf-8") + "\n# local core change\n", encoding="utf-8")
        self.sb.entry = copy / "validator" / "vmodel.py"
        try:
            st = self.sb.status()
            self.assertFalse(st["validator"]["ok"])  # lock mismatch: nothing is trusted
            self.sb.run_tty("lock", "--accept-current", "--reason", "core change test")
            sts = states(self.sb)
            self.assertEqual([sts[g] for g in ("G1", "G2", "G3", "G4", "G5", "G6")], ["STALE"] * 6)
            self.assertTrue(any(ln["type"] == "gate" and ln["gate"] == "G6" for ln in ledger_records(self.sb)))
        finally:
            self.sb.entry = PLUGIN / "validator" / "vmodel.py"
            shutil.rmtree(copy, ignore_errors=True)

    def test_T20_015_project_upgrades_and_migrates(self):
        """0.1.5 builds G1-G5 (unit command runs everything), the user re-pins 0.2.0 and adds integration_test."""
        old = old_release("0.1.5")
        if old is None:
            self.skipTest("0.1.5 release not available")
        sb = Sandbox(fixture=PIPELINE, plugin=old)
        try:
            sb.init()
            sb.new_wi()
            advance(sb, "G5")
            old_records = ledger_records(sb)
            sb.entry = PLUGIN / "validator" / "vmodel.py"
            self.assertFalse(sb.status()["validator"]["ok"])
            sb.run_tty("lock", "--accept-current", "--reason", "upgrade to 0.2.0")
            self.assertEqual(ledger_records(sb)[:len(old_records)], old_records)
            self.assertTrue(all(r["validator"]["version"] == "0.1.5" for r in old_records if r.get("type") == "gate"))
            self.assertEqual(sb.vm("audit")[0], 0)
            for r in old_records:
                for ev in r.get("evidence") or []:
                    self.assertEqual(sb.vm("verify-evidence", str(sb.root / ev["path"]))[0], 0, ev)
            st = states(sb)
            self.assertEqual([st[g] for g in GATES5], ["STALE"] * 5)  # core change (D1), not G6
            self.assertTrue(gate_view(sb, "G6").get("not_evaluated"))
            out = sb.run_tty("configure-tests", "--integration", "tests/integration").decode("utf-8", "replace")
            self.assertIn("integration_test", sb.config(), out)
            for g in GATES5:  # G1-G3 reviews are reused as they are; G4 needs a review (config changed)
                if g == "G4":
                    sb.review("G4")
                res = sb.gate(g)[1]
                self.assertEqual(res["status"], "PASSED", res)
            res = sb.gate("G6")[1]
            self.assertEqual(res["status"], "PASSED", res)
        finally:
            sb.cleanup()


@unittest.skipUnless(has_pytest(), "pytest not installed")
class CompatInvariant(unittest.TestCase):
    """C1/C2 and T17: same project and history, the 0.1.5 release and this core agree on G1-G5."""

    def test_C1_C2_T17_same_g1_g5_decisions_and_manifests_without_interfaces(self):
        old = old_release("0.1.5")
        if old is None:
            self.skipTest("0.1.5 release not available")

        def run(plugin) -> tuple[list, Sandbox]:
            sb = Sandbox(fixture=SINGLE, plugin=plugin)
            sb.init()
            sb.new_wi()
            advance(sb, "G5", na=True)
            p = sb.root / "src/meanstat/stats.py"
            p.write_text(p.read_text(encoding="utf-8").replace("if not values", "if values is None"), encoding="utf-8")
            sb.review("G4")
            sb.gate("G4")
            failed = sb.gate("G5")[1]
            sb.add_defect(failed.get("record_id") or "R00000", "G5", fix_scope=["src/meanstat/stats.py"])
            proj = [(r["gate"], r["status"], r.get("failure_signature"),
                     tuple((c["id"], c["status"]) for c in r["checks"]),
                     tuple(sorted((r.get("executed_tests") or {}).items())))
                    for r in ledger_records(sb) if r.get("type") == "gate" and r["gate"] in GATES5]
            return proj, sb

        new_proj, sb = run(PLUGIN)
        try:
            old_proj, sb_old = run(old)
            sb_old.cleanup()
            self.assertEqual(new_proj, old_proj)  # C1: same history, same G1-G5 decisions
            # C2: the same project hashed by both cores gives the same G1-G5 manifests
            for g in GATES5:
                files = {}
                for plugin in (PLUGIN, old):
                    sb.entry = plugin / "validator" / "vmodel.py"
                    code, out = sb.vm("hash", "WI-001", g, "--json")
                    files[str(plugin)] = json.loads(out)["files"]
                self.assertEqual(files[str(PLUGIN)], files[str(old)], g)
        finally:
            sb.cleanup()

    def test_T17_015_signed_evidence_verifies_with_this_core(self):
        old = old_release("0.1.5")
        if old is None:
            self.skipTest("0.1.5 release not available")
        sb = Sandbox(fixture=PIPELINE, plugin=old)
        try:
            sb.init()
            sb.new_wi()
            sb.split_tests()
            advance(sb, "G5")
            sb.entry = PLUGIN / "validator" / "vmodel.py"
            recs = [r for r in ledger_records(sb) if r.get("type") == "gate"]
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


if __name__ == "__main__":
    unittest.main()

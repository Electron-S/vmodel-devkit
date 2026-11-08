"""v0.1.4 cross-version guarantees against the immutable 0.1.3 release (dist/vmodel-0.1.3 or the git tag v0.1.3).

- Gate decisions and manifest hashes are the same as 0.1.3 for the same history (the 0.1.4 changes are display-only).
- A ledger and evidence signed by 0.1.3 still verify under the new core, are never rewritten, and keep their 0.1.3
  validator version and core hash; after the user re-pins, the old PASS results are STALE and re-verification writes
  new records with the new version (SPEC section 11).
Tests skip when the 0.1.3 release cannot be found (e.g. an exported tree without .git and dist/).
"""
from __future__ import annotations

import json
import sys
import unittest

from helpers import PLUGIN, REPO, Sandbox, fail_g5, has_pytest, old_release
from vmodel_version import VERSION

GATES = ("G1", "G2", "G3", "G4", "G5")


def projection(sb: Sandbox) -> list[tuple]:
    """What a gate decided, without times, paths, project ids or core hashes."""
    out = []
    for ln in (sb.root / ".vmodel/state/ledger.jsonl").read_text(encoding="utf-8").splitlines():
        r = json.loads(ln)["record"]
        if r.get("type") != "gate":
            out.append((r.get("type"), r.get("work_item"), r.get("gate")))
            continue
        out.append(("gate", r["work_item"], r["gate"], r["status"], r.get("blocked_reason"), r.get("failure_signature"),
                    tuple((c["id"], c["status"]) for c in r.get("checks") or []),
                    tuple(sorted((r.get("executed_tests") or {}).items()))))
    return out


def rework_history(plugin) -> tuple[list[tuple], list[str]]:
    """G5 FAILED -> DEFECT citing the failure and a PASSED record (invalid) with a missing link -> fix -> PASS,
    then the display commands, then a REVIEW_REQUIRED round."""
    sb = Sandbox(plugin=plugin)
    try:
        s = fail_g5(sb)
        sb.add_defect(s["failed"], "G5", related=["REQ-002", *s["failing"][1:]], status="fixed")
        doc = sb.load("defects.json")
        doc["defects"][0]["found_in_records"].append(s["g4_pass"])
        sb.save("defects.json", doc)
        s["wf"].write_text(s["good"], encoding="utf-8")
        sb.regate_g4()
        statuses = [sb.gate("G5")[1]["status"]]
        for args in (("status",), ("lint", "WI-001"), ("report", "WI-001"), ("trace", "WI-001")):
            sb.vm(*args)
        s["wf"].write_bytes(s["wf"].read_bytes() + b"\n")
        statuses.append(sb.gate("G4")[1]["status"])
        statuses.append(sb.gate("G5")[1]["status"])
        return projection(sb), statuses
    finally:
        sb.cleanup()


@unittest.skipUnless(has_pytest(), "pytest not installed")
class GateDecisionInvariant(unittest.TestCase):
    def setUp(self):
        self.old = old_release("0.1.3")
        if self.old is None:
            self.skipTest("0.1.3 release not available")

    def test_same_history_gives_the_same_gate_decisions(self):
        old_proj, old_st = rework_history(self.old)
        new_proj, new_st = rework_history(PLUGIN)
        self.assertEqual(old_st, ["PASSED", "REVIEW_REQUIRED", "BLOCKED"])
        self.assertEqual(new_st, old_st)
        self.assertEqual(new_proj, old_proj)

    def test_manifest_hashes_are_computed_identically(self):
        """Same project, both cores: identical per-file hashes and manifest hash for every gate."""
        import subprocess
        sb = Sandbox()
        try:
            s = fail_g5(sb)
            sb.add_defect(s["failed"], "G5", related=s["failing"], status="fixed")
            old_entry = self.old / "validator" / "vmodel.py"
            for g in GATES:
                code, new = sb.vm("hash", "WI-001", g, "--json")
                self.assertEqual(code, 0, new)
                r = subprocess.run([sys.executable, "-I", "-B", str(old_entry), "hash", "WI-001", g, "--json"],
                                   cwd=str(sb.root), env=sb.env, capture_output=True, timeout=120)
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertEqual(json.loads(new), json.loads(r.stdout.decode("utf-8")), g)
        finally:
            sb.cleanup()


@unittest.skipUnless(has_pytest(), "pytest not installed")
@unittest.skipUnless(sys.platform != "win32", "re-pinning needs a pty (POSIX only)")
class OldEvidenceAccept(unittest.TestCase):
    def test_013_ledger_and_evidence_verify_under_014(self):
        old = old_release("0.1.3")
        if old is None:
            self.skipTest("0.1.3 release not available")
        old_core = json.loads((REPO / "releases" / "vmodel-0.1.3.json").read_text(encoding="utf-8"))["core_hash"]
        sb = Sandbox(plugin=old)
        try:
            s = fail_g5(sb)
            sb.add_defect(s["failed"], "G5", related=["REQ-002", *s["failing"]], status="fixed")
            s["wf"].write_text(s["good"], encoding="utf-8")
            sb.regate_g4()
            passed = sb.gate("G5")[1]
            self.assertEqual(passed["status"], "PASSED")
            ledger = sb.root / ".vmodel/state/ledger.jsonl"
            old_bytes = ledger.read_bytes()
            old_records = [json.loads(ln)["record"] for ln in old_bytes.decode("utf-8").splitlines()]
            evidence = sorted({e["path"] for r in old_records for e in r.get("evidence") or []})
            self.assertTrue(evidence)
            ev_bytes = {p: (sb.root / p).read_bytes() for p in evidence}

            # switch to the new core: blocked until the user re-pins in a terminal
            sb.plugin, sb.entry = PLUGIN, PLUGIN / "validator" / "vmodel.py"
            self.assertFalse(sb.status()["validator"]["ok"])
            self.assertIn(b"re-pinned", sb.run_tty("lock", "--accept-current", "--reason", "upgrade to new core"))

            code, out = sb.vm("audit")
            self.assertEqual(code, 0, out)
            for p in evidence:
                code, out = sb.vm("verify-evidence", str(sb.root / p))
                self.assertEqual(code, 0, out)
            gates = {g["gate"]: g for g in sb.status()["work_items"][0]["gates"]}
            for g in GATES:
                self.assertEqual(gates[g]["status"], "STALE", g)
                self.assertIn("validator core changed since this PASS", gates[g]["notes"])
            d = sb.status()["work_items"][0]["defects"][0]
            self.assertEqual((d["verified_by"], d.get("closure_state"), d.get("closure_gate_status")),
                             (passed["record_id"], "VERIFIED", "STALE"))

            # re-verification with the new core: new records carry the new version, old ones are untouched
            for g in GATES:
                self.assertEqual(sb.gate(g)[1]["status"], "PASSED", g)
            new_bytes = ledger.read_bytes()
            self.assertTrue(new_bytes.startswith(old_bytes))
            for r in old_records:
                if r.get("type") == "gate":
                    self.assertEqual((r["validator"]["version"], r["validator"]["core_hash"]), ("0.1.3", old_core))
            added = [json.loads(ln)["record"] for ln in new_bytes[len(old_bytes):].decode("utf-8").splitlines()]
            self.assertEqual([r["type"] for r in added], ["lock", *["gate"] * 5])
            for r in added[1:]:
                self.assertEqual(r["validator"]["version"], VERSION)
                self.assertNotEqual(r["validator"]["core_hash"], old_core)
            self.assertEqual({p: (sb.root / p).read_bytes() for p in evidence}, ev_bytes)
            d = sb.status()["work_items"][0]["defects"][0]
            self.assertEqual((d["verified_by"], d.get("closure_state")), (passed["record_id"], "CLOSED"))
            self.assertEqual(sb.vm("audit")[0], 0)
        finally:
            sb.cleanup()


if __name__ == "__main__":
    unittest.main()

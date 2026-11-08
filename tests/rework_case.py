"""Shared base for the 0.1.4 defect regression tests: a work item whose G5 just FAILED (helpers.fail_g5)."""
from __future__ import annotations

import json
import unittest

from helpers import Sandbox, fail_g5, has_pytest


@unittest.skipUnless(has_pytest(), "pytest not installed")
class FailedG5Case(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox()
        self.s = fail_g5(self.sb)
        self.failed, self.failing = self.s["failed"], self.s["failing"]

    def tearDown(self):
        self.sb.cleanup()

    # ---------------------------------------------------------- views
    def wi(self, wi: str = "WI-001") -> dict:
        return [w for w in self.sb.status()["work_items"] if w["id"] == wi][0]

    def defect(self, did: str = "DEFECT-001") -> dict:
        return [d for d in self.wi()["defects"] if d["id"] == did][0]

    def gates(self) -> dict:
        return {g["gate"]: g["status"] for g in self.wi()["gates"]}

    def status_text(self) -> str:
        code, text = self.sb.vm("status", "WI-001")
        return text

    def defect_line(self, did: str = "DEFECT-001") -> str:
        lines = [ln.strip() for ln in self.status_text().splitlines() if ln.strip().startswith(did)]
        self.assertEqual(len(lines), 1, self.status_text())
        return lines[0]

    def report(self) -> str:
        code, out = self.sb.vm("report", "WI-001")
        self.assertEqual(code, 0, out)
        return (self.sb.root / ".vmodel/reports/WI-001.md").read_text(encoding="utf-8")

    def ledger_records(self) -> list[dict]:
        text = (self.sb.root / ".vmodel/state/ledger.jsonl").read_text(encoding="utf-8")
        return [json.loads(ln)["record"] for ln in text.splitlines() if ln.strip()]

    # ---------------------------------------------------------- edits
    def set_defect(self, did: str = "DEFECT-001", **fields) -> None:
        doc = self.sb.load("defects.json")
        [d for d in doc["defects"] if d["id"] == did][0].update(fields)
        self.sb.save("defects.json", doc)

    def gate_g4(self) -> str:
        """Fresh G4 review and evaluation; returns the PASSED record id."""
        self.sb.review("G4")
        res = self.sb.gate("G4")[1]
        self.assertEqual(res["status"], "PASSED", res)
        return res["record_id"]

    def close_defect(self) -> dict:
        """Documented rework order: DEFECT (fixed, all failing tests linked) with the fix, G4 re-review, G5 PASS."""
        self.sb.add_defect(self.failed, "G5", related=["REQ-002", *self.failing], status="fixed")
        self.s["wf"].write_text(self.s["good"], encoding="utf-8")
        self.gate_g4()
        res = self.sb.gate("G5")[1]
        self.assertEqual(res["status"], "PASSED", res)
        return res

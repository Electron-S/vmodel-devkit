"""Defects found by the real Claude Code E2E runs of the final verification (2026-11-10, build 589c779).

RED target: git archive 589c779 plugins/vmodel.
- E2E-A: the session first designed IF-001 (provider summarize, consumer the CLI main) with both components' units in
  one module. Since review 6 M1 the tracer records the provider's *entry* (outermost provider-file function), so inside
  that one file `main -> summarize` was recorded as `main` and G6 said "the provider (summarize) never ran": a false
  BLOCKED (e8a5a7e passed it). When the provider file is also a consumer file, the started function decides.
- E2E-B: the report's per-gate check heading said "G6 — PASSED" for an N/A evaluation (REQ-G6-17).
"""
from __future__ import annotations

import json
import unittest

from g6_base import RED, SINGLE_ENDPOINTS, SandboxClass, ledger_record, replace_function
from helpers import SINGLE

REPORT_WITH_PARSE = '''"""Score parsing and summary report in one module (DESIGN-001 parse, DESIGN-002/003 report)."""
import json
import sys


def parse(text: str) -> list[dict]:
    if not isinstance(text, str):
        raise TypeError("text must be str")
    records = []
    for no, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        name, sep, score = line.partition(",")
        if not sep or not name.strip():
            raise ValueError(f"line {no}: expected 'name,score'")
        try:
            value = int(score)
        except ValueError:
            raise ValueError(f"line {no}: score must be an integer") from None
        records.append({"name": name.strip(), "score": value})
    return records


def summarize(text: str) -> dict:
    records = parse(text)
    if not records:
        return {"count": 0, "total": 0, "top": None}
    top = max(records, key=lambda r: (r["score"], r["name"]))
    return {"count": len(records), "total": sum(r["score"] for r in records), "top": top["name"]}


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args:
        with open(args[0], encoding="utf-8") as fh:
            text = fh.read()
    else:
        text = sys.stdin.read()
    print(json.dumps(summarize(text), ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''


class E2ESameFileRed(SandboxClass):
    """pipeline, but DESIGN-001 (parse, ARCH-001) lives in src/pipeline/report.py with the report (ARCH-002)."""
    upto = "G1"

    @classmethod
    def build(cls, sb):
        super().build(sb)
        for g in ("G2", "G3"):
            sb.prepare(g)
            if g == "G3":
                design = sb.load("design.json")
                for u in design["units"]:
                    if u["id"] == "DESIGN-001":
                        u["module"] = "src/pipeline/report.py"
                sb.save("design.json", design)
            sb.review(g)
            res = sb.gate(g)[1]
            assert res["status"] == "PASSED", json.dumps(res, ensure_ascii=False)[:3000]
        sb.prepare("G4")
        (sb.root / "src/pipeline/parser.py").unlink()
        (sb.root / "src/pipeline/report.py").write_text(REPORT_WITH_PARSE, encoding="utf-8")
        up = sb.root / "tests/unit/test_parser.py"
        up.write_text(up.read_text(encoding="utf-8").replace("from pipeline.parser import", "from pipeline.report import"),
                      encoding="utf-8")
        sb.review("G4")
        for g in ("G4", "G5"):
            res = sb.gate(g)[1]
            assert res["status"] == "PASSED", json.dumps(res, ensure_ascii=False)[:3000]

    def test_E2E_A_provider_and_consumer_in_one_module(self):
        res = self.g6()
        self.assertEqual(res["status"], "PASSED", f"{RED} parse runs inside summarize in the same module: {res}")
        rec = ledger_record(self.sb, res["record_id"])
        if1 = [i for i in rec["interfaces"] if i["id"] == "IF-001"][0]
        self.assertEqual(if1["covered_by"], ["TEST-010", "TEST-011"], if1)


class E2EReportHeadingRed(SandboxClass):
    """single (N/A path), G1-G5 PASSED with confirming reviews."""
    fixture = SINGLE
    split = False
    na_reviews = True

    def test_E2E_B_report_heading_says_na(self):
        res = self.g6()
        self.assertEqual((res["status"], res.get("applicability")), ("PASSED", "not_applicable"), res)
        code, out = self.sb.vm("report", "WI-001")
        report = (self.sb.root / ".vmodel" / "reports" / "WI-001.md").read_text(encoding="utf-8")
        heads = [ln for ln in report.splitlines() if ln.startswith("### G6")]
        self.assertTrue(heads, report[:2000])
        self.assertNotIn("PASSED (R", heads[0].split("—", 1)[-1].split("recorded")[0], f"{RED} {heads[0]}")
        self.assertIn("N/A", heads[0], f"{RED} {heads[0]}")


if __name__ == "__main__":
    unittest.main()

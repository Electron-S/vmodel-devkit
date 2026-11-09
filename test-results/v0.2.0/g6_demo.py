"""v0.2.0 G6 demonstration on a release copy (no model calls). Writes a readable transcript of real validator runs.

    python3 -I test-results/v0.2.0/g6_demo.py <plugin dir, e.g. dist/vmodel-0.2.0> <out.txt>

Scenarios (the harness fixtures, driven through the CLI exactly as the tests do; the harness plays user and verifier):
  A  pipeline: G1-G5, then G6 path A (static call path + runtime trace), evidence record and audit
  B  pipeline: TEST-012 through a subprocess, verifier declares the runtime path, G6 path B
  C  pipeline: consumer bug -> G6 FAILED -> DEFECT -> fix -> G6 PASSED, defect CLOSED
  D  single: N/A confirmed by the G2/G3 reviews
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PLUGIN = Path(sys.argv[1]).resolve()
OUT = Path(sys.argv[2]).resolve()
os.environ["VMODEL_TEST_PLUGIN"] = str(PLUGIN)
sys.path.insert(0, str(REPO / "tests"))
import g6_base  # noqa: E402
from helpers import PIPELINE, SINGLE, Sandbox  # noqa: E402

lines: list[str] = []


def log(text: str = "") -> None:
    lines.append(text)


def show(sb: Sandbox, *args: str) -> str:
    code, out = sb.vm(*args)
    log(f"$ vmodel {' '.join(args)}   (exit {code})")
    log(out.rstrip())
    log()
    return out


def record(sb: Sandbox, rid: str) -> dict:
    return g6_base.ledger_record(sb, rid)


def scenario_a() -> None:
    log("=" * 100 + "\nA. pipeline (2 components, IF-001 parser->report, IF-002 report->EXTERNAL), path A\n" + "=" * 100)
    sb = Sandbox(fixture=PIPELINE)
    try:
        sb.init()
        sb.new_wi("G6 demo", "score pipeline")
        sb.split_tests()
        log("config integration_test: " + json.dumps(sb.config()["integration_test"]))
        log("config unit_test.argv:   " + json.dumps(sb.config()["unit_test"]["argv"]))
        g6_base.advance(sb, "G5")
        show(sb, "status", "WI-001")
        out = show(sb, "gate", "WI-001", "G6")
        res = json.loads(sb.vm("gate", "WI-001", "G6", "--json")[1])  # second run: same result, new record
        rec = record(sb, res["record_id"])
        ev = json.loads((sb.root / res["evidence"][0]["path"]).read_text(encoding="utf-8"))
        log("evidence record (signed): " + json.dumps({k: ev[k] for k in (
            "kind", "command", "command_source", "exit_code", "junit_summary", "runtime_trace")}, ensure_ascii=False))
        log("evidence files: " + ", ".join(sorted(ev["files"])))
        log("ledger interfaces: " + json.dumps([{k: i[k] for k in ("id", "covered", "covered_by")}
                                                 | {"tests": {t: {x: v[x] for x in ("status", "path", "function")}
                                                              for t, v in i["tests"].items()}}
                                                 for i in rec["interfaces"]], ensure_ascii=False))
        log("executed_tests: " + json.dumps(rec["executed_tests"]))
        log()
        show(sb, "verify-evidence", str(sb.root / res["evidence"][0]["path"]))
        show(sb, "audit")
        show(sb, "trace", "WI-001")
        del out
    finally:
        sb.cleanup()


def scenario_b() -> None:
    log("=" * 100 + "\nB. pipeline, TEST-012 runs the CLI in a subprocess: runtime path declared at G4, proven at G6\n"
        + "=" * 100)
    sb = Sandbox(fixture=PIPELINE)
    try:
        sb.init()
        sb.new_wi("G6 demo B", "score pipeline")
        sb.split_tests()
        g6_base.advance(sb, "G3")
        sb.put_code()
        itest = sb.root / "tests/integration/test_pipeline.py"
        g6_base.replace_function(itest, "test_TEST_012_cli_main_reads_file", g6_base.SUBPROCESS_TEST_012)
        sb.review("G4")
        show(sb, "gate", "WI-001", "G4")
        show(sb, "wiring", "WI-001")
        entries = sb.interface_review_entries()
        for e in entries:
            if e["id"] == "IF-002":
                e["runtime_paths"] = [{"test": "TEST-012", "kind": "subprocess",
                                       "test_file_sha256": g6_base.file_sha256(itest),
                                       "entry": "python -m pipeline.report", "note": "demo verifier"}]
        sb.review("G4", interfaces=entries)
        show(sb, "gate", "WI-001", "G4")
        show(sb, "gate", "WI-001", "G5")
        res = json.loads(sb.vm("gate", "WI-001", "G6", "--json")[1])
        log(f"G6 {res['status']} {res['record_id']}")
        rec = record(sb, res["record_id"])
        i2 = [i for i in rec["interfaces"] if i["id"] == "IF-002"][0]
        log("IF-002: " + json.dumps({k: i2[k] for k in ("covered", "covered_by")} | {"TEST-012": i2["tests"]["TEST-012"]},
                                    ensure_ascii=False))
        log("runtime_trace: " + json.dumps({k: v for k, v in rec["runtime_trace"].items() if k != "tests"}))
        log()
    finally:
        sb.cleanup()


def scenario_c() -> None:
    log("=" * 100 + "\nC. integration failure -> DEFECT -> fix -> re-verification\n" + "=" * 100)
    sb = Sandbox(fixture=PIPELINE)
    try:
        sb.init()
        sb.new_wi("G6 demo C", "score pipeline")
        sb.split_tests()
        g6_base.advance(sb, "G5")
        rp = sb.root / "src/pipeline/report.py"
        good = rp.read_text(encoding="utf-8")
        rp.write_text(good.replace("    records = parse(text)\n",
                                   "    try:\n        records = parse(text)\n    except ValueError:\n"
                                   "        records = []\n"), encoding="utf-8")
        log("seeded: report.summarize swallows the parser's ValueError (IF-001 error contract); unit tests still pass")
        for g in ("G4", "G5"):
            if g == "G4":
                sb.review("G4")
            log(f"{g} {sb.gate(g)[1]['status']}")
        failed = json.loads(sb.vm("gate", "WI-001", "G6", "--json")[1])
        show(sb, "status", "WI-001")
        show(sb, "gate", "WI-001", "G6")
        sb.add_defect(failed["record_id"], "G6", phase="P4", related=["IF-001", "TEST-011"],
                      fix_scope=["src/pipeline/report.py"], status="fixed")
        rp.write_text(good, encoding="utf-8")
        log("DEFECT-001 (gate G6, P4) cites " + failed["record_id"] + "; fix restored the error propagation")
        for g in ("G4", "G5", "G6"):
            if g == "G4":
                sb.review("G4")
            log(f"{g} {sb.gate(g)[1]['status']}")
        show(sb, "status", "WI-001")
    finally:
        sb.cleanup()


def scenario_d() -> None:
    log("=" * 100 + "\nD. single component, no interface: G6 N/A only after the G2 and G3 reviews confirm it\n"
        + "=" * 100)
    sb = Sandbox(fixture=SINGLE)
    try:
        sb.init()
        sb.new_wi("G6 demo D", "mean")
        g6_base.advance(sb, "G5")
        log("G2/G3 reviews WITHOUT integration_applicability:")
        show(sb, "gate", "WI-001", "G6")
        for g in ("G2", "G3"):
            sb.review(g, extra=g6_base.applicability(g6_base.SINGLE_ENDPOINTS))
            log(f"{g} re-reviewed with integration_applicability: {sb.gate(g)[1]['status']}")
        show(sb, "gate", "WI-001", "G6")
        show(sb, "status", "WI-001")
    finally:
        sb.cleanup()


for fn in (scenario_a, scenario_b, scenario_c, scenario_d):
    fn()
OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"wrote {OUT}")

"""v0.3.0 G7 demonstration on a release copy (no model calls). Writes a readable transcript of real validator runs.

    python3 -I test-results/v0.3.0/g7_demo.py <plugin dir, e.g. dist/vmodel-0.3.0> <out.txt>

Scenarios (the harness fixtures driven through the CLI as the tests do; the harness plays user and verifier):
  A  gradecalc: G1-G6 (G6 N/A), G7 runs the CLI and HTTP API system tests -> PASSED, evidence, trace, COMPLETED
  B  gradecalc: CLI entry bug -> G7 FAILED -> DEFECT -> fix -> G4-G7 again -> PASSED, defect CLOSED
  C  gradecalc: no system_test configured -> G7 BLOCKED misconfigured, nothing executed
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
import g7_base  # noqa: E402
from helpers import Sandbox  # noqa: E402

lines: list[str] = []


def log(text: str = "") -> None:
    lines.append(text)


def show(sb: Sandbox, *args: str) -> str:
    code, out = sb.vm(*args)
    log(f"$ vmodel {' '.join(args)}   (exit {code})")
    log(out.rstrip())
    log()
    return out


def build(mode: str = "system") -> Sandbox:
    sb = Sandbox(fixture=g7_base.GRADECALC)
    sb.init()
    sb.new_wi("G7 demo", "점수 등급 CLI와 HTTP API")
    g7_base.set_test_commands(sb, mode)
    for g in g7_base.GATES7[:6]:
        sb.prepare(g)
        if g in ("G1", "G2", "G3", "G4"):
            sb.review(g, extra=g7_base.applicability(g7_base.GC_ENDPOINTS) if g in ("G2", "G3") else None)
        res = sb.gate(g)[1]
        assert res["status"] == "PASSED", res
    return sb


def scenario_a() -> None:
    log("=" * 100 + "\nA. gradecalc: CLI + HTTP API system tests (separate processes), G6 N/A\n" + "=" * 100)
    sb = build()
    try:
        log("config system_test: " + json.dumps(sb.config()["system_test"]))
        log("config unit_test.argv: " + json.dumps(sb.config()["unit_test"]["argv"]))
        show(sb, "status", "WI-001")
        show(sb, "gate", "WI-001", "G7")
        res = json.loads(sb.vm("gate", "WI-001", "G7", "--json")[1])  # second run: same result, new record
        rec = g7_base.ledger_record(sb, res["record_id"])
        ev = json.loads((sb.root / res["evidence"][0]["path"]).read_text(encoding="utf-8"))
        log("evidence record (signed): " + json.dumps({k: ev[k] for k in (
            "kind", "command_source", "command", "exit_code", "timed_out", "duration_s", "junit_summary", "files",
            "manifest_hash", "config_sha256", "system_test_sha256", "git", "validator")}, ensure_ascii=False, indent=1))
        log("ledger record executed_tests: " + json.dumps(rec["executed_tests"]))
        log("ledger record requirements_coverage: " + json.dumps(rec["requirements_coverage"], ensure_ascii=False))
        log("ledger record basis_records: " + json.dumps(rec["basis_records"]))
        show(sb, "verify-evidence", str(sb.root / res["evidence"][0]["path"]))
        show(sb, "trace", "WI-001")
        show(sb, "status", "WI-001")
        show(sb, "audit")
    finally:
        sb.cleanup()


def scenario_b() -> None:
    log("=" * 100 + "\nB. gradecalc: CLI entry bug -> G7 FAILED -> DEFECT -> fix -> G7 PASSED, defect CLOSED\n" + "=" * 100)
    sb = build()
    try:
        cli = sb.root / "src/gradecalc/cli.py"
        good = cli.read_text(encoding="utf-8")
        cli.write_text(good.replace(*g7_base.CLI_EXIT_BUG), encoding="utf-8")
        log("seeded: src/gradecalc/cli.py __main__ calls main() without SystemExit (exit code always 0); the unit "
            "tests call main() directly and still pass")
        for g in ("G4", "G5", "G6"):
            if g == "G4":
                sb.review("G4")
            log(f"{g}: {sb.gate(g)[1]['status']}")
        failed = json.loads(sb.vm("gate", "WI-001", "G7", "--json")[1])
        show(sb, "status", "WI-001")
        show(sb, "gate", "WI-001", "G7")  # refused: rework record missing
        cli.write_text(good, encoding="utf-8")
        sb.add_defect(failed["record_id"], "G7", related=["REQ-001", "REQ-003", "AC-001-3", "TEST-103", "TEST-106"],
                      fix_scope=["src/gradecalc/cli.py"], status="fixed",
                      root_cause="the CLI entry point ignored main()'s return value")
        log(f"DEFECT-001 cites {failed['record_id']}, fix restored, defects.json status fixed")
        for g in ("G4", "G5", "G6"):
            if g == "G4":
                sb.review("G4")
            log(f"{g}: {sb.gate(g)[1]['status']}")
        show(sb, "status", "WI-001")
        show(sb, "gate", "WI-001", "G7")
        show(sb, "status", "WI-001")
    finally:
        sb.cleanup()


def scenario_c() -> None:
    log("=" * 100 + "\nC. gradecalc without system_test: G7 BLOCKED misconfigured, nothing executed\n" + "=" * 100)
    sb = build("nosystem")
    try:
        show(sb, "status", "WI-001")
        show(sb, "gate", "WI-001", "G7")
        base = sb.root / ".vmodel/evidence/WI-001/G7"
        log(f"G7 evidence directories: {sorted(p.name for p in base.iterdir()) if base.is_dir() else []}")
    finally:
        sb.cleanup()


for fn in (scenario_a, scenario_b, scenario_c):
    fn()
OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"wrote {OUT}")

"""Judge a finished E2E sandbox with the release validator only (no model call).

    python3 scripts/e2e/e2e_verify.py --work <e2e work dir> --out <result.json>

Runs `vmodel status --json`, `audit`, `trace`, `report` and `verify-evidence` on every evidence record the signed
ledger lists, and summarises the G6 records (applicability, interface evidence levels), defects, the gate sequence,
guard denials in the transcript and the final report text of the session.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "plugins" / "vmodel" / "validator"))
sys.dont_write_bytecode = True
from vmodel_validator import VERSION  # noqa: E402

RELEASE = REPO / "dist" / f"vmodel-{VERSION}"


def vm(env: dict, cwd: Path, *args: str) -> tuple[int, str]:
    r = subprocess.run(["sh", str(RELEASE / "bin" / "vmodel"), *args], cwd=cwd, env={**os.environ, **env},
                       capture_output=True)
    return r.returncode, r.stdout.decode("utf-8", errors="replace") + r.stderr.decode("utf-8", errors="replace")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--project-name", default="한글 샘플 프로젝트")
    ap.add_argument("--transcript-dir", help="where the session transcripts are (default: --work)")
    ap.add_argument("--release", help="release copy to judge with (default: dist/vmodel-<source version>)")
    args = ap.parse_args()
    global RELEASE
    if args.release:
        RELEASE = Path(args.release)
    work = Path(args.work)
    proj = work / args.project_name
    env = {"VMODEL_HOME": str(work / "vmodel-home"), "VMODEL_GUARD_LOG": str(work / "guard-log.jsonl")}
    out: dict = {"release": str(RELEASE)}
    code, st = vm(env, proj, "status", "--json")
    status = json.loads(st) if code == 0 else {"raw": st[-2000:]}
    out["status_exit"] = code
    acode, audit = vm(env, proj, "audit")
    out["audit"] = {"exit": acode, "tail": audit.strip().splitlines()[-5:]}
    ledger = proj / ".vmodel" / "state" / "ledger.jsonl"
    records = [json.loads(x)["record"] for x in ledger.read_text("utf-8").splitlines() if x.strip()]
    out["gate_sequence"] = [f"{r.get('record_id')} {r.get('work_item')} {r.get('gate')} {r.get('status')}"
                            + (f" ({r.get('blocked_reason')})" if r.get("blocked_reason") else "")
                            + (f" applicability={r.get('applicability')}" if r.get("gate") == "G6" else "")
                            for r in records if r.get("type") == "gate"]
    out["reviews"] = [f"{r.get('record_id')} {r.get('gate')} {r.get('verdict')}" for r in records
                      if r.get("type") == "review"]
    ev = []
    for r in records:
        for e in r.get("evidence") or []:
            c, o = vm(env, proj, "verify-evidence", e["path"])
            ev.append({"record": r.get("record_id"), "gate": r.get("gate"), "path": e["path"], "exit": c,
                       "result": o.strip().splitlines()[-1] if o.strip() else ""})
    out["verify_evidence"] = ev
    g6 = []
    for r in records:
        if r.get("type") == "gate" and r.get("gate") == "G6":
            cov = [c for c in r.get("checks") or [] if c.get("id") == "G6.IF_COVERAGE"]
            g6.append({"record": r.get("record_id"), "status": r.get("status"), "applicability": r.get("applicability"),
                       "blocked_reason": r.get("blocked_reason"),
                       "if_coverage": {"status": cov[0].get("status"), "detail": cov[0].get("detail"),
                                       "items": (cov[0].get("items") or [])[:12]} if cov else None,
                       "interfaces": [{"id": i.get("id"), "verification": i.get("verification"),
                                       "covered_by": i.get("covered_by"),
                                       "tests": {t: {"status": v.get("status"), "path": v.get("path"),
                                                     "evidence_level": v.get("evidence_level"),
                                                     "reason": (v.get("evidence_reason") or "")[:300]}
                                                 for t, v in (i.get("tests") or {}).items()}}
                                      for i in r.get("interfaces") or []],
                       "executed_tests": r.get("executed_tests"), "failed_cases": r.get("failed_cases"),
                       "runtime_trace": {k: (r.get("runtime_trace") or {}).get(k)
                                         for k in ("active", "processes", "spawned_processes", "truncated",
                                                   "test_boundaries", "boundary_clock", "edges", "errors")}})
    out["g6_records"] = g6
    g7 = []  # 0.3.0: G7 system verification records and their signed evidence
    for r in records:
        if r.get("type") == "gate" and r.get("gate") == "G7":
            item = {"record": r.get("record_id"), "work_item": r.get("work_item"), "status": r.get("status"),
                    "blocked_reason": r.get("blocked_reason"),
                    "checks": [f"{c.get('id')} {c.get('status')}: {c.get('detail')}" for c in r.get("checks") or []],
                    "failed_check_items": {c.get("id"): (c.get("items") or [])[:10] for c in r.get("checks") or []
                                           if c.get("status") in ("fail", "blocked", "warn") and c.get("items")},
                    "executed_tests": r.get("executed_tests"), "executed_levels": r.get("executed_levels"),
                    "unmapped_cases": r.get("unmapped_cases"), "system_specs": r.get("system_specs"),
                    "requirements_coverage": r.get("requirements_coverage"),
                    "basis_records": r.get("basis_records"), "junit": r.get("junit"),
                    "failed_cases": r.get("failed_cases"), "manifest_hash": (r.get("manifest") or {}).get("hash"),
                    "validator": r.get("validator"), "evidence": []}
            for e in r.get("evidence") or []:
                p = proj / e["path"]
                try:
                    rec = json.loads(p.read_text("utf-8"))
                except (OSError, json.JSONDecodeError) as exc:
                    item["evidence"].append({"path": e["path"], "error": str(exc)})
                    continue
                item["evidence"].append({"path": e["path"], "sha256": e.get("sha256"),
                                         **{k: rec.get(k) for k in ("kind", "command_source", "command", "exit_code",
                                                                    "timed_out", "duration_s", "junit_summary",
                                                                    "manifest_hash", "config_sha256",
                                                                    "system_test_sha256", "git", "validator")},
                                         "files": {n: (v or {}).get("sha256") for n, v in (rec.get("files") or {}).items()},
                                         "signed": "sig" in rec})
            g7.append(item)
    out["g7_records"] = g7
    wis = status.get("work_items") or []
    out["work_items"] = [{"id": w["id"], "status": w["status"], "gate_summary": w.get("gate_summary"),
                          "gates": {g["gate"]: g.get("display_status") or g["status"] for g in w["gates"]},
                          "next_action": w.get("next_action"),
                          "defects": [{k: d.get(k) for k in ("id", "closure_state", "gate", "root_cause_phase",
                                                             "verified_by", "failing_tests")}
                                      for d in w.get("defects") or []]} for w in wis]
    for w in wis:
        d = proj / ".vmodel" / "work-items" / w["id"]
        for name in ("architecture.json", "tests.json", "defects.json"):
            f = d / name
            if f.is_file():
                doc = json.loads(f.read_text("utf-8"))
                if name == "architecture.json":
                    out.setdefault("architecture", {})[w["id"]] = {
                        "components": [c.get("id") for c in doc.get("components") or []],
                        "interfaces": [{k: i.get(k) for k in ("id", "provider", "consumers", "signature")}
                                       for i in doc.get("interfaces") or []]}
                elif name == "tests.json":
                    out.setdefault("tests", {})[w["id"]] = [(t.get("id"), t.get("level"), t.get("verifies"))
                                                            for t in doc.get("tests") or []]
                else:
                    out.setdefault("defects_file", {})[w["id"]] = doc.get("defects")
        for g in ("G2", "G3", "G4"):
            f = d / "reviews" / f"{g}.json"
            if f.is_file():
                rv = json.loads(f.read_text("utf-8"))
                out.setdefault("review_keys", {}).setdefault(w["id"], {})[g] = {
                    "verdict": rv.get("verdict"), "integration_applicability": rv.get("integration_applicability"),
                    "interfaces": rv.get("interfaces")}
        tcode, trace = vm(env, proj, "trace", w["id"])
        out.setdefault("trace", {})[w["id"]] = trace.strip().splitlines()[-25:]
        rcode, report = vm(env, proj, "report", w["id"])
        out.setdefault("report_g6_lines", {})[w["id"]] = [ln for ln in report.splitlines()
                                                         if "G6" in ln or "interface" in ln.lower()][:20]
    tr = sorted(Path(args.transcript_dir or work).glob("transcript-*.jsonl"))
    if tr:
        final, denials = {}, []
        for line in tr[-1].read_text("utf-8", errors="replace").splitlines():
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            if e.get("type") == "result":
                final = {k: e.get(k) for k in ("subtype", "total_cost_usd", "num_turns", "duration_ms", "result")}
            if e.get("type") == "user":
                for b in (e.get("message") or {}).get("content") or []:
                    if isinstance(b, dict) and b.get("type") == "tool_result" and b.get("is_error"):
                        c = b.get("content")
                        c = " ".join(x.get("text", "") for x in c if isinstance(x, dict)) if isinstance(c, list) else str(c)
                        if "vmodel guard" in c:
                            denials.append(c[:300])
        out["session"] = {k: v for k, v in final.items() if k != "result"}
        out["session_result_text"] = (final.get("result") or "")[-3000:]
        out["guard_denials"] = denials
    Path(args.out).write_text(json.dumps(out, indent=2, ensure_ascii=False), "utf-8")
    print(json.dumps({k: out.get(k) for k in ("gate_sequence", "work_items", "audit", "session")}, indent=1,
                     ensure_ascii=False)[:6000])
    return 0


if __name__ == "__main__":
    sys.exit(main())

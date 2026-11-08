"""Safety probes against the real rework-drill sandbox state (no model calls, every probe is reverted).

    python scripts/e2e/drill_safety.py --work <drill dir> --tag after-s1

Each probe tampers with the project the way an agent (or a careless person) could, asks the pinned release validator
what it now believes, then restores the exact bytes. The whole project tree digest and the ledger length are compared
before and after, so the real drill state is provably untouched. Results go to <work>/safety-<tag>.json.
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
sys.dont_write_bytecode = True
sys.path.insert(0, str(HERE))
from rework_drill import PROJECT_DIR, env_for, tree_digest  # noqa: E402

WI = "WI-001"


class Probe:
    def __init__(self, work: Path, release: Path):
        self.work, self.release = work, release
        self.proj = work / PROJECT_DIR
        self.env = env_for(work)
        self.ledger = self.proj / ".vmodel" / "state" / "ledger.jsonl"
        self.results: list[dict] = []

    def vm(self, *args: str, stdin: bytes | None = None) -> tuple[int, str]:
        r = subprocess.run(["sh", str(self.release / "bin" / "vmodel"), *args], cwd=self.proj,
                           env={**os.environ, **self.env}, capture_output=True, input=stdin)
        return r.returncode, r.stdout.decode("utf-8", "replace") + r.stderr.decode("utf-8", "replace")

    def gates(self) -> dict:
        code, out = self.vm("status", WI, "--json")
        try:
            st = json.loads(out)
        except json.JSONDecodeError:
            return {"_raw": out[-500:]}
        w = st["work_items"][0] if st.get("work_items") else {}
        return {"wi": w.get("status"), "ledger_ok": st["ledger"]["ok"], "ledger_error": st["ledger"]["error"],
                **{g["gate"]: g["status"] for g in w.get("gates", []) if g["gate"] in ("G1", "G2", "G3", "G4", "G5")}}

    def lines(self) -> int:
        return len([x for x in self.ledger.read_text("utf-8").splitlines() if x.strip()])

    def run(self, name: str, claim: str, fn) -> None:
        before_digest, before_lines, before_gates = tree_digest(self.proj), self.lines(), self.gates()
        saved: dict[Path, bytes | None] = {}

        def save(p: Path) -> None:
            if p not in saved:
                saved[p] = p.read_bytes() if p.exists() else None

        try:
            observed = fn(save)
        finally:
            for p, data in saved.items():
                if data is None:
                    if p.exists():
                        p.unlink()
                    d = p.parent
                    while d != self.proj and d.exists() and not any(d.iterdir()):
                        d.rmdir()
                        d = d.parent
                else:
                    p.write_bytes(data)
        after_digest, after_lines = tree_digest(self.proj), self.lines()
        res = {"probe": name, "claim": claim, "before": before_gates, **observed,
               "restored": after_digest == before_digest and after_lines == before_lines,
               "after": self.gates()}
        self.results.append(res)
        print(f"[{'ok' if observed.get('pass') else 'FAIL'}] {name}: {observed.get('summary', '')} "
              f"(restored={res['restored']})")


def probes(pr: Probe) -> None:
    proj = pr.proj
    wi_dir = proj / ".vmodel" / "work-items" / WI

    # S1: a failed G5 cannot be re-run into a PASS without a rework record
    def rerun_g5(save):
        n = pr.lines()
        code, out = pr.vm("gate", WI, "G5", "--json")
        res = json.loads(out)
        return {"pass": res["status"] == "BLOCKED" and not res["recorded"] and pr.lines() == n
                and any("rework record missing" in r for r in res["reasons"]),
                "summary": f"gate G5 -> {res['status']} recorded={res['recorded']}", "reasons": res["reasons"]}
    pr.run("S1-rerun-failed-G5", "G5 cannot be re-evaluated (let alone pass) while the failure has no DEFECT", rerun_g5)

    # S2: AI-written JSON is not evidence
    def fake_evidence(save):
        d = proj / ".vmodel" / "evidence" / WI / "G5" / "29991231T000000000000Z-unit-fake01"
        rec, junit = d / "record.json", d / "junit.xml"
        save(rec)
        save(junit)
        d.mkdir(parents=True)
        junit.write_text('<testsuites><testsuite tests="1"><testcase classname="t" name="test_TEST_999_ok"/>'
                         '</testsuite></testsuites>', "utf-8")
        rec.write_text(json.dumps({"schema": "vmodel.evidence/1", "work_item": WI, "gate": "G5", "kind": "unit_test",
                                   "exit_code": 0, "junit_summary": {"tests": 1, "passed": 1, "failures": 0},
                                   "sig": "0" * 64}), "utf-8")
        c1, o1 = pr.vm("verify-evidence", str(rec))
        c2, o2 = pr.vm("audit")
        g = pr.gates()
        return {"pass": c1 != 0 and "REJECTED" in o1 and c2 != 0 and "not referenced by the ledger" in o2
                and g["G5"] != "PASSED",
                "summary": f"verify-evidence exit {c1}, audit exit {c2}, G5 still {g['G5']}",
                "verify_evidence": o1.strip().splitlines()[-3:], "audit": o2.strip().splitlines()[-3:]}
    pr.run("S2-fake-evidence-json", "a hand-written evidence record + junit is rejected and changes no gate",
           fake_evidence)

    def fake_result_file(save):
        f = wi_dir / "g5-result.json"
        save(f)
        f.write_text(json.dumps({"gate": "G5", "status": "PASSED", "tests": 7, "failures": 0}), "utf-8")
        g = pr.gates()
        return {"pass": g["G5"] != "PASSED" and g["wi"] != "PARTIALLY_VERIFIED",
                "summary": f"G5 {g['G5']}, WI {g['wi']} (file ignored)"}
    pr.run("S2-fake-result-json", "a 'PASSED' result file written into the work item is not a gate decision",
           fake_result_file)

    # S2/S3: forged ledger records (no test execution -> no PASS)
    def forged_append(save):
        save(pr.ledger)
        last = json.loads(pr.ledger.read_text("utf-8").splitlines()[-1])
        forged = json.loads(json.dumps(last))
        forged["record"]["status"] = "PASSED"
        forged["seq"] = last.get("seq", 0) + 1 if isinstance(last.get("seq"), int) else last.get("seq")
        with pr.ledger.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(forged, ensure_ascii=False) + "\n")
        g = pr.gates()
        code, out = pr.vm("gate", WI, "G5", "--json")
        res = json.loads(out)
        return {"pass": not g["ledger_ok"] and g["G5"] != "PASSED" and res["status"] == "BLOCKED",
                "summary": f"ledger_ok={g['ledger_ok']} G5={g['G5']} gate->{res['status']}",
                "ledger_error": g["ledger_error"], "gate_reasons": res["reasons"][:2]}
    pr.run("S3-forged-PASS-appended", "an appended G5 PASSED record without a valid signature is detected",
           forged_append)

    def flipped_in_place(save):
        save(pr.ledger)
        rows = pr.ledger.read_text("utf-8").splitlines()
        idx = max(i for i, x in enumerate(rows) if '"gate": "G5"' in x or '"gate":"G5"' in x)
        row = json.loads(rows[idx])
        row["record"]["status"] = "PASSED"
        rows[idx] = json.dumps(row, ensure_ascii=False)
        pr.ledger.write_text("\n".join(rows) + "\n", "utf-8")
        g = pr.gates()
        return {"pass": not g["ledger_ok"] and g["G5"] != "PASSED",
                "summary": f"ledger_ok={g['ledger_ok']} G5={g['G5']}", "ledger_error": g["ledger_error"]}
    pr.run("S3-G5-FAILED-flipped-to-PASSED", "editing the signed FAILED record into PASSED is detected",
           flipped_in_place)

    def tail_truncated(save):
        save(pr.ledger)
        rows = pr.ledger.read_text("utf-8").splitlines()
        pr.ledger.write_text("\n".join(rows[:-1]) + "\n", "utf-8")
        g = pr.gates()
        return {"pass": not g["ledger_ok"], "summary": f"ledger_ok={g['ledger_ok']}", "ledger_error": g["ledger_error"]}
    pr.run("S3-ledger-tail-deleted", "deleting the last (FAILED) record is detected (signed head + external anchor)",
           tail_truncated)

    # S4/S5: freshness after code / test / config changes
    def changed(rel_glob: str, label: str):
        def fn(save):
            targets = sorted(p for p in proj.glob(rel_glob) if p.is_file())
            if not targets:
                return {"pass": False, "summary": f"no file matches {rel_glob}"}
            t = targets[0]
            save(t)
            t.write_bytes(t.read_bytes() + b"\n# drill probe\n" if t.suffix in (".py", ".toml") else t.read_bytes()
                          .replace(b'"timeout_s": 600', b'"timeout_s": 601'))
            code, out = pr.vm("status", WI, "--json")
            gates = {g["gate"]: g for g in json.loads(out)["work_items"][0]["gates"]}
            g4 = gates["G4"]
            ok = g4["status"] != "PASSED" and any(t.relative_to(proj).as_posix() in c
                                                  for c in g4.get("changed_files", []))
            return {"pass": ok, "summary": f"{label}: G4 {g4['status']}, changed={g4.get('changed_files', [])[:3]}",
                    "file": t.relative_to(proj).as_posix()}
        return fn
    pr.run("S4-source-change", "a source change invalidates the G4 PASS (STALE)", changed("src/**/*.py", "source"))
    pr.run("S5-test-change", "a test file change invalidates the G4 PASS (STALE)", changed("tests/test_*.py", "test"))
    pr.run("S5-build-config-change", "a pytest/build config change invalidates the G4 PASS",
           changed("pyproject.toml", "pyproject"))
    pr.run("S5-validator-config-change", "a validator config change invalidates the G4 PASS",
           changed(".vmodel/config.json", "config"))

    # S6: the guard hook refuses agent writes to validator-owned files
    def guard(save):
        def decide(tool, tool_input, agent_type=None):
            payload = {"session_id": "probe", "hook_event_name": "PreToolUse", "tool_name": tool,
                       "tool_input": tool_input, "cwd": str(proj)}
            if agent_type:
                payload["agent_type"] = agent_type
            code, out = pr.vm("hook", "guard", stdin=json.dumps(payload).encode("utf-8"))
            return "deny" if '"deny"' in out else ("allow" if code == 0 and not out.strip() else f"?{code}")
        cases = {
            "Write evidence": decide("Write", {"file_path": str(proj / ".vmodel/evidence/WI-001/G5/x/record.json")}),
            "Edit ledger": decide("Edit", {"file_path": ".vmodel/state/ledger.jsonl"}),
            "Bash redirect into ledger": decide("Bash", {"command": "echo {} >> .vmodel/state/ledger.jsonl"}),
            "Edit release validator core": decide("Edit", {"file_path": str(pr.release / "validator" /
                                                                            "vmodel_validator" / "gates.py")}),
            "Write G4 review as main session": decide("Write", {"file_path": str(wi_dir / "reviews" / "G4.json")}),
            "Bash review-submit as main session": decide("Bash", {"command": f"{pr.release}/bin/vmodel review-submit "
                                                                             f"{WI} G4"}),
            "Write source as main session (allowed)": decide("Write", {"file_path": str(proj / "src/x.py")}),
        }
        exp_allow = {"Write source as main session (allowed)"}
        ok = all((v == "allow") if k in exp_allow else (v == "deny") for k, v in cases.items())
        return {"pass": ok, "summary": json.dumps(cases, ensure_ascii=False)}
    pr.run("S6-guard-hook", "the guard hook denies agent writes to evidence/ledger/core/reviews", guard)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--tag", required=True)
    ap.add_argument("--release", default=str(REPO / "dist" / "vmodel-0.1.2"))
    args = ap.parse_args()
    pr = Probe(Path(args.work), Path(args.release))
    probes(pr)
    out = Path(args.work) / f"safety-{args.tag}.json"
    out.write_text(json.dumps(pr.results, indent=2, ensure_ascii=False), "utf-8")
    bad = [r["probe"] for r in pr.results if not (r.get("pass") and r["restored"])]
    print(f"{len(pr.results) - len(bad)}/{len(pr.results)} probes passed and restored; results: {out}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

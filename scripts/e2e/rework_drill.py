"""Real Claude Code rework drill: seeded defect -> G5 FAILED -> DEFECT -> fix -> re-verify (costs money: capped).

    python scripts/e2e/rework_drill.py setup  --work <new dir>                 # sandbox + sealed seeding plan
    python scripts/e2e/rework_drill.py probe  --work <dir>                     # haiku: does the pytest deny rule bite?
    python scripts/e2e/rework_drill.py run    --work <dir> --phase s1 --prompt-file p1.txt
    python scripts/e2e/rework_drill.py run    --work <dir> --phase s2 --prompt-file p2.txt
    python scripts/e2e/rework_drill.py inspect --work <dir> --tag <name>       # validator-side facts, no model calls

S1 develops the sample feature with one blind-seeded defect and stops at the first FAILED gate (agent-side pytest is
denied so that only the validator's G5 run executes tests). S2 is a fresh session that knows nothing about the seeding
and runs the DevKit rework loop. Every run uses the pinned release (--release, default dist/vmodel-0.1.2), an isolated
VMODEL_HOME, --setting-sources project,local and --no-session-persistence. Never --dangerously-skip-permissions.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(HERE))
import e2e_run  # noqa: E402
from claude_run import run_claude  # noqa: E402

PROJECT_DIR = "한글 드릴 프로젝트"
SAMPLE = REPO / "samples" / "scorestats"
DENY_AGENT_PYTEST = ["Bash(*pytest*)"]

SEEDING_PLAN = {
    "drill": "rework-drill-1",
    "feature": "nearest-rank percentile of a score list (scorestats)",
    "seeded_defect": {
        "phase": "P4",
        "unit": "the percentile function designed in P3 (name chosen by the session)",
        "fault": "0-based index computed as min(int(p*N/100), N-1) instead of ceil(p*N/100)-1",
        "correct": "rank r = ceil(p/100*N) (1-based) -> sorted_scores[r-1]",
        "manifests_when": "p*N/100 is an integer smaller than N, e.g. [15,20,35,40,50] p=40 -> 35 instead of 20; "
                          "p=20 -> 20 instead of 15; N=4 p=50 -> 3rd instead of 2nd value",
        "masked_when": "p*N/100 is not an integer, or p=100 (clamped), or N=1",
    },
    "expected_detection": {
        "gate": "G5",
        "status": "FAILED",
        "checks": ["G5.EXECUTION (pytest exit code 1)", "G5.RESULTS (failed test case)",
                   "G5.TEST_MAPPING (the TEST id of the failing case)"],
        "work_item_not": "PARTIALLY_VERIFIED",
        "alternative": "G4 review reject if the verifier spots the fault by reading (recorded as such, not G5)",
    },
    "expected_rework": {
        "root_cause_phase": "P4",
        "fix_scope": "the percentile module only; no test or spec change is needed",
        "tests_changed": False,
    },
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def env_for(work: Path) -> dict:
    return {"VMODEL_HOME": str(work / "vmodel-home"), "VMODEL_GUARD_LOG": str(work / "guard-log.jsonl")}


def vm(release: Path, env: dict, cwd: Path, *args: str) -> tuple[int, str]:
    r = subprocess.run(["sh", str(release / "bin" / "vmodel"), *args], cwd=cwd, env={**os.environ, **env},
                       capture_output=True)
    return r.returncode, r.stdout.decode("utf-8", errors="replace") + r.stderr.decode("utf-8", errors="replace")


def tree_digest(root: Path) -> str:
    """Content digest of the whole project tree (incl. .vmodel and .git) to prove a probe left nothing behind."""
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        if p.is_file() and not p.is_symlink() and p.relative_to(root).as_posix() != ".git/index":  # git stat cache
            h.update(p.relative_to(root).as_posix().encode("utf-8") + b"\0")
            h.update(hashlib.sha256(p.read_bytes()).digest())
    return "sha256:" + h.hexdigest()


def cmd_setup(args) -> int:
    work = Path(args.work)
    work.mkdir(parents=True, exist_ok=False)
    release = Path(args.release)
    plan = {**SEEDING_PLAN, "sealed_at": now(), "release": release.name}
    plan_bytes = json.dumps(plan, indent=2, ensure_ascii=False).encode("utf-8")
    (work / "drill-plan.json").write_bytes(plan_bytes)
    (work / "drill-plan.sha256").write_text("sha256:" + hashlib.sha256(plan_bytes).hexdigest() + "\n", "utf-8")
    proj = work / PROJECT_DIR
    shutil.copytree(SAMPLE, proj, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
    git = ["git", "-c", "user.name=vmodel-drill", "-c", "user.email=drill@example.invalid"]
    subprocess.run(git + ["init", "-q"], cwd=proj, check=True)
    subprocess.run(git + ["add", "-A"], cwd=proj, check=True)
    subprocess.run(git + ["commit", "-qm", "sample baseline"], cwd=proj, check=True)
    env = env_for(work)
    code, out = vm(release, env, proj, "install", "--project", str(proj), "--lint", "auto")
    (work / "install.log").write_text(out, "utf-8")
    if code != 0:
        print(out)
        return 1
    print(json.dumps({"work": str(work), "project": str(proj), "plan_sha256": (work / "drill-plan.sha256")
                      .read_text("utf-8").strip(), "install_exit": code}, indent=2, ensure_ascii=False))
    return 0


def cmd_probe(args) -> int:
    """Cheap haiku run: is an agent's pytest call denied by DENY_AGENT_PYTEST while ls/vmodel stay allowed?"""
    work = Path(args.work)
    d = work / "deny-probe"
    d.mkdir(parents=True, exist_ok=False)
    shutil.copytree(SAMPLE, d / "proj")
    prompt = ("This is a permission probe. Run exactly these Bash commands one at a time and report for each whether "
              "it ran or was denied: 1) ls  2) python3 -m pytest --version  3) cd . && PYTHONPATH=src python3 -m pytest "
              "-q  4) python3 -I -c \"import pytest\". Do not try alternatives.")
    summary = run_claude(prompt, d / "proj", plugin_dirs=[], model="haiku", budget_usd=0.3, env={},
                         transcript=work / "transcript-deny-probe.jsonl",
                         extra_args=["--allowedTools", "Bash(ls*)", "Bash(python3 *)", "Bash(cd *)",
                                     "--disallowedTools", *DENY_AGENT_PYTEST],
                         permission_args=["--permission-mode", "acceptEdits", "--permission-prompts", "none"],
                         timeout_s=600)
    rows = [{"command": t["input"].get("command"), "is_error": (t.get("result") or {}).get("is_error"),
             "result": ((t.get("result") or {}).get("content") or "")[:200]}
            for t in summary["tool_uses"] if t["name"] == "Bash"]
    out = {"rows": rows, "cost": summary["final"].get("total_cost_usd"), "exit": summary["exit_code"]}
    (work / "deny-probe.json").write_text(json.dumps(out, indent=2, ensure_ascii=False), "utf-8")
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


def _ledger_records(proj: Path) -> list[dict]:
    led = proj / ".vmodel" / "state" / "ledger.jsonl"
    return [json.loads(x)["record"] for x in led.read_text("utf-8").splitlines() if x.strip()] if led.exists() else []


def inspect(work: Path, release: Path, tag: str, summary: dict | None = None) -> dict:
    """Validator-side facts after a run, read from the signed ledger and evidence (no model calls, no new records)."""
    proj = work / PROJECT_DIR
    env = env_for(work)
    recs = _ledger_records(proj)
    gates = []
    for r in recs:
        if r.get("type") != "gate":
            continue
        g = {"record_id": r.get("record_id"), "gate": r.get("gate"), "status": r.get("status"),
             "at": r.get("evaluated_at"), "manifest": (r.get("manifest") or {}).get("hash"),
             "core": (r.get("validator") or {}).get("core_hash"), "failure_signature": r.get("failure_signature"),
             "checks": [{"id": c["id"], "status": c["status"], "detail": c["detail"][:200],
                         "items": (c.get("items") or [])[:6]} for c in r.get("checks") or [] if c["status"] != "pass"]}
        if r.get("gate") == "G5":
            g["executed_tests"] = r.get("executed_tests")
            g["junit"] = r.get("junit")
            g["failed_cases"] = r.get("failed_cases")
            g["test_files"] = r.get("test_files")
            ev = []
            for e in r.get("evidence") or []:
                rec = json.loads((proj / e["path"]).read_text("utf-8"))
                ev.append({"path": e["path"], "exit_code": rec.get("exit_code"), "command": rec.get("command"),
                           "started_at": rec.get("started_at"), "junit_summary": rec.get("junit_summary"),
                           "stdout_sha256": rec["files"]["stdout.bin"]["sha256"], "git": rec.get("git"),
                           "manifest_hash": rec.get("manifest_hash")})
            g["evidence"] = ev
        gates.append(g)
    reviews = [{k: r.get(k) for k in ("record_id", "gate", "verdict", "target_hash", "review_sha256")}
               for r in recs if r.get("type") == "review"]
    defects_p = proj / ".vmodel" / "work-items" / "WI-001" / "defects.json"
    defects = json.loads(defects_p.read_text("utf-8")) if defects_p.exists() else None
    diff = subprocess.run(["git", "-c", "core.quotepath=off", "status", "--porcelain"], cwd=proj,
                          capture_output=True).stdout.decode("utf-8", "replace").splitlines()
    out = {
        "tag": tag, "at": now(), "release": release.name,
        "status": vm(release, env, proj, "status")[1],
        "audit": vm(release, env, proj, "audit"),
        "trace": vm(release, env, proj, "trace", "WI-001")[1][-3000:],
        "gate_records": gates, "review_records": reviews, "defects": defects, "git_status": diff,
        "guard_log": (work / "guard-log.jsonl").read_text("utf-8").splitlines()[-40:]
        if (work / "guard-log.jsonl").exists() else [],
    }
    if summary is not None:
        bash = [t for t in summary["tool_uses"] if t["name"] == "Bash"]
        out["agent_pytest_attempts"] = [
            {"command": t["input"].get("command", "")[:200], "by_subagent": bool(t.get("parent")),
             "is_error": (t.get("result") or {}).get("is_error"),
             "result": ((t.get("result") or {}).get("content") or "")[:200]}
            for t in bash if "pytest" in t["input"].get("command", "")]
        out["final"] = {k: summary["final"].get(k) for k in ("subtype", "is_error", "total_cost_usd", "num_turns",
                                                              "duration_ms")}
        out["result_text"] = summary["final"].get("result")
    (work / f"inspect-{tag}.json").write_text(json.dumps(out, indent=2, ensure_ascii=False), "utf-8")
    return out


def cmd_run(args) -> int:
    work = Path(args.work)
    release = Path(args.release)
    proj = work / PROJECT_DIR
    env = env_for(work)
    prompt = Path(args.prompt_file).read_text("utf-8")
    vm_path = str(release / "bin" / "vmodel")
    allowed = ["Bash(vmodel *)", f"Bash({vm_path} *)", f'Bash("{vm_path}" *)', "Bash(*/bin/vmodel *)",
               'Bash(*/bin/vmodel" *)', "Bash(python3 -m pytest*)", "Bash(python -m pytest*)", "Bash(pytest*)",
               "Bash(ls*)", "Bash(cat *)", "Bash(head *)", "Bash(tail *)", "Bash(wc *)", "Bash(grep *)",
               "Bash(git status*)", "Bash(git diff*)", "Bash(git log*)", "Bash(ruff *)", "Bash(python3 -c *)"]
    extra = ["--allowedTools", *allowed]
    if args.phase == "s1":
        extra += ["--disallowedTools", *DENY_AGENT_PYTEST]
    (work / f"prompt-{args.phase}.txt").write_text(prompt, "utf-8")
    pre_digest = tree_digest(release)
    summary = run_claude(prompt, proj, plugin_dirs=[release], model=args.model, budget_usd=args.budget, env=env,
                         transcript=work / f"transcript-{args.phase}.jsonl", extra_args=extra, timeout_s=5400,
                         permission_args=["--permission-mode", args.permission_mode, "--permission-prompts", "none"])
    e2e_run.RELEASE = release
    m = e2e_run.measure(work, proj, env, summary, args.phase)
    facts = inspect(work, release, args.phase, summary)
    facts["release_tree_unchanged"] = tree_digest(release) == pre_digest
    (work / f"inspect-{args.phase}.json").write_text(json.dumps(facts, indent=2, ensure_ascii=False), "utf-8")
    brief = {"phase": args.phase, "skills": m["skill_invocations"], "subagents": m["subagents"],
             "gate_records": [f"{g['record_id']} {g['gate']} {g['status']}" for g in facts["gate_records"]],
             "reviews": [f"{r['record_id']} {r['gate']} {r['verdict']}" for r in facts["review_records"]],
             "work_items": m["work_items"], "guard_denials": m["guard_denials"],
             "agent_pytest_attempts": facts.get("agent_pytest_attempts"), "audit": m["audit"],
             "release_tree_unchanged": facts["release_tree_unchanged"], "final": facts.get("final"),
             "result_tail": (facts.get("result_text") or "")[-1500:]}
    print(json.dumps(brief, indent=2, ensure_ascii=False))
    return 0


MISSED_REVIEW_SUMMARY = (
    "[DRILL FAULT INJECTION - written by the rework-drill harness, not by an AI reviewer] Approval injected by the "
    "test orchestrator to simulate a G4 review that missed a defect, so that the G5 path can be exercised. In the "
    "source drill the real vmodel:verifier rejected this code. Do not treat this file as an AI review.")


def cmd_fork(args) -> int:
    """G5-path sandbox from a finished S1: same real artifacts and code, real G1-G3 reviews, injected G4 approval.

    Only the G4 approval is synthetic (marked in its summary, which the ledger hashes). Everything the validator
    then does - running pytest, recording G5 FAILED and its evidence - is real.
    """
    src_work, work, release = Path(args.source), Path(args.work), Path(args.release)
    if cmd_setup(argparse.Namespace(work=str(work), release=str(release))) != 0:
        return 1
    plan = json.loads((work / "drill-plan.json").read_text("utf-8"))
    plan["fork"] = {"from": str(src_work), "at": now(), "synthetic": ["reviews/G4.json (approve, harness-written)"],
                    "copied": ["WI-001 artifacts", "reviews G1-G3 (real vmodel:verifier output)",
                               "src/scorestats/percentile.py", "tests/test_percentile.py"]}
    (work / "drill-plan.json").write_text(json.dumps(plan, indent=2, ensure_ascii=False), "utf-8")
    src_proj, proj = src_work / PROJECT_DIR, work / PROJECT_DIR
    env = env_for(work)
    wi_src, wi_dst = src_proj / ".vmodel/work-items/WI-001", proj / ".vmodel/work-items/WI-001"
    (wi_dst / "reviews").mkdir(parents=True)
    for name in ("workitem.json", "requirements.json", "architecture.json", "design.json", "tests.json"):
        shutil.copy2(wi_src / name, wi_dst / name)
    for rel in ("src/scorestats/percentile.py", "tests/test_percentile.py"):
        shutil.copy2(src_proj / rel, proj / rel)
    log = []

    def step(*a: str) -> dict:
        code, out = vm(release, env, proj, *a)
        log.append({"cmd": " ".join(a), "exit": code, "out": out[-1500:]})
        try:
            return json.loads(out)
        except json.JSONDecodeError:
            return {"exit": code, "out": out}

    for g in ("G1", "G2", "G3"):
        shutil.copy2(wi_src / "reviews" / f"{g}.json", wi_dst / "reviews" / f"{g}.json")
        step("review-submit", "WI-001", g)
        res = step("gate", "WI-001", g, "--json")
        if res.get("status") != "PASSED":
            print(json.dumps(log, indent=2, ensure_ascii=False))
            return 1
    target = step("hash", "WI-001", "G4", "--json")["target_hash"]
    review = {"gate": "G4", "work_item": "WI-001", "reviewer": "vmodel:verifier", "target_hash": target,
              "reviewed_at": now(), "verdict": "approve", "summary": MISSED_REVIEW_SUMMARY,
              "checklist": [{"item": "drill fault injection", "result": "na", "note": "no review was performed"}],
              "findings": []}
    (wi_dst / "reviews" / "G4.json").write_text(json.dumps(review, indent=2, ensure_ascii=False), "utf-8")
    step("review-submit", "WI-001", "G4")
    g4 = step("gate", "WI-001", "G4", "--json")
    g5 = step("gate", "WI-001", "G5", "--json")
    (work / "fork.log.json").write_text(json.dumps(log, indent=2, ensure_ascii=False), "utf-8")
    print(json.dumps({"G4": g4.get("status"), "G5": g5.get("status"), "G5_record": g5.get("record_id"),
                      "G5_checks": [(c["id"], c["status"], c["detail"][:160]) for c in g5.get("checks") or []],
                      "G5_evidence": g5.get("evidence")}, indent=2, ensure_ascii=False))
    return 0


def cmd_inspect(args) -> int:
    out = inspect(Path(args.work), Path(args.release), args.tag)
    print(json.dumps({k: out[k] for k in ("status", "audit", "gate_records", "defects", "git_status")}, indent=2,
                     ensure_ascii=False)[:20000])
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("setup", "probe", "run", "inspect", "fork"):
        p = sub.add_parser(name)
        p.add_argument("--work", required=True)
        p.add_argument("--release", default=str(REPO / "dist" / "vmodel-0.1.2"))
        if name == "fork":
            p.add_argument("--source", required=True, help="finished S1 drill directory")
        if name == "run":
            p.add_argument("--phase", required=True, choices=["s1", "s2", "s3"])
            p.add_argument("--prompt-file", required=True)
            p.add_argument("--model", default="sonnet")
            p.add_argument("--budget", type=float, default=4.0)
            p.add_argument("--permission-mode", default="auto", choices=["acceptEdits", "auto"])
        if name == "inspect":
            p.add_argument("--tag", required=True)
    args = ap.parse_args()
    return {"setup": cmd_setup, "probe": cmd_probe, "run": cmd_run, "inspect": cmd_inspect,
            "fork": cmd_fork}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())

"""Real Claude Code G6 failure drill: G1-G5 PASSED -> G6 FAILED -> DEFECT -> fix -> G6 PASSED -> CLOSED (costs money).

    python3 scripts/e2e/g6_drill.py setup      --work <new dir>                  # sandbox + sealed plan, no model call
    python3 scripts/e2e/g6_drill.py run        --work <dir> --phase s1 --prompt-file p1.txt
    python3 scripts/e2e/g6_drill.py seed-check --work <dir> --seed <seed.json>   # on a copy: unit pass, integration fail
    python3 scripts/e2e/g6_drill.py seed-apply --work <dir> --seed <seed.json>   # same seed, into the sandbox
    python3 scripts/e2e/g6_drill.py run        --work <dir> --phase s2 --prompt-file p2.txt
    python3 scripts/e2e/g6_drill.py verify     --work <dir> --tag <name>         # validator-side facts, no model call

S1 (a fresh session) develops the sample feature through P1-P4 (G1-G3 reviewed by the real verifier, code and tests
written) and stops before the G4 review. The harness then seeds one interface contract defect into the implementation
(the spec and the tests stay as S1 wrote them), after checking on a copy that the configured unit command still passes
and the integration command fails. S2 is another fresh session that knows nothing about the seeding: it continues the
work item (G4 review by the real verifier, G5, G6) and handles whatever the validator reports. The agent's own pytest
calls are denied in S2 (DECISIONS D26: test execution is the validator's G5/G6 job). Plans, seeds, prompts and
transcripts live in <work>-sealed/, outside the folder the sessions work in. Every run uses the pinned release, an
isolated VMODEL_HOME, --setting-sources project,local, --no-session-persistence and never
--dangerously-skip-permissions.
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
SAMPLE = REPO / "samples" / "orderdesk"
DENY_AGENT_PYTEST = ["Bash(*pytest*)"]

PLAN = {
    "drill": "g6-failure-drill-1",
    "goal": "G1-G5 PASSED -> G6 FAILED -> DEFECT (failing TEST ids linked) -> root cause -> minimal fix -> "
            "re-verification -> G6 PASSED -> DEFECT CLOSED -> audit OK, all from validator records",
    "sample": "samples/orderdesk (empty package; the feature request names a provider (pricing) and a consumer "
              "(receipt) module and asks for consumer unit tests with an injected fake pricer)",
    "seeding": {
        "when": "after S1 (P1-P4: requirements, architecture with the interface, design, test specs, code and tests "
                "written; G1-G3 PASSED), before any G4 review",
        "where": "implementation only (src/), one interface contract mismatch between consumer and provider, at most "
                 "3 changed lines, no comments or markers; tests, specs and reviews untouched",
        "acceptance": ["on a copy of the sandbox, the configured unit_test command exits 0",
                       "on the same copy, the configured integration_test command fails with at least one failing "
                       "test whose name carries a TEST id of an integration spec, through the real connection",
                       "the seed file and its check result are sealed (sha256) before S2"],
        "candidate_classes": ["consumer passes a differently shaped argument to the provider than the interface "
                              "contract says (a fake pricer in the consumer unit tests does not look at it)",
                              "keyword/parameter name mismatch between the consumer's call and the provider",
                              "consumer reads a field of the provider result under another name than the provider "
                              "returns (only if the consumer unit tests' fake also supplies that name)"],
        "chosen": "decided after S1 from the real code (seed.json, sealed separately)",
    },
    "expected": {
        "G4": "real vmodel:verifier review of the seeded code; if it finds the defect, G4 FAILED is recorded as is "
              "and the drill reports that the G6 FAILED path was not observed",
        "G5": "PASSED (unit tests use the fake pricer)",
        "G6": "FAILED from the integration test run (EXECUTION/RESULTS/TEST_MAPPING), not BLOCKED",
        "rework": "S2 on its own: status -> failing TEST ids -> DEFECT gate G6 with found_in_records and the failing "
                  "TEST ids -> root cause P4 (or P2/P3 if it argues so) -> fix in src -> G4 re-review -> G5 -> G6 "
                  "PASSED -> defect CLOSED (verified by the G6 record) -> audit OK",
    },
    "rules": ["no harness-written review", "no change to validator records or evidence", "no test expectation change by "
              "the harness", "BLOCKED is never turned into FAILED", "the sessions get no hint of the seed"],
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_bytes(b: bytes) -> str:
    return "sha256:" + hashlib.sha256(b).hexdigest()


def sealed_dir(work: Path) -> Path:
    return work.parent / (work.name + "-sealed")


def env_for(work: Path) -> dict:
    return {"VMODEL_HOME": str(work / "vmodel-home"), "VMODEL_GUARD_LOG": str(work / "guard-log.jsonl")}


def vm(release: Path, env: dict, cwd: Path, *args: str) -> tuple[int, str]:
    r = subprocess.run(["sh", str(release / "bin" / "vmodel"), *args], cwd=cwd, env={**os.environ, **env},
                       capture_output=True)
    return r.returncode, r.stdout.decode("utf-8", errors="replace") + r.stderr.decode("utf-8", errors="replace")


def tree_digest(root: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        if p.is_file() and not p.is_symlink() and "__pycache__" not in p.parts:
            h.update(p.relative_to(root).as_posix().encode("utf-8") + b"\0")
            h.update(hashlib.sha256(p.read_bytes()).digest())
    return "sha256:" + h.hexdigest()


def cmd_setup(args) -> int:
    work, release = Path(args.work), Path(args.release)
    sealed = sealed_dir(work)
    work.mkdir(parents=True, exist_ok=False)
    sealed.mkdir(parents=True, exist_ok=False)
    plan = {**PLAN, "sealed_at": now(), "release": release.name,
            "release_core": json.loads((release / "RELEASE_MANIFEST.json").read_text("utf-8")).get("core_hash")}
    data = json.dumps(plan, indent=2, ensure_ascii=False).encode("utf-8")
    (sealed / "drill-plan.json").write_bytes(data)
    (sealed / "drill-plan.sha256").write_text(sha256_bytes(data) + "\n", "utf-8")
    proj = work / PROJECT_DIR
    shutil.copytree(SAMPLE, proj, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
    git = ["git", "-c", "user.name=vmodel-drill", "-c", "user.email=drill@example.invalid"]
    subprocess.run(git + ["init", "-q"], cwd=proj, check=True)
    subprocess.run(git + ["add", "-A"], cwd=proj, check=True)
    subprocess.run(git + ["commit", "-qm", "sample baseline"], cwd=proj, check=True)
    env = env_for(work)
    code, out = vm(release, env, proj, "install", "--project", str(proj), "--lint", "auto")
    (sealed / "install.log").write_text(out, "utf-8")
    if code != 0:
        print(out)
        return 1
    print((proj / ".vmodel" / "config.json").read_text("utf-8"))
    print(vm(release, env, proj, "status")[1])
    print(json.dumps({"work": str(work), "sealed": str(sealed), "project": str(proj),
                      "plan_sha256": (sealed / "drill-plan.sha256").read_text("utf-8").strip()}, indent=2,
                     ensure_ascii=False))
    return 0


def cmd_run(args) -> int:
    work, release = Path(args.work), Path(args.release)
    sealed = sealed_dir(work)
    proj = work / PROJECT_DIR
    env = env_for(work)
    prompt = Path(args.prompt_file).read_text("utf-8")
    vm_path = str(release / "bin" / "vmodel")
    allowed = ["Bash(vmodel *)", f"Bash({vm_path} *)", f'Bash("{vm_path}" *)', "Bash(*/bin/vmodel *)",
               'Bash(*/bin/vmodel" *)', "Bash(python3 -m pytest*)", "Bash(python -m pytest*)", "Bash(pytest*)",
               "Bash(ls*)", "Bash(cat *)", "Bash(head *)", "Bash(tail *)", "Bash(wc *)", "Bash(grep *)",
               "Bash(git status*)", "Bash(git diff*)", "Bash(git log*)", "Bash(ruff *)", "Bash(python3 -c *)"]
    extra = ["--allowedTools", *allowed]
    if args.phase == "s2":
        extra += ["--disallowedTools", *DENY_AGENT_PYTEST]
    (sealed / f"prompt-{args.phase}.txt").write_text(prompt, "utf-8")
    pre_release = tree_digest(release)
    summary = run_claude(prompt, proj, plugin_dirs=[release], model=args.model, budget_usd=args.budget, env=env,
                         transcript=sealed / f"transcript-{args.phase}.jsonl", extra_args=extra, timeout_s=5400,
                         permission_args=["--permission-mode", "auto", "--permission-prompts", "none"])
    e2e_run.RELEASE = release
    m = e2e_run.measure(sealed, proj, env, summary, args.phase)
    brief = {"phase": args.phase, "skills": m["skill_invocations"], "subagents": m["subagents"],
             "gate_records": [f"{r['record_id']} {r['gate']} {r['status']}" for r in m["gate_records"]],
             "reviews": [f"{r['record_id']} {r['gate']} {r['verdict']}" for r in m["review_submissions"]],
             "work_items": m["work_items"], "guard_denials": m["guard_denials"], "audit": m["audit"],
             "release_tree_unchanged": tree_digest(release) == pre_release,
             "agent_pytest_attempts": [
                 {"command": (t["input"].get("command") or "")[:160], "by_subagent": bool(t.get("parent")),
                  "denied": (t.get("result") or {}).get("is_error")}
                 for t in summary["tool_uses"] if t["name"] == "Bash" and "pytest" in (t["input"].get("command") or "")],
             "outside_project_access": outside_access(summary, proj),
             "final": {k: summary["final"].get(k) for k in ("subtype", "is_error", "total_cost_usd", "num_turns",
                                                             "duration_ms")},
             "result_tail": (summary["final"].get("result") or "")[-2500:]}
    (sealed / f"brief-{args.phase}.json").write_text(json.dumps(brief, indent=2, ensure_ascii=False), "utf-8")
    print(json.dumps(brief, indent=2, ensure_ascii=False))
    return 0


def outside_access(summary: dict, proj: Path) -> list[dict]:
    """Tool calls that name the drill's work folder, its sealed folder or a parent path ('..') - the seed must stay
    out of the session's sight; the release (plugin) path and the session's own config are expected."""
    work = proj.parent
    hits = []
    for t in summary["tool_uses"]:
        text = json.dumps(t.get("input"), ensure_ascii=False)
        rest = text.replace(str(proj), "<PROJECT>")
        if "-sealed" in rest or str(work) in rest or "../" in rest or "..\\\\" in rest or rest.count('"..') > 0:
            hits.append({"tool": t["name"], "input": text[:300], "by_subagent": bool(t.get("parent"))})
    return hits


def load_seed(path: Path) -> tuple[dict, bytes]:
    data = path.read_bytes()
    seed = json.loads(data)
    for k in ("file", "old", "new", "class", "why_unit_tests_pass", "expected_integration_failure"):
        if k not in seed:
            raise SystemExit(f"seed.json needs {k!r}")
    return seed, data


def apply_seed(root: Path, seed: dict) -> tuple[str, str]:
    f = root / seed["file"]
    text = f.read_text("utf-8")
    if text.count(seed["old"]) != 1:
        raise SystemExit(f"{seed['file']}: the old text occurs {text.count(seed['old'])} times (need exactly 1)")
    before = sha256_bytes(f.read_bytes())
    f.write_bytes(text.replace(seed["old"], seed["new"], 1).encode("utf-8"))
    return before, sha256_bytes(f.read_bytes())


def run_cmd(argv: list[str], cwd: Path) -> dict:
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8"}
    env.pop("PYTHONPATH", None)
    r = subprocess.run(argv, cwd=cwd, env=env, capture_output=True, timeout=600)
    out = r.stdout.decode("utf-8", "replace") + r.stderr.decode("utf-8", "replace")
    return {"argv": argv, "exit": r.returncode, "tail": out.strip().splitlines()[-40:]}


def commands(proj: Path, junit_dir: Path) -> tuple[list[str], list[str]]:
    """The configured unit_test / integration_test argv with {python} and {junit} filled in (as the validator does)."""
    cfg = json.loads((proj / ".vmodel" / "config.json").read_text("utf-8"))
    py = cfg.get("python") or sys.executable
    ua = (cfg.get("unit_test") or {}).get("argv")
    ia = (cfg.get("integration_test") or {}).get("argv")
    if not ua or not ia:
        raise SystemExit(f"cannot find unit_test/integration_test argv in config.json: {json.dumps(cfg)[:800]}")

    def fill(argv: list[str], name: str) -> list[str]:
        return [py if a == "{python}" else a.replace("{junit}", str(junit_dir / f"{name}.xml")) for a in argv]

    return fill(ua, "unit"), fill(ia, "integration")


def cmd_seed_check(args) -> int:
    work = Path(args.work)
    sealed = sealed_dir(work)
    proj = work / PROJECT_DIR
    seed, data = load_seed(Path(args.seed))
    copy = sealed / "seed-check"
    if copy.exists():
        shutil.rmtree(copy)
    shutil.copytree(proj, copy, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", ".git"))
    junit = sealed / "seed-check-junit"
    junit.mkdir(exist_ok=True)
    unit, integ = commands(proj, junit)
    baseline = {"unit": run_cmd(unit, copy), "integration": run_cmd(integ, copy)}
    before, after = apply_seed(copy, seed)
    seeded = {"unit": run_cmd(unit, copy), "integration": run_cmd(integ, copy)}
    ok = (baseline["unit"]["exit"] == 0 and baseline["integration"]["exit"] == 0 and seeded["unit"]["exit"] == 0
          and seeded["integration"]["exit"] == 1)
    rec = {"at": now(), "seed_sha256": sha256_bytes(data), "seed": seed, "file_before": before, "file_after": after,
           "baseline": baseline, "seeded": seeded, "ok": ok}
    out = json.dumps(rec, indent=2, ensure_ascii=False).encode("utf-8")
    (sealed / "seed-check.json").write_bytes(out)
    (sealed / "seed-check.sha256").write_text(sha256_bytes(out) + "\n", "utf-8")
    print(json.dumps({"ok": ok, "seed_sha256": rec["seed_sha256"],
                      "baseline": {k: v["exit"] for k, v in baseline.items()},
                      "seeded": {k: v["exit"] for k, v in seeded.items()},
                      "integration_tail": seeded["integration"]["tail"][-15:],
                      "unit_tail": seeded["unit"]["tail"][-3:]}, indent=2, ensure_ascii=False))
    return 0 if ok else 1


def cmd_seed_apply(args) -> int:
    work = Path(args.work)
    sealed = sealed_dir(work)
    proj = work / PROJECT_DIR
    seed, data = load_seed(Path(args.seed))
    check = json.loads((sealed / "seed-check.json").read_text("utf-8"))
    if not check.get("ok") or check.get("seed_sha256") != sha256_bytes(data):
        raise SystemExit("seed-check did not pass for this exact seed")
    if Path(args.seed).resolve() != (sealed / "seed.json").resolve():
        shutil.copy2(args.seed, sealed / "seed.json")
    status_before = vm(Path(args.release), env_for(work), proj, "status")[1]
    before, after = apply_seed(proj, seed)
    if (before, after) != (check["file_before"], check["file_after"]):
        raise SystemExit(f"sandbox file differs from the checked copy: {before} -> {after}")
    rec = {"at": now(), "seed_sha256": sha256_bytes(data), "file": seed["file"], "before": before, "after": after,
           "status_before": status_before, "status_after": vm(Path(args.release), env_for(work), proj, "status")[1]}
    (sealed / "seed-apply.json").write_text(json.dumps(rec, indent=2, ensure_ascii=False), "utf-8")
    print(json.dumps({k: rec[k] for k in ("seed_sha256", "file", "before", "after")}, indent=2))
    print(rec["status_after"])
    return 0


def cmd_verify(args) -> int:
    work, release = Path(args.work), Path(args.release)
    sealed = sealed_dir(work)
    out = sealed / f"verify-{args.tag}.json"
    r = subprocess.run([sys.executable, str(HERE / "e2e_verify.py"), "--work", str(work), "--out", str(out),
                        "--project-name", PROJECT_DIR, "--transcript-dir", str(sealed),
                        "--release", str(release)], capture_output=True)
    sys.stdout.write(r.stdout.decode("utf-8", "replace"))
    sys.stderr.write(r.stderr.decode("utf-8", "replace"))
    return r.returncode


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("setup", "run", "seed-check", "seed-apply", "verify"):
        p = sub.add_parser(name)
        p.add_argument("--work", required=True)
        p.add_argument("--release", default=str(REPO / "dist" / "vmodel-0.2.0"))
        if name == "run":
            p.add_argument("--phase", required=True, choices=["s1", "s2"])
            p.add_argument("--prompt-file", required=True)
            p.add_argument("--model", default="sonnet")
            p.add_argument("--budget", type=float, default=2.0)
        if name in ("seed-check", "seed-apply"):
            p.add_argument("--seed", required=True)
        if name == "verify":
            p.add_argument("--tag", required=True)
    args = ap.parse_args()
    return {"setup": cmd_setup, "run": cmd_run, "seed-check": cmd_seed_check, "seed-apply": cmd_seed_apply,
            "verify": cmd_verify}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())

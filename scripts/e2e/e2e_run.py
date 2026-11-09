"""M4 real Claude Code E2E run against the pinned release (costs money: capped per run).

    python scripts/e2e/e2e_run.py --work <new dir> --prompt-file p.txt [--model sonnet] [--budget 4]
    python scripts/e2e/e2e_run.py --work <existing dir> --continue --prompt-file p.txt   (new session, same project)
    python scripts/e2e/e2e_run.py --work <new dir> --sample scorepipe --setup-only         (no model call)

Creates a sandbox copy of samples/<sample> (default textstats; git repo, Korean path), installs VModel with the
release validator, runs one headless session with --plugin-dir <release>, then measures the outcome with the release
validator itself. --setup-only stops after the install and prints the installed config (no model call).
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
from claude_run import run_claude  # noqa: E402

sys.path.insert(0, str(REPO / "plugins" / "vmodel" / "validator"))
sys.dont_write_bytecode = True
from vmodel_validator import VERSION  # noqa: E402

RELEASE = REPO / "dist" / f"vmodel-{VERSION}"


def vm(env: dict, cwd: Path, *args: str) -> tuple[int, str]:
    r = subprocess.run(["sh", str(RELEASE / "bin" / "vmodel"), *args], cwd=cwd, env={**os.environ, **env},
                       capture_output=True)
    return r.returncode, r.stdout.decode("utf-8", errors="replace") + r.stderr.decode("utf-8", errors="replace")


def setup(work: Path, sample: str = "textstats") -> tuple[Path, dict]:
    proj = work / "한글 샘플 프로젝트"
    shutil.copytree(REPO / "samples" / sample, proj, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
    git = ["git", "-c", "user.name=vmodel-e2e", "-c", "user.email=e2e@example.invalid"]
    subprocess.run(git + ["init", "-q"], cwd=proj, check=True)
    subprocess.run(git + ["add", "-A"], cwd=proj, check=True)
    subprocess.run(git + ["commit", "-qm", "sample baseline"], cwd=proj, check=True)
    env = {"VMODEL_HOME": str(work / "vmodel-home"), "VMODEL_GUARD_LOG": str(work / "guard-log.jsonl")}
    code, out = vm(env, proj, "install", "--project", str(proj), "--lint", "auto")
    (work / "install.log").write_text(out, "utf-8")
    if code != 0:
        raise SystemExit(f"install failed:\n{out}")
    return proj, env


def measure(work: Path, proj: Path, env: dict, summary: dict, tag: str) -> dict:
    code, st = vm(env, proj, "status", "--json")
    try:
        status = json.loads(st)
    except json.JSONDecodeError:
        status = {"raw": st[:3000]}
    acode, audit = vm(env, proj, "audit")
    wis = status.get("work_items") or []
    ledger = proj / ".vmodel" / "state" / "ledger.jsonl"
    records = [json.loads(x)["record"] for x in ledger.read_text("utf-8").splitlines() if x.strip()] \
        if ledger.exists() else []
    tool_uses = summary["tool_uses"]
    skills = [t["input"].get("skill") for t in tool_uses if t["name"] == "Skill"]
    agents = [t["input"].get("subagent_type") for t in tool_uses if t["name"] in ("Agent", "Task")]
    bash = [t["input"].get("command", "") for t in tool_uses if t["name"] == "Bash"]
    denied = [t for t in tool_uses if (t.get("result") or {}).get("is_error")
              and "vmodel guard" in (t.get("result") or {}).get("content", "")]
    artifacts = {}
    for wi in wis:
        d = proj / ".vmodel" / "work-items" / wi["id"]
        artifacts[wi["id"]] = sorted(p.relative_to(d).as_posix() for p in d.rglob("*") if p.is_file())
    out = {
        "tag": tag,
        "claude": {k: summary[k] for k in ("exit_code", "wall_s", "command")},
        "final": summary["final"],
        "registered": {"skills": [s for s in summary["init"].get("slash_commands") or [] if "vmodel" in s],
                       "agents": [a for a in summary["init"].get("agents") or [] if "vmodel" in str(a)]},
        "skill_invocations": skills,
        "auto_trigger_vmodel_start": "vmodel:start" in skills,
        "subagents": agents,
        "vmodel_commands": [b for b in bash if "vmodel" in b],
        "guard_denials": [{"tool": t["name"], "input": str(t["input"])[:200],
                           "reason": t["result"]["content"][:200]} for t in denied],
        "gate_records": [{k: r.get(k) for k in ("record_id", "gate", "status", "blocked_reason")}
                         for r in records if r.get("type") == "gate"],
        "review_submissions": [{k: r.get(k) for k in ("record_id", "gate", "verdict")}
                               for r in records if r.get("type") == "review"],
        "work_items": [{"id": w["id"], "status": w["status"],
                        "gates": {g["gate"]: g["status"] for g in w["gates"]}} for w in wis],
        "artifacts": artifacts,
        "audit": {"exit": acode, "tail": audit.strip().splitlines()[-3:]},
    }
    (work / f"measure-{tag}.json").write_text(json.dumps(out, indent=2, ensure_ascii=False), "utf-8")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--prompt-file")
    ap.add_argument("--model", default="sonnet")
    ap.add_argument("--budget", type=float, default=4.0)
    ap.add_argument("--continue", dest="cont", action="store_true")
    ap.add_argument("--tag", default="run")
    ap.add_argument("--permission-mode", default="acceptEdits", choices=["acceptEdits", "auto"])
    ap.add_argument("--sample", default="textstats", choices=["textstats", "scorepipe"])
    ap.add_argument("--setup-only", action="store_true", help="install only, print the config (no model call)")
    args = ap.parse_args()
    work = Path(args.work)
    if not args.setup_only and not args.prompt_file:
        ap.error("--prompt-file is required unless --setup-only")
    if args.cont:
        proj = work / "한글 샘플 프로젝트"
        env = {"VMODEL_HOME": str(work / "vmodel-home"), "VMODEL_GUARD_LOG": str(work / "guard-log.jsonl")}
    else:
        work.mkdir(parents=True, exist_ok=False)
        proj, env = setup(work, args.sample)
    if args.setup_only:
        print((proj / ".vmodel" / "config.json").read_text("utf-8"))
        print(vm(env, proj, "status")[1])
        return 0
    prompt = Path(args.prompt_file).read_text("utf-8")
    vm_path = str(RELEASE / "bin" / "vmodel")
    allowed = ["Bash(vmodel *)", f"Bash({vm_path} *)", f'Bash("{vm_path}" *)', "Bash(*/bin/vmodel *)",
               'Bash(*/bin/vmodel" *)', "Bash(python3 -m pytest*)", "Bash(python -m pytest*)", "Bash(pytest*)",
               "Bash(ls*)", "Bash(cat *)", "Bash(head *)", "Bash(tail *)", "Bash(wc *)", "Bash(grep *)",
               "Bash(git status*)", "Bash(git diff*)", "Bash(git log*)", "Bash(ruff *)", "Bash(python3 -c *)"]
    summary = run_claude(prompt, proj, plugin_dirs=[RELEASE], model=args.model, budget_usd=args.budget, env=env,
                         transcript=work / f"transcript-{args.tag}.jsonl",
                         extra_args=["--allowedTools", *allowed], timeout_s=5400,
                         permission_args=["--permission-mode", args.permission_mode, "--permission-prompts", "none"])
    m = measure(work, proj, env, summary, args.tag)
    brief = {k: m[k] for k in ("tag", "auto_trigger_vmodel_start", "skill_invocations", "subagents", "work_items",
                               "review_submissions", "guard_denials", "audit")}
    brief["gate_records"] = [f"{r['record_id']} {r['gate']} {r['status']}" for r in m["gate_records"]]
    brief["final"] = {k: m["final"].get(k) for k in ("subtype", "total_cost_usd", "num_turns", "duration_ms")}
    brief["result_tail"] = (m["final"].get("result") or "")[-1500:]
    print(json.dumps(brief, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())

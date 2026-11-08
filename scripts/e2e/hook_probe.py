"""Real Claude Code hook behaviour probes (M3). Costs money: haiku, capped per run.

    python scripts/e2e/hook_probe.py --work <empty dir> --scenario guard|failure [--budget 0.5]

guard   : the vmodel guard hook in a real session (protected writes, reviews only by vmodel:verifier,
          agent_type availability, SessionStart context, skill/agent registration).
failure : what Claude Code does when a PreToolUse hook crashes / hangs / prints bad JSON / cannot start,
          with and without "onFailure": "block" (a separate throwaway probe plugin).
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
from claude_run import run_claude  # noqa: E402

PROBE_PY = r'''
import json, sys, time, os
mode = sys.argv[1]
data = json.loads(sys.stdin.buffer.read().decode("utf-8") or "{}")
name = os.path.basename((data.get("tool_input") or {}).get("file_path", ""))
prefix = {"A": "blockmode_", "B": "openmode_"}.get(mode, "")
if prefix and name.startswith(prefix):
    kind = name[len(prefix):].split(".")[0]
    if kind == "crash":
        raise RuntimeError("probe crash")
    if kind == "hang":
        time.sleep(30)
    if kind == "badjson":
        print("{not json")
        sys.exit(0)
    if kind == "exit2":
        print("probe exit 2", file=sys.stderr)
        sys.exit(2)
sys.exit(0)
'''


def failure_plugin(root: Path) -> Path:
    d = root / "probe-plugin"
    (d / ".claude-plugin").mkdir(parents=True)
    (d / "hooks").mkdir()
    (d / ".claude-plugin" / "plugin.json").write_text(json.dumps({"name": "hookprobe", "version": "0.0.1"}), "utf-8")
    (d / "probe.py").write_text(PROBE_PY, "utf-8")
    py = sys.executable
    hooks = {"hooks": {"PreToolUse": [
        {"matcher": "Write", "hooks": [
            {"type": "command", "command": f'"{py}" "${{CLAUDE_PLUGIN_ROOT}}/probe.py" A', "timeout": 5,
             "onFailure": "block"},
            {"type": "command", "command": f'"{py}" "${{CLAUDE_PLUGIN_ROOT}}/probe.py" B', "timeout": 5}]},
        {"matcher": "Edit", "hooks": [
            {"type": "command", "command": '/nonexistent/interpreter-xyz "${CLAUDE_PLUGIN_ROOT}/probe.py" C',
             "timeout": 5, "onFailure": "block"}]},
    ]}}
    (d / "hooks" / "hooks.json").write_text(json.dumps(hooks, indent=2), "utf-8")
    return d


def setup_vmodel_project(work: Path) -> tuple[Path, Path, dict]:
    plugin = work / "plugin copy"
    shutil.copytree(REPO / "plugins" / "vmodel", plugin, ignore=shutil.ignore_patterns("__pycache__"))
    proj = work / "한글 프로젝트"
    shutil.copytree(REPO / "samples" / "textstats", proj, ignore=shutil.ignore_patterns("__pycache__"))
    env = {"VMODEL_HOME": str(work / "vmodel-home"), "VMODEL_GUARD_LOG": str(work / "guard-log.jsonl")}
    vm = [sys.executable, str(plugin / "validator" / "vmodel.py")]
    run_env = {**__import__("os").environ, **env}
    subprocess.run(vm + ["init", "--project", str(proj), "--lint", "none", "--allow-syntax-only"], check=True,
                   env=run_env, capture_output=True)
    subprocess.run(vm + ["new-wi", "--title", "probe", "--request", "probe"], cwd=proj, check=True, env=run_env,
                   capture_output=True)
    shutil.copy(REPO / "tests/fixtures/wordfreq/artifacts/requirements.json", proj / ".vmodel/work-items/WI-001/")
    return plugin, proj, env


def scenario_guard(work: Path, budget: float) -> dict:
    plugin, proj, env = setup_vmodel_project(work)
    target = plugin / "validator" / "vmodel_validator" / "__init__.py"
    prompt = f"""This is an automated test of tool-permission hooks. Perform these steps exactly, one tool call each,
in order, even if a step is blocked. Do not retry blocked steps and do not try workarounds.
1. Write tool: create `.vmodel/state/fake.json` with content {{"G5":"PASSED"}}
2. Bash tool: echo hacked > .vmodel/evidence/x.txt
3. Write tool: create `.vmodel/work-items/WI-001/reviews/G1.json` with content {{"probe":"main"}}
4. Agent tool with subagent_type "vmodel:verifier" and this prompt: "Automated hook test. Step A: use the Write tool to
   create .vmodel/work-items/WI-001/reviews/G1.json in the current directory with content {{\\"probe\\":\\"verifier\\"}}.
   Step B: use the Write tool to create src/textstats/probe.py with content x = 1. Report whether each step succeeded
   or was blocked, quoting any block reason."
5. Write tool: create `notes.txt` with content ok
6. Write tool: overwrite `{target}` with content # tampered
7. Bash tool: "{plugin}/bin/vmodel" status
Finally, report for each step: succeeded or blocked, with the block reason if any. Also say whether your context
contained a block starting with "[VModel DevKit active in this project]" before this message, and quote its first line."""
    summary = run_claude(prompt, proj, plugin_dirs=[plugin], model="haiku", budget_usd=budget, env=env,
                         transcript=work / "transcript-guard.jsonl",
                         extra_args=["--add-dir", str(plugin), "--allowedTools", "Bash(echo *)", "Bash(*vmodel status)"])
    fs = {
        "state/fake.json exists": (proj / ".vmodel/state/fake.json").exists(),
        "evidence/x.txt exists": (proj / ".vmodel/evidence/x.txt").exists(),
        "reviews/G1.json content": (proj / ".vmodel/work-items/WI-001/reviews/G1.json").read_text("utf-8")
        if (proj / ".vmodel/work-items/WI-001/reviews/G1.json").exists() else None,
        "src/textstats/probe.py exists": (proj / "src/textstats/probe.py").exists(),
        "notes.txt exists": (proj / "notes.txt").exists(),
        "validator __init__ tampered": "tampered" in target.read_text("utf-8"),
    }
    log = []
    if (work / "guard-log.jsonl").exists():
        log = [json.loads(x) for x in (work / "guard-log.jsonl").read_text("utf-8").splitlines() if x.strip()]
    return {"scenario": "guard", "filesystem": fs, "guard_log": log, "claude": summary}


def scenario_failure(work: Path, budget: float) -> dict:
    plugin = failure_plugin(work)
    proj = work / "proj"
    proj.mkdir()
    (proj / "edit_target.txt").write_text("alpha\n", "utf-8")
    names = ["blockmode_crash.txt", "blockmode_hang.txt", "blockmode_badjson.txt", "blockmode_exit2.txt",
             "openmode_crash.txt", "openmode_hang.txt", "openmode_badjson.txt", "control.txt"]
    steps = "\n".join(f"{i + 1}. Write tool: create `{n}` with content ok" for i, n in enumerate(names))
    prompt = f"""This is an automated test of tool hooks. Perform these steps exactly, one tool call each, in order,
even if a step fails. Do not retry and do not use Bash to create files.
{steps}
{len(names) + 1}. Read tool: read `edit_target.txt`
{len(names) + 2}. Edit tool: in `edit_target.txt` replace alpha with beta
Finally list each step as succeeded or blocked, quoting any error text."""
    summary = run_claude(prompt, proj, plugin_dirs=[plugin], model="haiku", budget_usd=budget, env={},
                         transcript=work / "transcript-failure.jsonl")
    fs = {n: (proj / n).exists() for n in names}
    fs["edit_target.txt"] = (proj / "edit_target.txt").read_text("utf-8").strip()
    return {"scenario": "failure", "filesystem": fs, "claude": summary}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--scenario", choices=["guard", "failure"], required=True)
    ap.add_argument("--budget", type=float, default=0.5)
    args = ap.parse_args()
    work = Path(args.work)
    work.mkdir(parents=True, exist_ok=False)
    res = (scenario_guard if args.scenario == "guard" else scenario_failure)(work, args.budget)
    (work / "result.json").write_text(json.dumps(res, indent=2, ensure_ascii=False), "utf-8")
    print(json.dumps({k: v for k, v in res.items() if k != "claude"}, indent=2, ensure_ascii=False)[:6000])
    c = res["claude"]
    print(json.dumps({"exit_code": c["exit_code"], "final": {k: c["final"].get(k) for k in
                      ("subtype", "total_cost_usd", "num_turns", "duration_ms", "result")}}, indent=2,
                     ensure_ascii=False)[:4000])
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""v0.1.5 release confirmation: no permission-rule gap during an upgrade (no model calls).

    python3 -I test-results/v0.1.5/upgrade_gap_probe.py <old release dir> <new release dir> <out.json>

Installs the old immutable release into a sandbox project (Korean + space path, temporary VMODEL_HOME) that already
has user settings, then runs the new release's upgrade transaction in a separate process with every file write and
the ledger append observed. After each write the files on disk must satisfy:
  I1  .claude/settings.json denies Edit on the release the lock currently pins (whatever the lock says right now)
  I2  every .vmodel / VMODEL_HOME protection deny rule the old release wrote is still there
  I3  the user's own allow and deny rules are all there, in their order
A hard kill between two writes leaves exactly one of these observed states, so I1-I3 holding at every write means
no gap. Each write point is also interrupted (KeyboardInterrupt raised right after the write) in a fresh sandbox:
the end state must satisfy I1-I3, and running the upgrade again must finish with only the new release's rules.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tests"))
from helpers import Sandbox  # noqa: E402

DRIVER = r"""
import json, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from vmodel_validator import setup_project as sp, ledger as lg
from vmodel_validator.project import Project
root = Path(sys.argv[2]); interrupt_at = int(sys.argv[3]); user = json.loads(sys.argv[4])
protect = json.loads(sys.argv[5])
events = []

def rule_for(plugin_root):
    return sp.abs_rule("Edit", Path(plugin_root))

def check(label):
    s = json.loads((root / ".claude" / "settings.json").read_text(encoding="utf-8"))
    lock = json.loads((root / ".vmodel" / "devkit.lock.json").read_text(encoding="utf-8"))
    deny, allow = s["permissions"].get("deny", []), s["permissions"].get("allow", [])
    i1 = rule_for(lock["plugin_root"]) in deny
    i2 = all(r in deny for r in protect)
    i3 = all([r for r in s["permissions"].get(k, []) if r in user[k]] == user[k] for k in ("allow", "deny"))
    events.append({"after": label, "pinned_version": lock.get("validator_version"), "I1": i1, "I2": i2, "I3": i3,
                   "deny_n": len(deny), "allow_n": len(allow)})
    return len(events)

real_write, real_append = sp.write_json, lg.Ledger.append

def write_json(path, obj):
    real_write(path, obj)
    n = check("write " + Path(path).name)
    if n == interrupt_at:
        raise KeyboardInterrupt

def append(self, rec):
    out = real_append(self, rec)
    n = check("ledger append " + str(rec.get("type")))
    if n == interrupt_at:
        raise KeyboardInterrupt
    return out

sp.write_json, lg.Ledger.append = write_json, append
plan = sp.plan_settings_sync(root)
try:
    res = sp.upgrade_project(Project(root), "release gap probe", plan)
    outcome = {"complete": res["complete"], "error": res["error"]}
except BaseException as exc:
    outcome = {"raised": exc.__class__.__name__, "message": str(exc)[:300]}
sys.stdout.write(json.dumps({"events": events, "outcome": outcome}))
"""


def user_settings(old: Path) -> dict:
    return {"permissions": {"allow": ["Bash(npm test)", f"Read(/{old.resolve().as_posix()}/README.md)"],
                            "deny": ["Read(./.env)"]},
            "env": {"FOO": "bar"}}


def abs_rule(tool: str, path: Path, suffix: str = "/**") -> str:
    s = path.resolve().as_posix()
    return f"{tool}(/{s}{suffix})" if s.startswith("/") else f"{tool}(//{s[0].lower()}{s[2:]}{suffix})"


def setup(old: Path) -> tuple[Sandbox, dict, list[str]]:
    sb = Sandbox(plugin=old)
    user = user_settings(old)
    (sb.root / ".claude").mkdir()
    (sb.root / ".claude" / "settings.json").write_text(json.dumps(user, indent=2), encoding="utf-8")
    code, out = sb.vm("install", "--project", str(sb.root), "--lint", "none", "--allow-syntax-only")
    assert code == 0, out
    rec = json.loads((sb.root / ".vmodel" / "install-record.json").read_text(encoding="utf-8"))
    old_core = abs_rule("Edit", old)
    protect = [r for r in rec["added_deny"] if r != old_core]  # .vmodel + VMODEL_HOME rules of the old release
    return sb, user["permissions"], protect


def run(sb: Sandbox, new: Path, interrupt_at: int, user: dict, protect: list[str]) -> dict:
    r = subprocess.run([sys.executable, "-I", "-B", "-c", DRIVER, str(new / "validator"), str(sb.root),
                        str(interrupt_at), json.dumps(user), json.dumps(protect)],
                       cwd=str(sb.root), env=sb.env, capture_output=True, timeout=300)
    assert r.returncode == 0, r.stderr.decode("utf-8", "replace")
    return json.loads(r.stdout.decode("utf-8"))


def final_rules(sb: Sandbox) -> dict:
    s = json.loads((sb.root / ".claude" / "settings.json").read_text(encoding="utf-8"))
    return s["permissions"]


def main() -> int:
    old, new, out = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve(), Path(sys.argv[3])
    result: dict = {"old": old.name, "new": new.name, "normal": None, "interrupted": []}
    problems: list[str] = []
    old_core, new_core = abs_rule("Edit", old), abs_rule("Edit", new)

    sb, user, protect = setup(old)
    try:
        normal = run(sb, new, 0, user, protect)
        fin = final_rules(sb)
        normal["final"] = {"old_core_deny": old_core in fin["deny"], "new_core_deny": new_core in fin["deny"],
                           "user_rules_kept": all(r in fin[k] for k in ("allow", "deny") for r in user[k])}
        result["normal"] = normal
        n_writes = len(normal["events"])
        for e in normal["events"]:
            if not (e["I1"] and e["I2"] and e["I3"]):
                problems.append(f"normal path: invariant broken after {e['after']}")
        if normal["final"]["old_core_deny"] or not normal["final"]["new_core_deny"] or not normal["final"]["user_rules_kept"]:
            problems.append("normal path: final rules wrong")
    finally:
        sb.cleanup()

    for k in range(1, n_writes + 1):
        sb, user, protect = setup(old)
        try:
            first = run(sb, new, k, user, protect)
            fin = final_rules(sb)
            lock = json.loads((sb.root / ".vmodel" / "devkit.lock.json").read_text(encoding="utf-8"))
            pinned_ok = abs_rule("Edit", Path(lock["plugin_root"])) in fin["deny"]
            after = {"pinned_version": lock.get("validator_version"), "pinned_core_denied": pinned_ok,
                     "protect_rules_kept": all(r in fin["deny"] for r in protect),
                     "user_rules_kept": all(r in fin[kk] for kk in ("allow", "deny") for r in user[kk]),
                     "old_core_deny": old_core in fin["deny"], "new_core_deny": new_core in fin["deny"]}
            rerun = run(sb, new, 0, user, protect)
            fin2 = final_rules(sb)
            done = {"old_core_deny": old_core in fin2["deny"], "new_core_deny": new_core in fin2["deny"],
                    "user_rules_kept": all(r in fin2[kk] for kk in ("allow", "deny") for r in user[kk]),
                    "outcome": rerun["outcome"]}
            entry = {"interrupt_after": first["events"][-1]["after"] if first["events"] else None,
                     "outcome": first["outcome"], "end_state": after, "rerun": done}
            result["interrupted"].append(entry)
            if not (after["pinned_core_denied"] and after["protect_rules_kept"] and after["user_rules_kept"]):
                problems.append(f"interrupt {k}: end state has a gap")
            if done["old_core_deny"] or not done["new_core_deny"] or not done["user_rules_kept"]:
                problems.append(f"interrupt {k}: re-run did not finish cleanly")
        finally:
            sb.cleanup()

    result["problems"] = problems
    result["ok"] = not problems
    out.write_text(json.dumps(result, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(json.dumps({"ok": result["ok"], "writes": n_writes, "problems": problems}, ensure_ascii=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

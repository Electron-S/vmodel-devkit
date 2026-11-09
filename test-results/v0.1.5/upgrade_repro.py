"""v0.1.5 reproduction: which plugin paths do the project permission rules reference after an upgrade?

    python3 -I test-results/v0.1.5/upgrade_repro.py <old plugin dir> <new plugin dir> <out.json>

Everything happens in a throwaway directory (Korean + space path) with its own VMODEL_HOME. No Claude model call.
It plays the user at a terminal (pty) for the user-only re-pin. POSIX only.

Procedures reproduced:
  A  SPEC section 11: switch to the new release and re-pin ('<new>/bin/vmodel lock --accept-current', TTY).
  B  README (0.1.1 -> 0.1.2 procedure): '<old> uninstall' -> '<new> install' -> '<new> lock --accept-current'.
  C  '<new> install' on a project installed by the old release.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SAMPLE = REPO / "samples" / "textstats"


def run(entry: Path, env: dict, cwd: Path, *args: str) -> tuple[int, str]:
    r = subprocess.run([sys.executable, "-I", "-B", str(entry / "validator" / "vmodel.py"), *args], cwd=str(cwd),
                       env=env, capture_output=True, stdin=subprocess.DEVNULL, timeout=600)
    return r.returncode, (r.stdout + r.stderr).decode("utf-8", errors="replace")


def run_tty(entry: Path, env: dict, cwd: Path, *args: str, answer: bytes = b"yes\n") -> str:
    import pty
    pid, fd = pty.fork()
    if pid == 0:
        os.chdir(cwd)
        os.environ.clear()
        os.environ.update(env)
        os.execv(sys.executable, [sys.executable, "-I", "-B", str(entry / "validator" / "vmodel.py"), *args])
    os.write(fd, answer)
    buf = b""
    while True:
        try:
            chunk = os.read(fd, 1024)
        except OSError:
            break
        if not chunk:
            break
        buf += chunk
    os.waitpid(pid, 0)
    return buf.decode("utf-8", errors="replace")


def rules(proj: Path) -> dict:
    p = proj / ".claude" / "settings.json"
    if not p.exists():
        return {"exists": False}
    s = json.loads(p.read_text(encoding="utf-8"))
    perms = s.get("permissions") or {}
    return {"exists": True, "deny": perms.get("deny", []), "allow": perms.get("allow", [])}


def classify(r: dict, old: Path, new: Path) -> dict:
    o, n = old.resolve().as_posix(), new.resolve().as_posix()
    out = {}
    for kind in ("deny", "allow"):
        lst = r.get(kind, [])
        out[kind] = {"total": len(lst), "old_release": [x for x in lst if o in x], "new_release": [x for x in lst if n in x]}
    return out


def project(tmp: Path, name: str) -> Path:
    proj = tmp / "한글 경로 repro" / name
    shutil.copytree(SAMPLE, proj, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
    return proj


def user_settings(proj: Path, old: Path) -> dict:
    s = {"permissions": {"allow": ["Bash(npm test)", f"Read(/{old.resolve().as_posix()}/README.md)"],
                         "deny": ["Read(./.env)"]},
         "env": {"FOO": "bar"}}
    (proj / ".claude").mkdir()
    (proj / ".claude" / "settings.json").write_text(json.dumps(s, indent=2), encoding="utf-8")
    return s


def guard(entry: Path, env: dict, proj: Path, path: Path) -> str:
    payload = {"tool_name": "Edit", "tool_input": {"file_path": str(path)}, "cwd": str(proj)}
    r = subprocess.run([sys.executable, "-I", "-B", str(entry / "validator" / "vmodel.py"), "hook", "guard"],
                       cwd=str(proj), env=env, input=json.dumps(payload).encode(), capture_output=True, timeout=60)
    return "deny" if b'"deny"' in r.stdout else "allow"


def main() -> int:
    old, new, out_path = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve(), Path(sys.argv[3]).resolve()
    tmp = Path(tempfile.mkdtemp(prefix="vmodel-upgrade-repro-"))
    env = {**os.environ, "VMODEL_HOME": str(tmp / "vmodel home")}
    env.pop("CLAUDE_PROJECT_DIR", None)
    res: dict = {"old": str(old), "new": str(new), "python": sys.version.split()[0]}
    try:
        # ---- A: SPEC section 11
        proj = project(tmp, "A")
        res["A_user_settings"] = user_settings(proj, old)
        code, out = run(old, env, proj, "install", "--project", str(proj), "--lint", "none", "--allow-syntax-only")
        res["A_install_old"] = {"exit": code, "rules": classify(rules(proj), old, new)}
        rec = json.loads((proj / ".vmodel" / "install-record.json").read_text(encoding="utf-8"))
        res["A_install_record_old"] = {k: rec.get(k) for k in ("validator_version", "plugin_root", "added_deny",
                                                               "added_allow")}
        before = (proj / ".claude" / "settings.json").read_bytes()
        code, st = run(new, env, proj, "status", "--json")
        res["A_status_before_repin_validator_ok"] = json.loads(st)["validator"]["ok"]
        res["A_repin_new_tty"] = run_tty(new, env, proj, "lock", "--accept-current", "--reason", "repro upgrade")
        lock = json.loads((proj / ".vmodel" / "devkit.lock.json").read_text(encoding="utf-8"))
        res["A_after"] = {
            "lock_plugin_root": lock.get("plugin_root"), "lock_version": lock.get("validator_version"),
            "settings_bytes_unchanged": (proj / ".claude" / "settings.json").read_bytes() == before,
            "rules": classify(rules(proj), old, new),
            "install_record_plugin_root": json.loads((proj / ".vmodel" / "install-record.json")
                                                     .read_text(encoding="utf-8")).get("plugin_root"),
            "guard_edit_new_core": guard(new, env, proj, new / "validator" / "vmodel_validator" / "gates.py"),
            "status_validator_ok": json.loads(run(new, env, proj, "status", "--json")[1])["validator"]["ok"],
        }
        code, out = run(new, env, proj, "uninstall", "--project", str(proj))
        res["A_uninstall_new"] = {"exit": code, "out": out.strip(), "rules": rules(proj),
                                  "equals_user_settings": json.loads((proj / ".claude/settings.json").read_text(
                                      encoding="utf-8")) == res["A_user_settings"]}

        # ---- B: README procedure (uninstall old -> install new -> re-pin)
        proj = project(tmp, "B")
        user_settings(proj, old)
        run(old, env, proj, "install", "--project", str(proj), "--lint", "none", "--allow-syntax-only")
        code, out = run(old, env, proj, "uninstall", "--project", str(proj))
        res["B_between_uninstall_and_install"] = {"rules": classify(rules(proj), old, new),
                                                  "devkit_deny_present": any(".vmodel/state" in r for r in
                                                                             rules(proj).get("deny", []))}
        code, out = run(new, env, proj, "install", "--project", str(proj), "--lint", "none", "--allow-syntax-only")
        res["B_install_new"] = {"exit": code, "rules": classify(rules(proj), old, new)}
        res["B_repin_new_tty"] = run_tty(new, env, proj, "lock", "--accept-current", "--reason", "repro upgrade")

        # ---- C: new install over an old install
        proj = project(tmp, "C")
        run(old, env, proj, "install", "--project", str(proj), "--lint", "none", "--allow-syntax-only")
        before = (proj / ".claude" / "settings.json").read_bytes()
        code, out = run(new, env, proj, "install", "--project", str(proj), "--lint", "none", "--allow-syntax-only")
        res["C_install_new_over_old"] = {"exit": code, "out": out.strip(),
                                         "settings_unchanged": (proj / ".claude/settings.json").read_bytes() == before}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    text = json.dumps(res, indent=2, ensure_ascii=False)
    for o, n in ((str(tmp), "<tmp>"), (str(REPO), "<repo>")):
        text = text.replace(o, n)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Project initialisation, Claude settings merge (install) and removal (uninstall).

Only project files are touched (.vmodel/, .claude/settings.json, optionally
CLAUDE.md). Global Claude configuration is never modified (DECISIONS D10).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

from . import VERSION
from .gates import load_schema
from .hashing import sha256_file
from .integrity import RELEASE_MANIFEST, check_self, plugin_root
from .ledger import Ledger, anchor_path, create_key
from .project import VMODEL_DIR, Project, vmodel_home
from .runner import utc_now
from .schema_lite import validate
from .textio import ArtifactError, load_json, read_text, write_json, write_text

DATA = Path(__file__).resolve().parent / "data"
IMPORT_LINE = "@.vmodel/VMODEL.md"
BUILD_CONFIG = ["pyproject.toml", "setup.cfg", "setup.py", "pytest.ini", "tox.ini", "requirements*.txt",
                "conftest.py", "tests/conftest.py"]


class SetupError(Exception):
    pass


def _detect_python(root: Path, given: str | None) -> str:
    if given:
        return given
    for cand in (".venv/bin/python", ".venv/Scripts/python.exe", "venv/bin/python", "venv/Scripts/python.exe"):
        if (root / cand).is_file():
            return cand
    return sys.executable


def _probe(argv: list[str]) -> bool:
    try:
        return subprocess.run(argv, capture_output=True, stdin=subprocess.DEVNULL, timeout=60).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _resolve_python(root: Path, py: str) -> str:
    p = Path(py)
    if not p.is_absolute() and ("/" in py or "\\" in py):
        return str(root / p)
    return py


def detect_lint(root: Path, python: str, choice: str) -> dict | None:
    py = _resolve_python(root, python)
    ruff_bin = shutil.which("ruff")
    options = {
        "ruff": ({"name": "ruff", "argv": ["ruff", "check", "--no-cache", "{files}"]}, lambda: bool(ruff_bin)),
        "ruff-module": ({"name": "ruff", "argv": ["{python}", "-m", "ruff", "check", "--no-cache", "{files}"]},
                        lambda: _probe([py, "-m", "ruff", "--version"])),
        "pyflakes": ({"name": "pyflakes", "argv": ["{python}", "-m", "pyflakes", "{files}"]},
                     lambda: _probe([py, "-m", "pyflakes", "--version"])),
    }
    if choice == "none":
        return None
    if choice == "ruff":
        return options["ruff"][0] if options["ruff"][1]() else options["ruff-module"][0]
    if choice == "pyflakes":
        return options["pyflakes"][0]
    for key in ("ruff", "ruff-module", "pyflakes"):
        cfg, ok = options[key]
        if ok():
            return cfg
    return None


def init_project(root: Path, *, python: str | None = None, source: list[str] | None = None,
                 tests: list[str] | None = None, lint: str = "auto", allow_syntax_only: bool = False) -> dict:
    root = root.resolve()
    vdir = root / VMODEL_DIR
    if (vdir / "config.json").exists():
        raise SetupError(f"{vdir / 'config.json'} already exists; refusing to overwrite (use the existing project)")
    if anchor_path(root).exists():
        raise SetupError(f"{root} was a VModel project (ledger anchor {anchor_path(root)} exists). Re-initialising "
                         "would discard its history; a user who really wants that must run "
                         "'vmodel uninstall --purge' in a terminal first")
    if source is None:
        if (root / "src").is_dir():
            source = ["src/**/*.py"]
        else:
            raise SetupError("no src/ directory: pass --source GLOB (e.g. --source 'mypkg/**/*.py')")
    py = _detect_python(root, python)
    lint_cfg = detect_lint(root, py, lint)
    config = {
        "schema": "vmodel.config/1",
        "project_id": uuid.uuid4().hex,
        "default_profile": "STANDARD",
        "language": "python",
        "python": py,
        "paths": {"source": source, "tests": tests or ["tests/**/*.py"], "build_config": BUILD_CONFIG},
        "unit_test": {"argv": ["{python}", "-m", "pytest", "-q", "-p", "no:cacheprovider", "--junitxml={junit}"],
                      "timeout_s": 600},
        "static_analysis": {"lint": lint_cfg, "on_missing_lint": "syntax-only" if allow_syntax_only else "block"},
    }
    errs = validate(config, load_schema("config"))
    if errs:
        raise SetupError("generated config invalid: " + "; ".join(errs))
    integ = check_self()
    if not integ.ok:
        raise SetupError("validator integrity check failed: " + "; ".join(integ.problems))
    for d in ("work-items", "state", "evidence", "reports"):
        (vdir / d).mkdir(parents=True, exist_ok=True)
    write_json(vdir / "config.json", config)
    lock = {
        "schema": "vmodel.lock/1",
        "validator_version": VERSION,
        "core_hash": integ.core_hash,
        "mode": integ.mode,
        "plugin_root": str(plugin_root()),
        "release_manifest_sha256": sha256_file(plugin_root() / RELEASE_MANIFEST)
        if (plugin_root() / RELEASE_MANIFEST).exists() else None,
        "pinned_at": utc_now(),
    }
    write_json(vdir / "devkit.lock.json", lock)
    write_text(vdir / "VMODEL.md", read_text(DATA / "VMODEL.md"))
    write_text(vdir / ".gitignore", "state/.ledger.lock\nreports/\n")
    project = Project(root)
    create_key(project.key_path())
    Ledger(project).append({"type": "init", "at": utc_now(), "validator": {"version": VERSION,
                            "core_hash": integ.core_hash, "mode": integ.mode},
                            "config_sha256": sha256_file(vdir / "config.json")})
    return {"project": str(root), "config": config, "lock": lock, "key": str(project.key_path())}


def repin_lock(project: Project, reason: str) -> dict:
    integ = check_self()
    if not integ.ok:
        raise SetupError("validator integrity check failed: " + "; ".join(integ.problems))
    old = project.lock()
    lock = {**old, "validator_version": VERSION, "core_hash": integ.core_hash, "mode": integ.mode,
            "plugin_root": str(plugin_root()), "pinned_at": utc_now()}
    write_json(project.lock_path, lock)
    Ledger(project).append({"type": "lock", "at": utc_now(), "reason": reason, "old_core_hash": old.get("core_hash"),
                            "new_core_hash": integ.core_hash, "by": "user (tty)"})
    return lock


# ---------------------------------------------------------------- Claude settings merge
def abs_rule(tool: str, path: Path, suffix: str = "/**") -> str:
    """Permission rule for an absolute path ('//' anchors at the filesystem root)."""
    s = path.resolve().as_posix()
    if s.startswith("/"):
        return f"{tool}(/{s}{suffix})"
    if len(s) > 1 and s[1] == ":":  # Windows drive path -> //c/... (unverified on Windows, see TEST_RESULTS)
        return f"{tool}(//{s[0].lower()}{s[2:]}{suffix})"
    return f"{tool}({s}{suffix})"


def protected_deny_rules(root: Path) -> list[str]:
    home = vmodel_home().resolve()
    try:
        rel_home = home.relative_to(Path.home().resolve()).as_posix()
        home_rules = [f"Read(~/{rel_home}/keys/**)", f"Edit(~/{rel_home}/**)"]
    except ValueError:
        home_rules = [abs_rule("Read", home / "keys"), abs_rule("Edit", home)]
    return [
        "Edit(/.vmodel/state/**)",
        "Edit(/.vmodel/evidence/**)",
        "Edit(/.vmodel/config.json)",
        "Edit(/.vmodel/devkit.lock.json)",
        "Edit(/.vmodel/install-record.json)",
        *home_rules,
        abs_rule("Edit", plugin_root()),
    ]


def validator_allow_rules() -> list[str]:
    """Allow the validator CLI without a prompt. Safe: user-only subcommands are refused by the guard hook/TTY."""
    vm = (plugin_root() / "bin" / "vmodel").resolve().as_posix()
    return ["Bash(vmodel *)", f"Bash({vm} *)", f'Bash("{vm}" *)']


PROTECTED_MARKERS = (".vmodel/state", ".vmodel/evidence", ".vmodel/config.json", ".vmodel/devkit.lock", "keys")


def detect_conflicts(settings: dict) -> list[str]:
    out: list[str] = []
    perms = settings.get("permissions") if isinstance(settings.get("permissions"), dict) else {}
    for rule in perms.get("allow", []) or []:
        if not isinstance(rule, str):
            continue
        r = rule.replace("\\", "/")
        if rule in ("Edit", "Write", "Edit(*)", "Edit(**)", "Write(**)") or any(m in r for m in PROTECTED_MARKERS[:4]):
            out.append(f"permissions.allow has '{rule}' which overlaps VModel-protected paths "
                       "(deny rules still win, but review it)")
    if perms.get("defaultMode") == "bypassPermissions":
        out.append("permissions.defaultMode is bypassPermissions: permission prompts are skipped; the VModel guard hook "
                   "still runs but review whether this is intended")
    if settings.get("disableAllHooks") is True:
        out.append("disableAllHooks is true: the VModel guard hook will NOT run (protection reduced to deny rules)")
    for key in (settings.get("enabledPlugins") or {}):
        if key.startswith("vmodel@") and key != "vmodel@vmodel-devkit":
            out.append(f"enabledPlugins already has {key} from another marketplace")
    hooks = settings.get("hooks") or {}
    if isinstance(hooks, dict) and hooks.get("PreToolUse"):
        out.append("project settings already define PreToolUse hooks; they run alongside the VModel guard "
                   "(any deny wins)")
    return out


def install_claude(root: Path, *, claude_md_import: bool = False, enable_plugin: Path | None = None) -> dict:
    root = root.resolve()
    project = Project(root)
    if not project.config_path.exists():
        raise SetupError("run 'vmodel init' first (.vmodel/config.json missing)")
    record_path = project.vdir / "install-record.json"
    if record_path.exists():
        raise SetupError("already installed (.vmodel/install-record.json exists); run 'vmodel uninstall' first")
    settings_path = root / ".claude" / "settings.json"
    settings: dict[str, Any] = {}
    existed = settings_path.exists()
    backup = None
    if existed:
        try:
            settings = load_json(settings_path, ".claude/settings.json")
        except ArtifactError as exc:
            raise SetupError(f"existing .claude/settings.json is not valid JSON; not touching it: {exc}") from None
        if not isinstance(settings, dict):
            raise SetupError(".claude/settings.json is not a JSON object; not touching it")
        backup_dir = project.vdir / "install" / "backup"
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup = backup_dir / f"settings.json.{utc_now().replace(':', '').replace('.', '')}"
        shutil.copy2(settings_path, backup)
    conflicts = detect_conflicts(settings)
    perms = settings.setdefault("permissions", {})
    if not isinstance(perms, dict):
        raise SetupError("settings.permissions is not an object; not touching it")
    deny = perms.setdefault("deny", [])
    added = [r for r in protected_deny_rules(root) if r not in deny]
    deny.extend(added)
    allow = perms.setdefault("allow", [])
    added_allow = [r for r in validator_allow_rules() if r not in allow]
    allow.extend(added_allow)
    added_plugin: dict[str, Any] = {}
    if enable_plugin is not None:
        mk = settings.setdefault("extraKnownMarketplaces", {})
        ep = settings.setdefault("enabledPlugins", {})
        if "vmodel-devkit" not in mk:
            mk["vmodel-devkit"] = {"source": {"source": "directory", "path": str(enable_plugin.resolve())}}
            added_plugin["marketplace"] = True
        if "vmodel@vmodel-devkit" not in ep:
            ep["vmodel@vmodel-devkit"] = True
            added_plugin["enabled"] = True
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(settings_path, settings)

    md_change = None
    if claude_md_import:
        md = root / "CLAUDE.md"
        if md.exists():
            text = read_text(md, "CLAUDE.md")
            if IMPORT_LINE not in text.splitlines():
                sep = "" if text.endswith("\n") or not text else "\n"
                write_text(md, text + sep + "\n" + IMPORT_LINE + "\n")
                md_change = "appended"
        else:
            write_text(md, IMPORT_LINE + "\n")
            md_change = "created"
    record = {
        "schema": "vmodel.install/1", "installed_at": utc_now(), "validator_version": VERSION,
        "plugin_root": str(plugin_root()), "settings_existed": existed, "settings_backup": str(backup) if backup else None,
        "added_deny": added, "added_allow": added_allow, "added_plugin": added_plugin, "claude_md": md_change, "conflicts": conflicts,
    }
    write_json(record_path, record)
    return {**record, "register_commands": register_commands(enable_plugin)}


def register_commands(marketplace_dir: Path | None) -> list[str]:
    mk = str(marketplace_dir.resolve()) if marketplace_dir else "<path-to>/dist"
    return [
        f"claude plugin marketplace add \"{mk}\" --scope project",
        "claude plugin install vmodel@vmodel-devkit --scope project",
        f"# or, session only: claude --plugin-dir \"{plugin_root()}\"",
    ]


def uninstall(root: Path, *, purge: bool = False) -> dict:
    root = root.resolve()
    project = Project(root)
    record_path = project.vdir / "install-record.json"
    done: list[str] = []
    if record_path.exists():
        record = load_json(record_path, "install-record.json")
        settings_path = root / ".claude" / "settings.json"
        if settings_path.exists():
            settings = load_json(settings_path, ".claude/settings.json")
            perms = settings.get("permissions") or {}
            deny = perms.get("deny") or []
            perms["deny"] = [r for r in deny if r not in record.get("added_deny", [])]
            if not perms["deny"]:
                perms.pop("deny")
            if "allow" in perms:
                perms["allow"] = [r for r in perms["allow"] if r not in record.get("added_allow", [])]
                if not perms["allow"]:
                    perms.pop("allow")
            if not perms:
                settings.pop("permissions", None)
            ap = record.get("added_plugin") or {}
            if ap.get("marketplace"):
                (settings.get("extraKnownMarketplaces") or {}).pop("vmodel-devkit", None)
                if settings.get("extraKnownMarketplaces") == {}:
                    settings.pop("extraKnownMarketplaces")
            if ap.get("enabled"):
                (settings.get("enabledPlugins") or {}).pop("vmodel@vmodel-devkit", None)
                if settings.get("enabledPlugins") == {}:
                    settings.pop("enabledPlugins")
            if not settings and not record.get("settings_existed"):
                settings_path.unlink()
                try:
                    settings_path.parent.rmdir()
                except OSError:
                    pass
                done.append("removed .claude/settings.json (created by install)")
            else:
                write_json(settings_path, settings)
                done.append("removed VModel entries from .claude/settings.json")
        md = root / "CLAUDE.md"
        if record.get("claude_md") and md.exists():
            text = read_text(md, "CLAUDE.md")
            if record["claude_md"] == "created" and text.strip() == IMPORT_LINE:
                md.unlink()
                done.append("removed CLAUDE.md (created by install)")
            else:
                lines = text.split("\n")
                idx = [i for i, ln in enumerate(lines) if ln == IMPORT_LINE]
                if idx:
                    i = idx[-1]
                    del lines[i]
                    if i > 0 and lines[i - 1] == "" and (i >= len(lines) or lines[i] == ""):
                        del lines[i - 1]
                    write_text(md, "\n".join(lines))
                    done.append("removed import line from CLAUDE.md")
        record_path.unlink()
    if purge:
        key = None
        try:
            key = project.key_path()
        except (ArtifactError, KeyError):
            pass
        shutil.rmtree(project.vdir, ignore_errors=True)
        if key and key.exists():
            key.unlink()
        anchor = anchor_path(root)
        if anchor.exists():
            anchor.unlink()
        done.append("purged .vmodel/, its signing key and ledger anchor")
    return {"done": done}


def new_work_item(project: Project, title: str, request: str, profile: str = "STANDARD") -> dict:
    if profile != "STANDARD":
        raise SetupError(f"profile {profile} is not implemented in this DevKit version (MVP supports STANDARD only)")
    existing = project.work_items()
    n = max([int(w.split("-")[1]) for w in existing] or [0]) + 1
    wi = f"WI-{n:03d}"
    d = project.wi_root / wi
    (d / "reviews").mkdir(parents=True, exist_ok=False)
    doc = {"id": wi, "title": title, "request": request, "profile": profile, "created_at": utc_now()}
    errs = validate(doc, load_schema("workitem"))
    if errs:
        raise SetupError("; ".join(errs))
    write_json(d / "workitem.json", doc)
    return doc


def next_id(project: Project, kind: str, count: int = 1) -> list[str]:
    from .gates import collect_ids, load_artifacts

    used: list[int] = []
    for wi in project.work_items():
        arts, _ = load_artifacts(project, wi)
        for i in collect_ids(arts):
            if i.startswith(kind + "-") and i.count("-") == 1:
                try:
                    used.append(int(i.split("-")[1]))
                except ValueError:
                    pass
        if kind in ("ISSUE", "ASM"):
            rq = arts.get("requirements.json") or {}
            key = "open_issues" if kind == "ISSUE" else "assumptions"
            for it in rq.get(key) or []:
                if isinstance(it, dict) and str(it.get("id", "")).startswith(kind + "-"):
                    try:
                        used.append(int(str(it["id"]).split("-")[1]))
                    except ValueError:
                        pass
    start = max(used or [0]) + 1
    return [f"{kind}-{start + i:03d}" for i in range(count)]


def env_summary() -> dict:
    return {"python": sys.version.split()[0], "executable": sys.executable, "vmodel_home": str(vmodel_home()),
            "plugin_root": str(plugin_root()), "os": os.name}


def dump(obj: Any) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False)

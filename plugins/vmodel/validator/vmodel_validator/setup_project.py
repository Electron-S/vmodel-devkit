"""Project initialisation, Claude settings merge (install) and removal (uninstall).

Only project files are touched (.vmodel/, .claude/settings.json, optionally
CLAUDE.md). Global Claude configuration is never modified (DECISIONS D10).
"""
from __future__ import annotations

import ast
import json
import os
import posixpath
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

from . import VERSION
from .gates import load_schema
from .hashing import hash_obj, sha256_bytes, sha256_file
from .integrity import RELEASE_MANIFEST, check_self, plugin_root
from .ledger import Ledger, anchor_path, create_key
from .project import VMODEL_DIR, Project, vmodel_home
from .runner import utc_now
from .schema_lite import validate
from .textio import ArtifactError, load_json, read_text, write_bytes, write_json, write_text

DATA = Path(__file__).resolve().parent / "data"
IMPORT_LINE = "@.vmodel/VMODEL.md"
BUILD_CONFIG = ["pyproject.toml", "setup.cfg", "setup.py", "pytest.ini", "tox.ini", "requirements*.txt",
                "conftest.py", "tests/conftest.py"]


class SetupError(Exception):
    pass


# ---------------------------------------------------------------- test commands (0.2.0, G6, REQ-G6-27/28)
UNIT_ARGV = ["{python}", "-m", "pytest", "-q", "-p", "no:cacheprovider", "--junitxml={junit}"]
DEFAULT_INTEGRATION_DIR = "tests/integration"
INTEGRATION_TIMEOUT_S = 900


def integration_argv(rel: str) -> list[str]:
    return ["{python}", "-m", "pytest", "-q", "-p", "no:cacheprovider", rel, "--junitxml={junit}"]


def _glob_roots(globs: list[str]) -> list[str]:
    roots = []
    for pat in globs:
        parts = []
        for part in pat.replace("\\", "/").split("/"):
            if any(ch in part for ch in "*?["):
                break
            parts.append(part)
        roots.append("/".join(parts) + "/" if parts else "")
    return roots


def _count_test_functions(files: list[Path]) -> int:
    n = 0
    for f in files:
        try:
            tree = ast.parse(f.read_bytes(), filename=str(f))
        except (SyntaxError, ValueError, OSError, RecursionError, MemoryError):
            continue
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test"):
                n += 1
            elif isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
                n += sum(1 for m in node.body if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))
                         and m.name.startswith("test"))
    return n


def integration_path_problems(root: Path, given: str, test_globs: list[str]) -> tuple[str, list[str]]:
    """Check a user-given integration test path: it must exist inside the project under the configured tests paths,
    hold at least one test function, and not be the unit command's whole scope. Nothing is ever created (D3)."""
    raw = given.replace("\\", "/").strip()
    rel = posixpath.normpath(raw) if raw else ""  # tests/integration/.. and tests/. are tests (review F11)
    root = root.resolve()
    if not rel or rel == "." or os.path.isabs(given) or rel == ".." or rel.startswith("../"):
        return rel, [f"integration test path {given!r} must be a relative path inside the project"]
    path = (root / rel).resolve()
    try:
        path.relative_to(root)
    except ValueError:
        return rel, [f"integration test path {given!r} is outside the project"]
    if not path.exists():
        return rel, [f"integration test path {rel} does not exist (write the integration tests first; the DevKit "
                     "never creates test paths or tests)"]
    roots = _glob_roots(test_globs)
    if any(r in ("", rel + "/") or r.startswith(rel + "/") for r in roots):
        return rel, [f"integration test path {rel} is the same scope as the unit test command (it would run the unit "
                     "tests too); use a separate folder such as tests/integration"]
    if not any(rel.startswith(r) or (rel + "/").startswith(r) for r in roots):
        return rel, [f"integration test path {rel} is not under the configured tests paths {test_globs} (G4 would not "
                     "check those files)"]
    files = [path] if path.is_file() else [f for f in sorted(path.rglob("*.py")) if "__pycache__" not in f.parts]
    if _count_test_functions(files) == 0:
        return rel, [f"integration test path {rel} has no test function (def test_...): only existing tests are "
                     "registered"]
    return rel, []


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
                 tests: list[str] | None = None, lint: str = "auto", allow_syntax_only: bool = False,
                 integration_tests: str | None = None) -> dict:
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
    test_globs = tests or ["tests/**/*.py"]
    integration, integration_note = None, None
    if integration_tests is not None:  # the user named it: refuse rather than register something that is not there
        rel, probs = integration_path_problems(root, integration_tests, test_globs)
        if probs:
            raise SetupError("--integration-tests: " + "; ".join(probs))
        integration = rel
    elif (root / DEFAULT_INTEGRATION_DIR).is_dir():
        rel, probs = integration_path_problems(root, DEFAULT_INTEGRATION_DIR, test_globs)
        if probs:
            integration_note = f"{DEFAULT_INTEGRATION_DIR} not registered: " + "; ".join(probs)
        else:
            integration = rel
    py = _detect_python(root, python)
    lint_cfg = detect_lint(root, py, lint)
    unit_argv = list(UNIT_ARGV)
    if integration:
        unit_argv.insert(len(unit_argv) - 1, f"--ignore={integration}")
    config = {
        "schema": "vmodel.config/1",
        "project_id": uuid.uuid4().hex,
        "default_profile": "STANDARD",
        "language": "python",
        "python": py,
        "paths": {"source": source, "tests": test_globs, "build_config": BUILD_CONFIG},
        "unit_test": {"argv": unit_argv, "timeout_s": 600},
        "static_analysis": {"lint": lint_cfg, "on_missing_lint": "syntax-only" if allow_syntax_only else "block"},
    }
    if integration:
        config["integration_test"] = {"argv": integration_argv(integration), "timeout_s": INTEGRATION_TIMEOUT_S}
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
    return {"project": str(root), "config": config, "lock": lock, "key": str(project.key_path()),
            "integration_note": integration_note}


def _is_pytest(argv: list[str]) -> bool:
    if not argv:
        return False
    if Path(argv[0]).name.lower().split(".")[0] in ("pytest", "py.test"):
        return True
    return any(a == "-m" and i + 1 < len(argv) and argv[i + 1] == "pytest" for i, a in enumerate(argv))


def plan_configure_tests(project: Project, integration: str, timeout_s: int = INTEGRATION_TIMEOUT_S) -> dict:
    """REQ-G6-28: the config change that adds integration_test to an existing project (read-only)."""
    raw = project.config_path.read_bytes()
    cfg = load_json(project.config_path, ".vmodel/config.json")
    if not isinstance(cfg, dict):
        raise SetupError(".vmodel/config.json is not a JSON object")
    rel, probs = integration_path_problems(project.root, integration, cfg["paths"]["tests"])
    if probs:
        raise SetupError("; ".join(probs))
    if not isinstance(timeout_s, int) or timeout_s <= 0:
        raise SetupError("--timeout must be a positive number of seconds")
    unit = cfg.get("unit_test") if isinstance(cfg.get("unit_test"), dict) else {}
    argv = list(unit.get("argv") or [])
    if not _is_pytest(argv):
        raise SetupError("unit_test.argv is not a pytest command; edit .vmodel/config.json by hand so the unit and "
                         "integration commands run different tests")
    if rel in argv or any(a.rstrip("/") == rel for a in argv):
        raise SetupError(f"unit_test.argv names {rel} explicitly; edit .vmodel/config.json by hand")
    ignore = f"--ignore={rel}"
    if ignore not in argv:
        at = next((i for i, a in enumerate(argv) if "{junit}" in a), len(argv))
        argv.insert(at, ignore)
    new = {**cfg, "unit_test": {**unit, "argv": argv},
           "integration_test": {"argv": integration_argv(rel), "timeout_s": timeout_s}}
    errs = validate(new, load_schema("config"))
    if errs:
        raise SetupError("resulting config invalid: " + "; ".join(errs))
    return {"integration": rel, "old": cfg, "new": new, "old_sha256": sha256_bytes(raw),
            "unit_argv_before": unit.get("argv"), "unit_argv_after": argv,
            "integration_test": new["integration_test"], "replaces": cfg.get("integration_test")}


def apply_configure_tests(project: Project, plan: dict) -> dict:
    """Signed ledger record first, then the config file (the config never changes without a record)."""
    if sha256_file(project.config_path) != plan["old_sha256"]:
        raise SetupError(".vmodel/config.json changed since the plan was shown; run the command again")
    data = (json.dumps(plan["new"], indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    entry = Ledger(project).append({"type": "config", "at": utc_now(), "change": "integration_test",
                                    "integration_path": plan["integration"], "old_config_sha256": plan["old_sha256"],
                                    "new_config_sha256": sha256_bytes(data),
                                    "integration_test_sha256": hash_obj(plan["integration_test"]),
                                    "by": "user (tty)"})
    write_bytes(project.config_path, data)
    return {"record": entry.id, "config_sha256": sha256_bytes(data)}


def repin_lock(project: Project, reason: str) -> dict:
    integ = check_self()
    if not integ.ok:
        raise SetupError("validator integrity check failed: " + "; ".join(integ.problems))
    old = project.lock()
    lock = {**old, "validator_version": VERSION, "core_hash": integ.core_hash, "mode": integ.mode,
            "plugin_root": str(plugin_root()), "pinned_at": utc_now()}
    # the signed ledger record first: the lock never changes without one (0.1.5; before, a failed append left the
    # lock re-pinned with no record)
    Ledger(project).append({"type": "lock", "at": utc_now(), "reason": reason, "old_core_hash": old.get("core_hash"),
                            "new_core_hash": integ.core_hash, "by": "user (tty)"})
    write_json(project.lock_path, lock)
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
        "Edit(/.vmodel/install/**)",  # settings backups the user may restore from (0.1.5)
        *home_rules,
        abs_rule("Edit", plugin_root()),
    ]


def validator_allow_rules(plugin: Path | None = None) -> list[str]:
    """Allow the validator CLI without a prompt. Safe: user-only subcommands are refused by the guard hook/TTY."""
    vm = ((plugin or plugin_root()) / "bin" / "vmodel").resolve().as_posix()
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
        try:
            prev = load_json(record_path, "install-record.json")
        except ArtifactError:
            prev = None
        prev = prev if isinstance(prev, dict) else {}
        prev_root = prev.get("plugin_root")
        if isinstance(prev_root, str) and (prev_root != str(plugin_root()) or prev.get("validator_version") != VERSION):
            vm = plugin_root() / "bin" / "vmodel"
            raise SetupError(f"this project was installed by validator {prev.get('validator_version')} from {prev_root}. "
                             f"To upgrade, run '\"{vm}\" lock --accept-current' in a terminal: it re-pins the "
                             "validator and moves the DevKit permission rules to this release without a gap")
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


# ---------------------------------------------------------------- upgrade (0.1.5, DECISIONS D38)
# The permission rules that install writes name the release directory (deny on the plugin root, allow for its
# bin/vmodel). Re-pinning a new release moves the DevKit-owned rules -- exactly the strings listed in the install
# record (added_deny / added_allow) -- to the new release: new rules are added first, the lock is re-pinned, and only
# then are the previous release's rules removed, so the deny layer never lacks a rule for the pinned release.
RULE_KINDS = ("deny", "allow")


def _read_settings(path: Path) -> tuple[dict, bytes | None]:
    """The project settings as a dict (empty if missing). Refuses anything it would have to guess about."""
    if not path.exists():
        return {}, None
    try:
        raw = path.read_bytes()
        doc = load_json(path, ".claude/settings.json")
    except OSError as exc:
        raise SetupError(f"cannot read .claude/settings.json ({exc.__class__.__name__}: {exc}); not touching it") from None
    except ArtifactError as exc:
        raise SetupError(f"existing .claude/settings.json is not valid JSON; not touching it: {exc}") from None
    if not isinstance(doc, dict):
        raise SetupError(".claude/settings.json is not a JSON object; not touching it")
    perms = doc.get("permissions", {})
    if not isinstance(perms, dict):
        raise SetupError("settings.permissions is not an object; not touching it")
    for kind in RULE_KINDS:
        if not isinstance(perms.get(kind, []), list):
            raise SetupError(f"settings.permissions.{kind} is not a list; not touching it")
    return doc, raw


def _read_record(path: Path) -> tuple[dict, bytes]:
    try:
        raw = path.read_bytes()
        rec = load_json(path, "install-record.json")
    except OSError as exc:
        raise SetupError(f"cannot read .vmodel/install-record.json ({exc.__class__.__name__}: {exc}); not touching "
                         "anything") from None
    except ArtifactError as exc:
        raise SetupError(f".vmodel/install-record.json is not valid JSON; not touching anything: {exc}") from None
    if not isinstance(rec, dict):
        raise SetupError(".vmodel/install-record.json is not a JSON object; not touching anything")
    for key in ("added_deny", "added_allow", "declined_allow"):
        owned = rec.get(key)
        if owned is None:
            continue  # 0.1.0/0.1.1 records have no added_allow; declined_allow exists only when needed
        if not isinstance(owned, list) or not all(isinstance(r, str) for r in owned):
            raise SetupError(f".vmodel/install-record.json {key} is not a list of rules; not touching anything")
    return rec, raw


def _digest(raw: bytes | None) -> str | None:
    return None if raw is None else sha256_bytes(raw)


def plan_settings_sync(root: Path) -> dict | None:
    """What a re-pin by this release changes in .claude/settings.json and the install record (read-only).

    None when the project was never installed (init only): settings are then left alone.
    """
    root = root.resolve()
    vdir = root / VMODEL_DIR
    record_path = vdir / "install-record.json"
    if not record_path.exists():
        return None
    record, rec_raw = _read_record(record_path)
    settings_path = root / ".claude" / "settings.json"
    settings, raw = _read_settings(settings_path)
    perms = settings.get("permissions", {})
    generated = {"deny": protected_deny_rules(root), "allow": validator_allow_rules()}
    plan: dict[str, Any] = {
        "settings_path": str(settings_path), "settings_sha256": _digest(raw), "record_sha256": _digest(rec_raw),
        "from_plugin_root": record.get("plugin_root"), "from_version": record.get("validator_version"),
        "to_plugin_root": str(plugin_root()), "to_version": VERSION,
    }
    # Deny rules are the protection floor and are always (re)added. An allow rule is a grant: if the DevKit had added
    # the previous release's rule in the same position and the user removed it, the new release's counterpart is not
    # granted again (review 5). Records without added_allow (0.1.0/0.1.1) never owned one, so nothing was removed.
    # The decision is kept in the record (declined_allow) so that later upgrades do not grant it either.
    prev_root = record.get("plugin_root")
    prev_allow = validator_allow_rules(Path(prev_root)) if isinstance(prev_root, str) and prev_root else None
    declined = set(record.get("declined_allow") or [])
    plan["keep_removed_allow"] = []
    for kind in RULE_KINDS:
        current = perms.get(kind, [])
        owned = record.get(f"added_{kind}") or []
        add = []
        for i, r in enumerate(generated[kind]):
            if r in current:
                continue
            # withheld only while the previous rule is still gone (a rule the user added back is a fresh grant)
            if kind == "allow" and prev_allow is not None and prev_allow[i] not in current and (
                    prev_allow[i] in declined or prev_allow[i] in owned):
                plan["keep_removed_allow"].append(r)
                continue
            add.append(r)
        plan[f"add_{kind}"] = add
        plan[f"remove_{kind}"] = [r for r in dict.fromkeys(owned) if r not in generated[kind] and r in current]
        # ownership after the upgrade, in the order the rules will have in settings (as install records it)
        keep = {r for r in generated[kind] if r in add or (r in owned and r in current)}
        final = _remove_once(current, plan[f"remove_{kind}"]) + add
        plan[f"owned_{kind}"] = [r for r in dict.fromkeys(x for x in final if isinstance(x, str)) if r in keep]
    plan["settings_change"] = any(plan[f"{op}_{kind}"] for op in ("add", "remove") for kind in RULE_KINDS)
    plan["record_change"] = bool(
        plan["settings_change"] or "upgrade_pending" in record
        or any(plan[f"owned_{kind}"] != (record.get(f"added_{kind}") or []) for kind in RULE_KINDS)
        or (record.get("declined_allow") or []) != plan["keep_removed_allow"]
        or record.get("plugin_root") != plan["to_plugin_root"] or record.get("validator_version") != VERSION)
    return plan


def _plan_identity(plan: dict | None) -> Any:
    if plan is None:
        return None
    return {k: v for k, v in plan.items() if k != "settings_path"}


def _remove_once(rules: list, drop: list[str]) -> list:
    """Remove one occurrence of each dropped rule (a user's own copy of the same string, if any, stays)."""
    out = list(rules)
    for r in drop:
        if r in out:
            out.remove(r)
    return out


def _restore(snapshot: dict[Path, bytes | None], lock_path: Path, settings_path: Path,
             record_path: Path) -> list[str]:
    """Put files back, the lock first. The install record (DevKit ownership) goes back only once settings did, so
    rules left in settings by a failed restore stay owned by the DevKit (review 3)."""
    problems = []
    settings_restored = True
    for path in (lock_path, settings_path, record_path):
        if path == record_path and not settings_restored:
            problems.append(f"{path}: kept on purpose (it still lists the DevKit rules left in .claude/settings.json)")
            continue
        data = snapshot[path]
        try:
            current = path.read_bytes() if path.exists() else None
            if current == data:
                continue
            if data is None:
                path.unlink()
            else:
                write_bytes(path, data)
        except OSError as exc:
            problems.append(f"{path}: {exc}")
            if path == settings_path:
                settings_restored = False
    return problems


_UNSET: Any = object()


class _no_interrupts:
    """Ignore SIGINT while a rollback runs (main thread only; elsewhere a no-op)."""

    def __enter__(self):
        import signal
        try:
            self._prev = signal.signal(signal.SIGINT, signal.SIG_IGN)
        except (ValueError, OSError, AttributeError):
            self._prev = None
        return self

    def __exit__(self, *exc):
        import signal
        if self._prev is not None:
            signal.signal(signal.SIGINT, self._prev)


def upgrade_project(project: Project, reason: str, plan: dict | None = _UNSET) -> dict:
    """Re-pin this release and move the DevKit permission rules to it (USER ONLY; the CLI asks on a TTY first).

    Order: checks (no writes) -> back up -> record ownership -> add the new rules -> re-pin (signed ledger record,
    then lock) -> remove the previous release's rules. `plan` is what the user was shown (None = no settings change
    shown); if the files no longer give the same plan, nothing is done. A failure (or Ctrl-C) before the ledger
    record exists restores settings, install record and lock byte for byte. Once the ledger holds a new record, or
    cannot be read, nothing is rolled back: settings keep the old and the new rules (no gap whichever core is
    pinned) and running the command again finishes.
    """
    root = project.root.resolve()
    integ = check_self()
    if not integ.ok:
        raise SetupError("validator integrity check failed: " + "; ".join(integ.problems))
    entries_before = len(Ledger(project).entries())  # key, signatures, chain, head and anchor, before any write
    current = plan_settings_sync(root)
    if plan is not _UNSET and _plan_identity(current) != _plan_identity(plan):
        raise SetupError(".claude/settings.json or the install record changed after the plan was shown; nothing was "
                         "changed. Run the command again")
    plan = current
    settings_path = root / ".claude" / "settings.json"
    record_path = project.vdir / "install-record.json"
    lock_path = project.lock_path
    snapshot = {p: (p.read_bytes() if p.exists() else None) for p in (settings_path, record_path, lock_path)}
    writes = bool(plan and plan["record_change"])
    backup: Path | None = None
    step = "backup"
    try:
        if plan is not None and writes:
            base = project.vdir / "install" / "backup"
            stamp = utc_now().replace(":", "").replace(".", "").replace("-", "")
            backup = base / f"upgrade-{stamp}"
            n = 1
            while backup.exists():
                n += 1
                backup = base / f"upgrade-{stamp}-{n}"
            backup.mkdir(parents=True)
            for path, name in ((settings_path, "settings.json"), (record_path, "install-record.json"),
                               (lock_path, "devkit.lock.json")):
                data = snapshot[path]
                if data is not None:
                    write_bytes(backup / name, data)
            # ownership first: if the process dies between the two writes, a re-run still knows the new rules are
            # the DevKit's (a rule recorded but not yet in settings is simply added again)
            step = "install record"
            record, _ = _read_record(record_path)
            for kind in RULE_KINDS:  # until the old rules are gone, the DevKit owns old + new
                owned = record.get(f"added_{kind}") or []
                record[f"added_{kind}"] = owned + [r for r in plan[f"add_{kind}"] if r not in owned]
            record["upgrade_pending"] = {"from_plugin_root": plan["from_plugin_root"],
                                         "to_plugin_root": plan["to_plugin_root"], "started_at": utc_now(),
                                         "backup": str(backup)}
            write_json(record_path, record)
            step = "settings"
            if plan["add_deny"] or plan["add_allow"]:
                settings, _ = _read_settings(settings_path)
                perms = settings.setdefault("permissions", {})
                for kind in RULE_KINDS:
                    perms.setdefault(kind, []).extend(plan[f"add_{kind}"])
                write_json(settings_path, settings)
        step = "re-pin"
        lock = repin_lock(project, reason)
    except BaseException as exc:  # Ctrl-C while waiting for the ledger lock must roll back too (review 1)
        what = "interrupted" if isinstance(exc, KeyboardInterrupt) else f"{exc.__class__.__name__}: {exc}"
        with _no_interrupts():  # a second Ctrl-C must not cut the rollback short
            try:
                new = Ledger(project).entries()[entries_before:]
                ours = [e for e in new if e.record.get("type") == "lock" and e.record.get("reason") == reason
                        and e.record.get("new_core_hash") == integ.core_hash]
                entries_after: int | str = entries_before + len(new)
            except Exception as lexc:  # noqa: BLE001 - reported, never guessed
                ours, entries_after = None, f"unreadable ({lexc})"
            # only our own lock record means the re-pin may be recorded; others' records do not (re-review)
            if ours == []:
                problems = _restore(snapshot, lock_path, settings_path, record_path)
                msg = f"upgrade failed at the {step} step ({what}). "
                if problems:
                    msg += f"Could not restore {'; '.join(problems)}; copies of the previous files are in {backup}"
                else:
                    msg += "Rolled back: .claude/settings.json, the install record and the lock are as before"
                raise SetupError(msg) from exc
        locked = lock_path.read_bytes() if lock_path.exists() else None
        raise SetupError(
            f"upgrade failed at the {step} step ({what}) after the ledger changed (entries: {entries_before} before, "
            f"{entries_after} now): the re-pin is or may be recorded, so nothing was rolled back. The lock is "
            f"{'unchanged' if locked == snapshot[lock_path] else 'updated'}; .claude/settings.json keeps the previous "
            "and the new DevKit rules (no protection gap). Fix the cause and run 'vmodel lock --accept-current' "
            "again to finish") from exc
    result: dict[str, Any] = {"lock": lock, "plan": plan, "backup": str(backup) if backup else None,
                              "complete": True, "error": None}
    if plan is not None and writes:
        try:
            if plan["remove_deny"] or plan["remove_allow"]:
                settings, _ = _read_settings(settings_path)
                perms = settings.setdefault("permissions", {})
                for kind in RULE_KINDS:
                    if plan[f"remove_{kind}"]:
                        perms[kind] = _remove_once(perms.get(kind, []), plan[f"remove_{kind}"])
                write_json(settings_path, settings)
            record, _ = _read_record(record_path)
            record.pop("upgrade_pending", None)
            history = list(record["upgrades"]) if isinstance(record.get("upgrades"), list) else []
            history.append({"at": utc_now(), "from_version": plan["from_version"],
                            "from_plugin_root": plan["from_plugin_root"], "to_version": VERSION,
                            "to_plugin_root": plan["to_plugin_root"], "backup": str(backup),
                            **{f"{op}_{kind}": plan[f"{op}_{kind}"] for op in ("add", "remove") for kind in RULE_KINDS},
                            "keep_removed_allow": plan["keep_removed_allow"]})
            record.update({"validator_version": VERSION, "plugin_root": plan["to_plugin_root"],
                           "added_deny": plan["owned_deny"], "added_allow": plan["owned_allow"], "upgrades": history})
            if plan["keep_removed_allow"]:
                record["declined_allow"] = plan["keep_removed_allow"]
            else:
                record.pop("declined_allow", None)
            write_json(record_path, record)
        except BaseException as exc:  # the re-pin is recorded: never roll back from here, a re-run finishes
            what = "interrupted" if isinstance(exc, KeyboardInterrupt) else f"{exc.__class__.__name__}: {exc}"
            result["complete"] = False
            result["error"] = (f"the validator was re-pinned, but removing the previous release's DevKit rules failed "
                               f"({what}). .claude/settings.json keeps the old and the new rules (no protection gap); "
                               "run 'vmodel lock --accept-current' again to finish")
    return result


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

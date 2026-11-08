"""Validator Core integrity (SPEC section 5.6, DECISIONS D09).

The core = validator/, hooks/ and bin/ of the plugin. Its hash is pinned in
the project's .vmodel/devkit.lock.json. A release copy also carries
RELEASE_MANIFEST.json with per-file hashes of the whole plugin.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from . import VERSION
from .hashing import hash_obj, sha256_file
from .textio import ArtifactError, load_json

CORE_DIRS = ("validator", "hooks", "bin")
SKIP_DIRS = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
SKIP_SUFFIXES = (".pyc", ".pyo")
RELEASE_MANIFEST = "RELEASE_MANIFEST.json"


def plugin_root() -> Path:
    # .../plugins/vmodel/validator/vmodel_validator/integrity.py -> .../plugins/vmodel
    return Path(__file__).resolve().parents[2]


def _walk(root: Path, top: Path) -> dict[str, str]:
    files: dict[str, str] = {}
    if not top.is_dir():
        return files
    for dirpath, dirnames, filenames in os.walk(top):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for name in sorted(filenames):
            if name.endswith(SKIP_SUFFIXES) or name == ".DS_Store":
                continue
            p = Path(dirpath) / name
            files[p.relative_to(root).as_posix()] = sha256_file(p)
    return files


def core_files(root: Path | None = None) -> dict[str, str]:
    root = root or plugin_root()
    files: dict[str, str] = {}
    for d in CORE_DIRS:
        files.update(_walk(root, root / d))
    return files


def all_plugin_files(root: Path | None = None) -> dict[str, str]:
    root = root or plugin_root()
    files = _walk(root, root)
    files.pop(RELEASE_MANIFEST, None)
    return files


def core_hash(root: Path | None = None) -> str:
    return hash_obj(core_files(root))


@dataclass
class IntegrityReport:
    ok: bool
    version: str
    core_hash: str
    mode: str  # "release" or "dev"
    problems: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"ok": self.ok, "version": self.version, "core_hash": self.core_hash, "mode": self.mode,
                "problems": list(self.problems)}


def check_self(root: Path | None = None) -> IntegrityReport:
    """Recompute the core hash and compare against RELEASE_MANIFEST.json if present."""
    root = root or plugin_root()
    current = core_files(root)
    chash = hash_obj(current)
    manifest_path = root / RELEASE_MANIFEST
    if not manifest_path.exists():
        return IntegrityReport(True, VERSION, chash, "dev")
    problems: list[str] = []
    try:
        manifest = load_json(manifest_path, RELEASE_MANIFEST)
    except ArtifactError as exc:
        return IntegrityReport(False, VERSION, chash, "release", [str(exc)])
    expected = manifest.get("files", {})
    if manifest.get("version") != VERSION:
        problems.append(f"release manifest version {manifest.get('version')} != code version {VERSION}")
    actual_all = all_plugin_files(root)
    for rel, h in sorted(expected.items()):
        got = actual_all.get(rel)
        if got is None:
            problems.append(f"missing release file: {rel}")
        elif got != h:
            problems.append(f"modified release file: {rel}")
    for rel in sorted(set(current) - set(expected)):
        problems.append(f"unexpected core file: {rel}")
    if manifest.get("core_hash") != chash and not problems:
        problems.append("core hash differs from release manifest")
    return IntegrityReport(not problems, VERSION, chash, "release", problems)


def check_against_lock(lock: dict, report: IntegrityReport) -> IntegrityReport:
    problems = list(report.problems)
    if lock.get("core_hash") != report.core_hash:
        problems.append(
            "validator core hash does not match .vmodel/devkit.lock.json "
            f"(locked {lock.get('core_hash')}, running {report.core_hash}); "
            "the validator was modified or a different version is running. "
            "A user must re-pin with 'vmodel lock --accept-current' in a terminal."
        )
    return IntegrityReport(not problems, report.version, report.core_hash, report.mode, problems)

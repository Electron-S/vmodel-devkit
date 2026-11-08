"""Target project layout: .vmodel/ directory, config, work items, file sets."""
from __future__ import annotations

import os
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .textio import ArtifactError, load_json

VMODEL_DIR = ".vmodel"
EXCLUDED_PARTS = {".vmodel", ".git", "__pycache__", ".venv", "venv", ".pytest_cache", "node_modules",
                  ".ruff_cache", ".mypy_cache", ".tox"}
WALK_PRUNE = {".git", ".hg", ".svn", ".vmodel", ".venv", "venv", "node_modules", ".tox", ".nox", ".pytest_cache",
              ".ruff_cache", ".mypy_cache", ".idea", ".vscode", ".eggs"}
ROOT_PRUNE = {"build", "dist"}
JUNK_FILES = {".DS_Store", "Thumbs.db", "desktop.ini"}
WI_RE = re.compile(r"^WI-\d{3,}$")
ARTIFACTS = ("workitem.json", "requirements.json", "architecture.json", "design.json", "tests.json",
             "defects.json", "change-requests.json")
SCHEMA_FOR = {
    "workitem.json": "workitem",
    "requirements.json": "requirements",
    "architecture.json": "architecture",
    "design.json": "design",
    "tests.json": "tests",
    "defects.json": "defects",
    "change-requests.json": "change_requests",
}


class ProjectError(Exception):
    pass


def vmodel_home() -> Path:
    env = os.environ.get("VMODEL_HOME")
    return Path(env).expanduser() if env else Path.home() / ".vmodel-devkit"


@dataclass
class Project:
    root: Path

    @staticmethod
    def find(start: Path | None = None) -> "Project":
        start = (start or Path.cwd()).resolve()
        for d in (start, *start.parents):
            if (d / VMODEL_DIR / "config.json").is_file():
                return Project(d)
        raise ProjectError(f"no {VMODEL_DIR}/config.json found in {start} or its parents; run 'vmodel init' first")

    # ---- paths -------------------------------------------------------
    @property
    def vdir(self) -> Path:
        return self.root / VMODEL_DIR

    @property
    def config_path(self) -> Path:
        return self.vdir / "config.json"

    @property
    def lock_path(self) -> Path:
        return self.vdir / "devkit.lock.json"

    @property
    def wi_root(self) -> Path:
        return self.vdir / "work-items"

    @property
    def state_dir(self) -> Path:
        return self.vdir / "state"

    @property
    def evidence_dir(self) -> Path:
        return self.vdir / "evidence"

    @property
    def reports_dir(self) -> Path:
        return self.vdir / "reports"

    def rel(self, path: Path) -> str:
        try:
            return path.resolve().relative_to(self.root.resolve()).as_posix()
        except ValueError:
            return path.as_posix()

    # ---- config ------------------------------------------------------
    def config(self) -> dict[str, Any]:
        return load_json(self.config_path, ".vmodel/config.json")

    def lock(self) -> dict[str, Any]:
        return load_json(self.lock_path, ".vmodel/devkit.lock.json")

    def key_path(self) -> Path:
        pid = self.config()["project_id"]
        return vmodel_home() / "keys" / f"{pid}.key"

    def python_exe(self) -> str:
        py = self.config().get("python") or sys.executable
        p = Path(py)
        if not p.is_absolute() and ("/" in py or "\\" in py):
            p = self.root / p
            return str(p)
        if p.is_absolute():
            return str(p)
        return shutil.which(py) or py

    # ---- work items --------------------------------------------------
    def work_items(self) -> list[str]:
        if not self.wi_root.is_dir():
            return []
        return sorted(p.name for p in self.wi_root.iterdir() if p.is_dir() and WI_RE.match(p.name))

    def wi_dir(self, wi: str) -> Path:
        if not WI_RE.match(wi):
            raise ProjectError(f"invalid work item id {wi!r} (expected WI-001 style)")
        d = self.wi_root / wi
        if not d.is_dir():
            raise ProjectError(f"work item {wi} does not exist")
        return d

    def artifact_path(self, wi: str, name: str) -> Path:
        return self.wi_dir(wi) / name

    def load_artifact(self, wi: str, name: str) -> tuple[Any, str | None]:
        """Return (data, error). Missing file -> (None, 'missing')."""
        path = self.artifact_path(wi, name)
        if not path.exists():
            return None, "missing"
        try:
            return load_json(path, f"{wi}/{name}"), None
        except ArtifactError as exc:
            return None, str(exc)

    # ---- code file sets ---------------------------------------------
    def _glob(self, patterns: list[str]) -> list[Path]:
        found: dict[str, Path] = {}
        for pat in patterns:
            for p in self.root.glob(pat):
                if not p.is_file():
                    continue
                rel = p.relative_to(self.root)
                if any(part in EXCLUDED_PARTS for part in rel.parts[:-1]):
                    continue
                found[rel.as_posix()] = p
        return [found[k] for k in sorted(found)]

    def source_files(self) -> list[Path]:
        return self._glob(self.config()["paths"]["source"])

    def test_files(self) -> list[Path]:
        return self._glob(self.config()["paths"]["tests"])

    def build_config_files(self) -> list[Path]:
        return self._glob(self.config()["paths"].get("build_config", []))

    def other_code_files(self) -> list[Path]:
        return self._glob(self.config()["paths"].get("other", []))

    def project_files(self) -> tuple[dict[str, Path], list[str]]:
        """Every file of the project that can influence a test run (SPEC 5.5).

        Returns ({relative path: Path}, [relative symlink paths]). Skips VCS/tool/venv directories, the .vmodel
        directory and compiled caches inside __pycache__ (the validator runs tests with its own pycache prefix).
        Any other file, including .py files hidden in __pycache__, data files and stray modules, is included.
        """
        files: dict[str, Path] = {}
        links: list[str] = []
        for dirpath, dirnames, filenames in os.walk(self.root, followlinks=False):
            d = Path(dirpath)
            keep = []
            for name in sorted(dirnames):
                full = d / name
                if full.is_symlink():
                    links.append(full.relative_to(self.root).as_posix())
                    continue
                if name in WALK_PRUNE or (d == self.root and name in ROOT_PRUNE):
                    continue
                keep.append(name)
            dirnames[:] = keep
            in_pycache = d.name == "__pycache__"
            for name in sorted(filenames):
                full = d / name
                rel = full.relative_to(self.root).as_posix()
                if full.is_symlink():
                    links.append(rel)
                    continue
                if name in JUNK_FILES or (in_pycache and name.endswith((".pyc", ".pyo"))):
                    continue
                files[rel] = full
        return dict(sorted(files.items())), sorted(links)

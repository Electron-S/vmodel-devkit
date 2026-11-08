"""Build an immutable, hash-pinned release of the vmodel plugin (DECISIONS D09).

    python scripts/release.py [--out dist] [--force] [--no-record]

Creates:
  <out>/vmodel-<version>/                 copy of plugins/vmodel (+ RELEASE_MANIFEST.json), files read-only
  <out>/.claude-plugin/marketplace.json   local marketplace "vmodel-devkit" pointing at that copy
  releases/vmodel-<version>.json          hash record kept in the DevKit repository (trusted reference)
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "plugins" / "vmodel"
sys.path.insert(0, str(SRC / "validator"))
sys.dont_write_bytecode = True

from vmodel_validator import VERSION  # noqa: E402
from vmodel_validator.integrity import RELEASE_MANIFEST, all_plugin_files, core_hash  # noqa: E402


def _make_writable(path: Path) -> None:
    for p in [path, *path.rglob("*")]:
        try:
            os.chmod(p, (stat.S_IWRITE | stat.S_IREAD | (stat.S_IEXEC if p.is_dir() or os.access(p, os.X_OK) else 0)))
        except OSError:
            pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(REPO / "dist"))
    ap.add_argument("--force", action="store_true", help="replace an existing release directory")
    ap.add_argument("--no-record", action="store_true", help="do not write releases/vmodel-<ver>.json")
    args = ap.parse_args()
    out = Path(args.out).resolve()
    dest = out / f"vmodel-{VERSION}"
    if dest.exists():
        if not args.force:
            print(f"{dest} exists; releases are immutable (use --force only to rebuild the same version)")
            return 1
        _make_writable(dest)
        shutil.rmtree(dest)
    shutil.copytree(SRC, dest, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", RELEASE_MANIFEST))
    files = all_plugin_files(dest)
    manifest = {
        "name": "vmodel",
        "version": VERSION,
        "core_hash": core_hash(dest),
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "files": files,
    }
    (dest / RELEASE_MANIFEST).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    mk = out / ".claude-plugin" / "marketplace.json"
    mk.parent.mkdir(parents=True, exist_ok=True)
    mk.write_text(json.dumps({
        "name": "vmodel-devkit",
        "owner": {"name": "VModel DevKit"},
        "plugins": [{"name": "vmodel", "source": f"./vmodel-{VERSION}", "version": VERSION,
                     "description": "V-Model workflow with an independent quality gate validator"}],
    }, indent=2) + "\n", encoding="utf-8")
    for p in dest.rglob("*"):
        if p.is_file():
            mode = stat.S_IREAD | (stat.S_IEXEC if os.access(p, os.X_OK) else 0)
            os.chmod(p, mode | stat.S_IRGRP | stat.S_IROTH)
    if not args.no_record:
        rec = REPO / "releases" / f"vmodel-{VERSION}.json"
        rec.parent.mkdir(exist_ok=True)
        rec.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        print(f"record: {rec}")
    print(f"release: {dest}")
    print(f"core hash: {manifest['core_hash']}")
    print(f"marketplace: {mk}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

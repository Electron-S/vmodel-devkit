"""v0.2.0 release candidate check (no model calls, read-only).

    python3 -I test-results/v0.2.0/release_check.py <out.json>

Independent of the validator's own integrity module: hashes are recomputed here with hashlib
(same definition as the record: sha256 over raw bytes, core hash = sha256 of canonical JSON of
the validator/, hooks/, bin/ file map). Each release copy is also asked for its own self-check
(`bin/vmodel version`). Output is ASCII only (safe on a cp949 console).
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
VERSIONS = ["0.1.0", "0.1.1", "0.1.2", "0.1.3", "0.1.4", "0.1.5", "0.2.0"]
CORE_DIRS = ("validator", "hooks", "bin")
SKIP_DIRS = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
EXPECTED_TAGS = {"v0.1.2": "bbd6a3d", "v0.1.3": "0df13b7", "v0.1.4": "991af67", "v0.1.5": "78517d5"}
NEW = "0.2.0"


def sha256_file(p: Path) -> str:
    return "sha256:" + hashlib.sha256(p.read_bytes()).hexdigest()


def walk(root: Path, top: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not top.is_dir():
        return out
    for dirpath, dirnames, filenames in os.walk(top):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for name in sorted(filenames):
            if name.endswith((".pyc", ".pyo")) or name == ".DS_Store":
                continue
            p = Path(dirpath) / name
            out[p.relative_to(root).as_posix()] = sha256_file(p)
    return out


def core_hash(root: Path) -> str:
    files: dict[str, str] = {}
    for d in CORE_DIRS:
        files.update(walk(root, root / d))
    data = json.dumps(files, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(data).hexdigest()


def git(*args: str) -> str:
    r = subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True, encoding="utf-8")
    return r.stdout.strip() if r.returncode == 0 else f"ERROR rc={r.returncode} {r.stderr.strip()}"


def load(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8-sig"))


def main() -> int:
    out_path = Path(sys.argv[1])
    problems: list[str] = []
    result: dict = {"head": git("rev-parse", "HEAD"), "releases": {}}

    for v in VERSIONS:
        rec = load(REPO / "releases" / f"vmodel-{v}.json")
        dist = REPO / "dist" / f"vmodel-{v}"
        files = {k: h for k, h in walk(dist, dist).items() if k != "RELEASE_MANIFEST.json"}
        entry = {
            "record_version": rec.get("version"),
            "record_core_hash": rec.get("core_hash"),
            "record_files": len(rec.get("files", {})),
            "dist_files": len(files),
            "dist_files_match_record": files == rec.get("files"),
            "dist_core_hash_recomputed": core_hash(dist),
        }
        man = dist / "RELEASE_MANIFEST.json"
        entry["dist_manifest_equals_record"] = man.is_file() and load(man) == rec
        selfcheck = subprocess.run([str(dist / "bin" / "vmodel"), "version"], capture_output=True)
        try:
            sc = json.loads(selfcheck.stdout.decode("utf-8"))
            entry["selfcheck"] = {k: sc.get(k) for k in ("version", "core_hash", "mode", "integrity_ok", "problems")}
        except ValueError:
            entry["selfcheck"] = {"error": selfcheck.returncode}
        ok = (entry["record_version"] == v and entry["dist_files_match_record"] and entry["dist_manifest_equals_record"]
              and entry["dist_core_hash_recomputed"] == rec.get("core_hash")
              and entry["selfcheck"].get("integrity_ok") is True and entry["selfcheck"].get("version") == v
              and entry["selfcheck"].get("core_hash") == rec.get("core_hash"))
        entry["ok"] = ok
        if not ok:
            problems.append(f"release {v} does not match its record")
        result["releases"][v] = entry

    # source tree == 0.2.0 record
    rec_new = load(REPO / "releases" / f"vmodel-{NEW}.json")
    src = REPO / "plugins" / "vmodel"
    src_files = walk(src, src)
    src_files.pop("RELEASE_MANIFEST.json", None)
    result["source_matches_record"] = src_files == rec_new["files"]
    result["source_core_hash"] = core_hash(src)
    if not result["source_matches_record"] or result["source_core_hash"] != rec_new["core_hash"]:
        problems.append("source plugins/vmodel differs from the 0.2.0 record")

    # version strings
    init_py = (src / "validator" / "vmodel_validator" / "__init__.py").read_text(encoding="utf-8")
    plugin_json = load(src / ".claude-plugin" / "plugin.json")
    dist_plugin_json = load(REPO / "dist" / f"vmodel-{NEW}" / ".claude-plugin" / "plugin.json")
    market = load(REPO / "dist" / ".claude-plugin" / "marketplace.json")
    mk = market["plugins"][0]
    versions = {
        "validator_VERSION": f'VERSION = "{NEW}"' in init_py,
        "plugin_json": plugin_json.get("version"),
        "dist_plugin_json": dist_plugin_json.get("version"),
        "release_record": rec_new.get("version"),
        "marketplace_version": mk.get("version"),
        "marketplace_source": mk.get("source"),
    }
    result["versions"] = versions
    if not (versions["validator_VERSION"] and versions["plugin_json"] == NEW and versions["dist_plugin_json"] == NEW
            and versions["release_record"] == NEW and versions["marketplace_version"] == NEW
            and versions["marketplace_source"] == f"./vmodel-{NEW}"):
        problems.append("version strings disagree")

    # earlier records and tags untouched
    old_records = [f"releases/vmodel-{v}.json" for v in VERSIONS[:-1]]
    result["old_records_unchanged_since_v0.1.5"] = git("diff", "--name-only", "v0.1.5", "HEAD", "--", *old_records) == ""
    if not result["old_records_unchanged_since_v0.1.5"]:
        problems.append("an earlier release record changed")
    tags = {t: git("rev-parse", "--short", f"{t}^{{commit}}") for t in EXPECTED_TAGS}
    result["tags"] = tags
    if tags != EXPECTED_TAGS:
        problems.append("an existing tag moved")
    result["tag_v0.2.0_exists"] = git("tag", "-l", "v0.2.0") == "v0.2.0"  # must stay False: no tag for a candidate
    if result["tag_v0.2.0_exists"]:
        problems.append("a v0.2.0 tag exists (not allowed for the candidate)")
    result["main"] = git("rev-parse", "--short", "main")
    result["main_is_ancestor_of_head"] = subprocess.run(
        ["git", "-C", str(REPO), "merge-base", "--is-ancestor", "main", "HEAD"]).returncode == 0
    result["main_still_v0.1.5"] = result["main"] == "78517d5"
    if not result["main_still_v0.1.5"]:
        problems.append("main moved (no merge for the candidate)")
    result["plugin_tree_v0.1.5_to_head_changed_files"] = git(
        "diff", "--name-only", "v0.1.5", "HEAD", "--", "plugins/vmodel").splitlines()

    result["problems"] = problems
    result["ok"] = not problems
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(json.dumps({"ok": result["ok"], "problems": problems}, ensure_ascii=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Trusted command execution and evidence records (SPEC section 5.3-5.4).

Commands run without a shell (argv list). stdout/stderr are kept as raw bytes
and hashed before any decoding, so decoding problems can never alter the
recorded hashes or exit code.
"""
from __future__ import annotations

import os
import platform
import secrets
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from . import VERSION
from .hashing import sha256_bytes, sha256_file
from .textio import display_decode, write_bytes, write_json


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


@dataclass
class RunResult:
    argv: list[str]
    cwd: str
    started_at: str
    finished_at: str
    duration_s: float
    exit_code: int | None
    timed_out: bool
    stdout: bytes
    stderr: bytes
    error: str | None = None


KEEP_PYTHON_VARS = {"PYTHONUTF8", "PYTHONIOENCODING", "PYTHONLEGACYWINDOWSSTDIO"}


def scrubbed_env(pycache_dir: Path) -> tuple[dict, list[str]]:
    """Environment for validator-run tools: the agent's shell must not steer the run (SPEC 5.3).

    Drops PYTHON* (except encoding switches), PYTEST_* and VMODEL_* variables, disables bytecode writing and points
    the pycache prefix at an empty validator-owned directory so hand-made .pyc files in the tree are never loaded.
    """
    env, dropped = {}, []
    for k, v in os.environ.items():
        ku = k.upper()
        if (ku.startswith("PYTHON") and ku not in KEEP_PYTHON_VARS) or ku.startswith(("PYTEST", "VMODEL_")):
            dropped.append(k)
            continue
        env[k] = v
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPYCACHEPREFIX"] = str(pycache_dir)
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    return env, sorted(dropped)


def run_command(argv: list[str], cwd: Path, timeout_s: int, env: dict | None = None) -> RunResult:
    started = utc_now()
    t0 = time.monotonic()
    try:
        proc = subprocess.Popen(
            argv, cwd=str(cwd), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=env,
        )
    except (FileNotFoundError, PermissionError, OSError) as exc:
        return RunResult(argv, str(cwd), started, utc_now(), 0.0, None, False, b"", b"",
                         f"cannot start: {exc.__class__.__name__}: {exc}")
    timed_out = False
    try:
        out, err = proc.communicate(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        timed_out = True
        proc.kill()
        out, err = proc.communicate()
    return RunResult(argv, str(cwd), started, utc_now(), round(time.monotonic() - t0, 3),
                     None if timed_out else proc.returncode, timed_out, out or b"", err or b"")


def executable_info(requested: str) -> dict:
    info: dict = {"requested": requested, "resolved": None, "sha256": None, "version": None, "notes": []}
    resolved = requested if os.path.isabs(requested) and os.path.exists(requested) else shutil.which(requested)
    if not resolved:
        info["notes"].append("executable not found on PATH")
        return info
    info["resolved"] = str(resolved)
    try:
        if os.path.getsize(resolved) <= 512 * 1024 * 1024:
            info["sha256"] = sha256_file(Path(resolved))
    except OSError as exc:  # e.g. Windows app execution aliases
        info["notes"].append(f"executable not hashable: {exc.__class__.__name__}")
    try:
        res = subprocess.run([resolved, "--version"], stdin=subprocess.DEVNULL, capture_output=True, timeout=30)
        text = display_decode(res.stdout or res.stderr).strip().splitlines()
        info["version"] = text[0][:200] if text else None
    except (OSError, subprocess.SubprocessError) as exc:
        info["notes"].append(f"version query failed: {exc.__class__.__name__}")
    return info


def runtime_info() -> dict:
    return {
        "validator_python": sys.version.split()[0],
        "platform": platform.platform(),
        "machine": platform.machine(),
        "os_name": os.name,
        "preferred_encoding": __import__("locale").getpreferredencoding(False),
    }


def new_run_dir(evidence_root: Path, wi: str, gate: str, kind: str) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    d = evidence_root / wi / gate / f"{stamp}-{kind}-{secrets.token_hex(3)}"
    d.mkdir(parents=True, exist_ok=False)
    return d


def write_evidence(project, ledger, run_dir: Path, *, wi: str, gate: str, kind: str, run: RunResult,
                   exe: dict, git: dict, manifest_hash: str, core_hash: str, extra: dict | None = None,
                   extra_files: dict[str, Path] | None = None) -> dict:
    """Persist raw output and a signed evidence record. Returns {'path','sha256'}."""
    write_bytes(run_dir / "stdout.bin", run.stdout)
    write_bytes(run_dir / "stderr.bin", run.stderr)
    files = {
        "stdout.bin": {"sha256": sha256_bytes(run.stdout), "bytes": len(run.stdout)},
        "stderr.bin": {"sha256": sha256_bytes(run.stderr), "bytes": len(run.stderr)},
    }
    for name, path in (extra_files or {}).items():
        # a regular file (also through a symlink, hashed by content as in 0.1.x) is hashed; a directory, FIFO or device
        # a test planted there is recorded, never read (0.2.0, reviews F4/N7)
        if path.is_file():
            files[name] = {"sha256": sha256_file(path), "bytes": path.stat().st_size}
        elif path.exists() or path.is_symlink():
            files[name] = {"sha256": None, "bytes": 0, "missing": True, "not_regular_file": True}
        else:
            files[name] = {"sha256": None, "bytes": 0, "missing": True}
    record = {
        "schema": "vmodel.evidence/1",
        "work_item": wi,
        "gate": gate,
        "kind": kind,
        "command": run.argv,
        "cwd": project.rel(Path(run.cwd)) or ".",
        "executable": exe,
        "runtime": runtime_info(),
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "duration_s": run.duration_s,
        "exit_code": run.exit_code,
        "timed_out": run.timed_out,
        "start_error": run.error,
        "files": files,
        "git": git,
        "manifest_hash": manifest_hash,
        "validator": {"version": VERSION, "core_hash": core_hash},
    }
    if extra:
        record.update(extra)
    record["sig"] = ledger.sign(record)
    path = run_dir / "record.json"
    write_json(path, record)
    return {"path": project.rel(path), "sha256": sha256_file(path)}


def check_evidence(project, ledger, rel: str, expected_sha: str | None) -> list[str]:
    """Problems of one evidence record against the signed ledger (empty list = intact).

    Checks that record.json exists, matches the hash the ledger recorded for it, carries a valid validator signature,
    and that every file it lists still has its recorded hash. Shared by audit, verify-evidence and the defect check.
    Records of any earlier validator version are checked the same way: nothing here depends on the core hash.
    """
    from .ledger import verify_sig
    from .textio import ArtifactError, load_json

    problems = []
    path = project.root / rel
    if not path.is_file():
        return [f"{rel}: missing"]
    if expected_sha and sha256_file(path) != expected_sha:
        problems.append(f"{rel}: record file hash differs from the ledger")
    try:
        rec = load_json(path)
    except (ArtifactError, OSError) as exc:
        return [str(exc)]
    if not isinstance(rec, dict):
        return [*problems, f"{rel}: not an evidence record (JSON object expected)"]
    sig = rec.pop("sig", None)
    if not verify_sig(ledger.key, rec, sig):
        problems.append(f"{rel}: invalid signature (not written by the validator)")
    files = rec.get("files") or {}
    if not isinstance(files, dict):
        return [*problems, f"{rel}: 'files' is not an object"]
    for name, meta in files.items():
        if not isinstance(meta, dict):
            problems.append(f"{rel}: {name}: malformed file entry")
            continue
        f = path.parent / name
        if meta.get("missing"):
            continue
        try:
            if not f.is_file():
                problems.append(f"{rel}: {name} missing")
            elif sha256_file(f) != meta.get("sha256"):
                problems.append(f"{rel}: {name} content differs from its recorded hash")
        except OSError as exc:
            problems.append(f"{rel}: {name} unreadable ({exc.__class__.__name__})")
    return problems


def git_info(root: Path) -> dict:
    git = shutil.which("git")
    if not git:
        return {"available": False, "head": None, "dirty": None, "note": "git not installed"}
    try:
        head = subprocess.run([git, "-C", str(root), "rev-parse", "HEAD"], capture_output=True, timeout=30,
                              stdin=subprocess.DEVNULL)
        if head.returncode != 0:
            inside = subprocess.run([git, "-C", str(root), "rev-parse", "--is-inside-work-tree"],
                                    capture_output=True, timeout=30, stdin=subprocess.DEVNULL)
            note = "no commits yet" if inside.returncode == 0 else "not a git repository"
            return {"available": True, "head": None, "dirty": None, "note": note}
        status = subprocess.run([git, "-C", str(root), "-c", "core.quotepath=off", "status", "--porcelain"],
                                capture_output=True, timeout=60, stdin=subprocess.DEVNULL)
        return {"available": True, "head": display_decode(head.stdout).strip(),
                "dirty": bool(status.stdout.strip()), "note": None}
    except (OSError, subprocess.SubprocessError) as exc:
        return {"available": True, "head": None, "dirty": None, "note": f"git failed: {exc.__class__.__name__}"}

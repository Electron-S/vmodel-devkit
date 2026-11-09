"""Encoding-safe text and JSON I/O.

Rules (SPEC section 12, DECISIONS D16):
- DevKit files are UTF-8; a UTF-8 BOM is tolerated on read.
- Non-UTF-8 artifacts are reported as errors, never crash the validator.
- Process output is stored as raw bytes; decoding is for display only.
- CLI output is forced to UTF-8 when it goes to a pipe, and never raises on
  characters the console code page (e.g. CP949) cannot encode.
"""
from __future__ import annotations

import io
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any


class ArtifactError(Exception):
    """A DevKit file is missing, unreadable, wrongly encoded or invalid JSON."""


def decode_utf8(data: bytes, label: str) -> str:
    if data.startswith(b"\xff\xfe") or data.startswith(b"\xfe\xff"):
        raise ArtifactError(f"{label}: file is UTF-16 encoded; VModel files must be UTF-8")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        hint = ""
        try:
            data.decode("cp949")
            hint = " (it looks like CP949/EUC-KR; re-save as UTF-8)"
        except UnicodeDecodeError:
            pass
        raise ArtifactError(f"{label}: not valid UTF-8 at byte {exc.start}{hint}") from None


def read_text(path: Path, label: str | None = None) -> str:
    label = label or str(path)
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        raise ArtifactError(f"{label}: file not found") from None
    except OSError as exc:
        raise ArtifactError(f"{label}: cannot read ({exc.__class__.__name__}: {exc})") from None
    return decode_utf8(data, label)


def load_json(path: Path, label: str | None = None) -> Any:
    label = label or str(path)
    text = read_text(path, label)
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ArtifactError(f"{label}: invalid JSON at line {exc.lineno} column {exc.colno}: {exc.msg}") from None
    except (ValueError, RecursionError) as exc:  # e.g. an integer beyond the digit limit, absurd nesting (0.2.0)
        raise ArtifactError(f"{label}: unreadable JSON: {exc.__class__.__name__}: {str(exc)[:200]}") from None


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def write_text(path: Path, text: str) -> None:
    _atomic_write_bytes(path, text.encode("utf-8"))


def write_json(path: Path, obj: Any) -> None:
    write_text(path, json.dumps(obj, indent=2, ensure_ascii=False) + "\n")


def write_bytes(path: Path, data: bytes) -> None:
    _atomic_write_bytes(path, data)


def display_decode(data: bytes, limit: int | None = None) -> str:
    """Decode process output for humans. Never raises; never used for hashing."""
    if limit is not None and len(data) > limit:
        data = data[-limit:]
    for enc in ("utf-8", "cp949"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def setup_stdio() -> None:
    """Make stdout/stderr safe on CP949 consoles, pipes and pythonw (None)."""
    forced = os.environ.get("VMODEL_OUTPUT_ENCODING")
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name)
        if stream is None:
            setattr(sys, name, io.TextIOWrapper(io.BytesIO(), encoding="utf-8"))
            continue
        try:
            if forced:
                stream.reconfigure(encoding=forced, errors="replace")
            elif not stream.isatty():
                stream.reconfigure(encoding="utf-8", errors="replace")
            else:
                stream.reconfigure(errors="replace")
        except (AttributeError, ValueError, OSError, io.UnsupportedOperation):
            pass


def read_stdin_bytes() -> bytes:
    if sys.stdin is None:
        return b""
    try:
        return sys.stdin.buffer.read()
    except (AttributeError, OSError, ValueError):
        return b""

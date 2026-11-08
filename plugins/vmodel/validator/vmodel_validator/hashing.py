"""Content hashing helpers. All hashes are 'sha256:<hex>' over raw bytes."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def canonical_json(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def hash_obj(obj: Any) -> str:
    return sha256_bytes(canonical_json(obj))


def short(h: str | None, n: int = 12) -> str:
    if not h:
        return "-"
    return h.split(":", 1)[-1][:n]

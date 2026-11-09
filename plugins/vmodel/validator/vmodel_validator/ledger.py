"""Signed, hash-chained, append-only ledger of validator decisions (DECISIONS D03).

ledger.jsonl line: {"seq", "prev", "record", "sig"}
  sig  = HMAC-SHA256(key, canonical({"seq","prev","record"}))
  prev = entry hash of the previous line (sha256 of canonical body + sig)
head.json pins the last seq/hash (signed) so truncation is detected.
Record ids are "R" + zero padded seq (e.g. R00012).
"""
from __future__ import annotations

import hmac
import hashlib
import os
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .hashing import canonical_json, sha256_bytes
from .project import Project, vmodel_home
from .textio import ArtifactError, decode_utf8, load_json, write_json


class LedgerError(Exception):
    pass


def record_id(seq: int) -> str:
    return f"R{seq:05d}"


def create_key(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="ascii") as fh:
        fh.write(secrets.token_hex(32) + "\n")


def load_key(path: Path) -> bytes:
    try:
        text = path.read_text(encoding="ascii").strip()
        key = bytes.fromhex(text)
    except FileNotFoundError:
        raise LedgerError(f"signing key not found at {path}; gates cannot be evaluated or trusted (BLOCKED)") from None
    except (ValueError, UnicodeDecodeError, OSError) as exc:
        raise LedgerError(f"signing key at {path} is unreadable: {exc}") from None
    if len(key) < 16:
        raise LedgerError(f"signing key at {path} is too short")
    return key


def sign(key: bytes, obj: Any) -> str:
    return "hmac-sha256:" + hmac.new(key, canonical_json(obj), hashlib.sha256).hexdigest()


def verify_sig(key: bytes, obj: Any, sig: Any) -> bool:
    return isinstance(sig, str) and hmac.compare_digest(sign(key, obj), sig)


def entry_hash(body: dict, sig: str) -> str:
    return sha256_bytes(canonical_json(body) + sig.encode("ascii"))


@dataclass
class Entry:
    seq: int
    prev: str | None
    record: dict
    sig: str

    @property
    def id(self) -> str:
        return record_id(self.seq)


class _Lock:
    def __init__(self, path: Path, timeout: float = 30.0):
        self.path = path
        self.timeout = timeout

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + self.timeout
        while True:
            try:
                fd = os.open(str(self.path), os.O_WRONLY | os.O_CREAT | os.O_EXCL)
                os.close(fd)
                return self
            except FileExistsError:
                try:
                    if time.time() - self.path.stat().st_mtime > 600:
                        self.path.unlink()
                        continue
                except FileNotFoundError:
                    continue
                if time.monotonic() > deadline:
                    raise LedgerError(f"ledger lock {self.path} is held by another process")
                time.sleep(0.1)

    def __exit__(self, *exc):
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass


def anchor_path(root: Path) -> Path:
    """Out-of-project anchor of the ledger head (detects wipe / rollback / re-init of .vmodel)."""
    norm = os.path.normcase(os.path.realpath(str(root)))
    return vmodel_home() / "anchors" / (sha256_bytes(norm.encode("utf-8")).split(":", 1)[1][:32] + ".json")


class Ledger:
    def __init__(self, project: Project):
        self.project = project
        self.path = project.state_dir / "ledger.jsonl"
        self.head_path = project.state_dir / "head.json"
        self.lock_path = project.state_dir / ".ledger.lock"
        self._key: bytes | None = None

    @property
    def key(self) -> bytes:
        if self._key is None:
            self._key = load_key(self.project.key_path())
        return self._key

    def sign(self, obj: Any) -> str:
        return sign(self.key, obj)

    def verify_sig(self, obj: Any, sig: Any) -> bool:
        return verify_sig(self.key, obj, sig)

    def entries(self) -> list[Entry]:
        """Load and fully verify the ledger. Raises LedgerError on any tampering."""
        import json

        key = self.key
        entries: list[Entry] = []
        hashes: list[str] = []
        prev: str | None = None
        if self.path.exists():
            raw = self.path.read_bytes()
            try:
                text = decode_utf8(raw, "ledger.jsonl")
            except ArtifactError as exc:
                raise LedgerError(str(exc)) from None
            for lineno, line in enumerate(text.splitlines(), start=1):
                if not line.strip():
                    continue
                try:
                    obj = json.loads(line)
                    body = {"seq": obj["seq"], "prev": obj["prev"], "record": obj["record"]}
                    sig = obj["sig"]
                except (ValueError, KeyError, TypeError, RecursionError):  # ValueError covers JSONDecodeError (0.2.0)
                    raise LedgerError(f"ledger line {lineno} is malformed (tampered or corrupted)") from None
                expected_seq = len(entries) + 1
                if body["seq"] != expected_seq:
                    raise LedgerError(f"ledger line {lineno}: seq {body['seq']} != expected {expected_seq}")
                if body["prev"] != prev:
                    raise LedgerError(f"ledger line {lineno}: hash chain broken")
                if not verify_sig(key, body, sig):
                    raise LedgerError(f"ledger line {lineno}: invalid signature (record not written by the validator)")
                entries.append(Entry(body["seq"], body["prev"], body["record"], sig))
                prev = entry_hash(body, sig)
                hashes.append(prev)
        head = None
        if self.head_path.exists():
            try:
                head = load_json(self.head_path, "head.json")
            except ArtifactError as exc:
                raise LedgerError(str(exc)) from None
            hbody = {"seq": head.get("seq"), "entry_hash": head.get("entry_hash")}
            if not verify_sig(key, hbody, head.get("sig")):
                raise LedgerError("head.json has an invalid signature")
        if entries and head is None:
            raise LedgerError("head.json missing while ledger has entries")
        if head is not None:
            if head["seq"] != len(entries) or head["entry_hash"] != prev:
                raise LedgerError(
                    f"ledger head mismatch: head says seq {head['seq']}, ledger has {len(entries)} "
                    "(entries were removed or the head was replaced)"
                )
        self._check_anchor(key, hashes)
        return entries

    def _check_anchor(self, key: bytes, hashes: list[str]) -> None:
        path = anchor_path(self.project.root)
        if not path.exists():
            return
        try:
            anchor = load_json(path, "ledger anchor")
        except ArtifactError as exc:
            raise LedgerError(str(exc)) from None
        body = {k: anchor.get(k) for k in ("project_root", "project_id", "seq", "entry_hash")}
        if not verify_sig(key, body, anchor.get("sig")):
            raise LedgerError(f"ledger anchor {path} has an invalid signature (the project was re-initialised or "
                              "the anchor was replaced)")
        if body["project_id"] != self.project.config().get("project_id"):
            raise LedgerError("ledger anchor belongs to another project id: .vmodel was re-initialised")
        seq = body["seq"]
        if not isinstance(seq, int) or seq > len(hashes) or (seq > 0 and hashes[seq - 1] != body["entry_hash"]):
            raise LedgerError(f"ledger rolled back or truncated: the out-of-project anchor records seq {seq}, "
                              f"the ledger has {len(hashes)} entries")

    def _write_anchor(self, seq: int, ehash: str) -> None:
        body = {"project_root": str(self.project.root), "project_id": self.project.config().get("project_id"),
                "seq": seq, "entry_hash": ehash}
        write_json(anchor_path(self.project.root), {**body, "sig": self.sign(body)})

    def append(self, record: dict) -> Entry:
        with _Lock(self.lock_path):
            entries = self.entries()
            seq = len(entries) + 1
            prev = entry_hash(
                {"seq": entries[-1].seq, "prev": entries[-1].prev, "record": entries[-1].record}, entries[-1].sig
            ) if entries else None
            record = dict(record)
            record["record_id"] = record_id(seq)
            body = {"seq": seq, "prev": prev, "record": record}
            sig = self.sign(body)
            line = canonical_json({**body, "sig": sig}).decode("utf-8") + "\n"
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8", newline="\n") as fh:
                fh.write(line)
                fh.flush()
                os.fsync(fh.fileno())
            hbody = {"seq": seq, "entry_hash": entry_hash(body, sig)}
            write_json(self.head_path, {**hbody, "sig": self.sign(hbody)})
            self._write_anchor(seq, hbody["entry_hash"])
            return Entry(seq, prev, record, sig)

"""Bootstrap test harness helpers (DECISIONS D17: stdlib unittest only).

The harness drives the validator as a black box through its CLI, in throwaway
sandboxes whose paths contain Korean characters and spaces (T18). It plays
the roles of the orchestrator and of the verifier (writing review files) so
that the validator's state machine can be tested without Claude.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
# VMODEL_TEST_PLUGIN points the harness at another plugin copy (e.g. the immutable 0.1.3 release) so that new
# regression tests can be shown to FAIL on the old core before the fix (scripts/red_green.py). Default: the source.
PLUGIN = Path(os.environ["VMODEL_TEST_PLUGIN"]).resolve() if os.environ.get("VMODEL_TEST_PLUGIN") \
    else REPO / "plugins" / "vmodel"
SOURCE_PLUGIN = REPO / "plugins" / "vmodel"
SAMPLE = REPO / "samples" / "textstats"
FIXTURE = REPO / "tests" / "fixtures" / "wordfreq"
GATES = ["G1", "G2", "G3", "G4", "G5"]
GATE_ARTIFACTS = {"G1": ["requirements.json"], "G2": ["architecture.json"], "G3": ["design.json", "tests.json"]}
KEEP = os.environ.get("VMODEL_TEST_KEEP") == "1"


def has_pytest() -> bool:
    return subprocess.run([sys.executable, "-c", "import pytest"], capture_output=True).returncode == 0


class Sandbox:
    def __init__(self, korean: bool = True, plugin: Path | None = None, sample: Path = SAMPLE):
        self.tmp = Path(tempfile.mkdtemp(prefix="vmodel-test-"))
        base = self.tmp / ("한글 경로 sandbox" if korean else "sandbox")
        self.home = self.tmp / "vmodel home"
        self.root = base / "proj"
        shutil.copytree(sample, self.root, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
        self.plugin = plugin or PLUGIN
        self.entry = self.plugin / "validator" / "vmodel.py"
        self.env = {**os.environ, "VMODEL_HOME": str(self.home)}
        self.env.pop("CLAUDE_PROJECT_DIR", None)
        self.wi = "WI-001"

    # ---------------------------------------------------------- process helpers
    def vm(self, *args: str, cwd: Path | None = None, env: dict | None = None) -> tuple[int, str]:
        r = subprocess.run([sys.executable, "-I", "-B", str(self.entry), *args], cwd=str(cwd or self.root),
                           env=env or self.env,
                           capture_output=True, stdin=subprocess.DEVNULL, timeout=600)
        return r.returncode, r.stdout.decode("utf-8") + r.stderr.decode("utf-8", errors="replace")

    def vm_json(self, *args: str) -> tuple[int, dict]:
        code, out = self.vm(*args, "--json")
        try:
            return code, json.loads(out)
        except json.JSONDecodeError:
            raise AssertionError(f"non-JSON output (exit {code}):\n{out}") from None

    def hook(self, kind: str, payload: dict, env: dict | None = None) -> tuple[int, str]:
        r = subprocess.run([sys.executable, "-I", "-B", str(self.entry), "hook", kind], cwd=str(self.root),
                           env=env or self.env, input=json.dumps(payload).encode("utf-8"), capture_output=True,
                           timeout=120)
        return r.returncode, r.stdout.decode("utf-8") + r.stderr.decode("utf-8", errors="replace")

    def git(self, *args: str) -> None:
        subprocess.run(["git", "-c", "user.name=vmodel-test", "-c", "user.email=test@example.invalid", *args],
                       cwd=self.root, capture_output=True, check=True)

    # ---------------------------------------------------------- project setup
    def init(self, *extra: str) -> None:
        args = list(extra) or ["--lint", "none", "--allow-syntax-only"]
        code, out = self.vm("init", "--project", str(self.root), *args)
        assert code == 0, out

    def new_wi(self, title: str = "단어 빈도 기능", request: str = "단어 빈도와 상위 N개 단어 기능을 개발해줘") -> str:
        code, out = self.vm("new-wi", "--title", title, "--request", request)
        assert code == 0, out
        return out.strip().splitlines()[-1]

    @property
    def wi_dir(self) -> Path:
        return self.root / ".vmodel" / "work-items" / self.wi

    def put_artifact(self, name: str, wi: str | None = None) -> None:
        shutil.copy(FIXTURE / "artifacts" / name, self.root / ".vmodel" / "work-items" / (wi or self.wi) / name)

    def put_code(self) -> None:
        shutil.copytree(FIXTURE / "code", self.root, dirs_exist_ok=True)

    def load(self, name: str) -> dict:
        return json.loads((self.wi_dir / name).read_text(encoding="utf-8"))

    def save(self, name: str, obj: dict) -> None:
        (self.wi_dir / name).write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def review(self, gate: str, verdict: str = "approve", findings: list | None = None,
               reviewer: str = "vmodel:verifier", target_hash: str | None = None, submit: bool = True) -> None:
        if target_hash is None:
            code, out = self.vm("hash", self.wi, gate)
            assert code == 0, out
            target_hash = out.strip()
        doc = {"gate": gate, "work_item": self.wi, "reviewer": reviewer, "target_hash": target_hash,
               "reviewed_at": "2026-11-08T00:00:00Z", "verdict": verdict, "summary": f"harness review of {gate}",
               "checklist": [{"item": "harness", "result": "ok"}], "findings": findings or []}
        (self.wi_dir / "reviews").mkdir(exist_ok=True)
        (self.wi_dir / "reviews" / f"{gate}.json").write_text(json.dumps(doc, indent=2), encoding="utf-8")
        if submit:  # the harness plays the verifier, so it also registers the review
            code, out = self.vm("review-submit", self.wi, gate)
            assert code == 0, out

    def gate(self, gate: str) -> tuple[int, dict]:
        return self.vm_json("gate", self.wi, gate)

    def prepare(self, gate: str) -> None:
        if gate in GATE_ARTIFACTS:
            for a in GATE_ARTIFACTS[gate]:
                self.put_artifact(a)
        if gate == "G4":
            self.put_code()

    def advance(self, upto: str) -> None:
        """Bring the work item to PASSED for every gate up to and including `upto`."""
        for g in GATES[: GATES.index(upto) + 1]:
            self.prepare(g)
            if g != "G5":
                self.review(g)
            code, res = self.gate(g)
            assert res["status"] == "PASSED", json.dumps(res, indent=2, ensure_ascii=False)

    def status(self) -> dict:
        code, st = self.vm_json("status")
        return st

    def gate_status(self, gate: str, wi: str | None = None) -> str:
        st = self.status()
        w = [x for x in st["work_items"] if x["id"] == (wi or self.wi)][0]
        return [g for g in w["gates"] if g["gate"] == gate][0]["status"]

    def add_defect(self, record_id: str, gate: str, did: str = "DEFECT-001", phase: str = "P4", **extra) -> None:
        path = self.wi_dir / "defects.json"
        doc = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"work_item": self.wi, "defects": []}
        existing = [d for d in doc["defects"] if d["id"] == did]
        if existing:
            existing[0]["found_in_records"].append(record_id)
            existing[0].update(extra)
        else:
            doc["defects"].append({"id": did, "gate": gate, "found_in_records": [record_id],
                                   "description": "harness defect", "root_cause_phase": phase,
                                   "root_cause": "harness", "fix_scope": ["src/textstats/wordfreq.py"],
                                   "status": "open", **extra})
        path.write_text(json.dumps(doc, indent=2), encoding="utf-8")

    def regate_g4(self) -> None:
        """After a rework record changes defects.json (part of the G4/G5 manifest), G4 needs a fresh review."""
        self.review("G4")
        code, res = self.gate("G4")
        assert res["status"] == "PASSED", json.dumps(res, indent=2, ensure_ascii=False)

    def run_tty(self, *args: str, answer: bytes = b"yes\n") -> bytes:
        """Run a user-only command on a pseudo terminal (POSIX only), as a person at a terminal would."""
        import pty
        pid, fd = pty.fork()
        if pid == 0:
            os.chdir(self.root)
            os.environ.clear()
            os.environ.update(self.env)
            os.execv(sys.executable, [sys.executable, "-I", "-B", str(self.entry), *args])
        os.write(fd, answer)
        buf = b""
        while True:
            try:
                chunk = os.read(fd, 1024)
            except OSError:
                break
            if not chunk:
                break
            buf += chunk
        os.waitpid(pid, 0)
        return buf

    def cleanup(self) -> None:
        if not KEEP:
            shutil.rmtree(self.tmp, ignore_errors=True)


def copy_plugin(dest_parent: Path) -> Path:
    dest = dest_parent / "plugin copy"
    shutil.copytree(PLUGIN, dest, ignore=shutil.ignore_patterns("__pycache__"))
    return dest


# ---------------------------------------------------------------- shared rework scenario (0.1.4 regression tests)
def fail_g5(sb: Sandbox) -> dict:
    """G1-G4 PASSED, then a seeded bug in wordfreq.top_n -> G4 re-reviewed PASSED -> G5 FAILED.

    Returns the failed record id, the failing TEST ids read from the signed record's G5.TEST_MAPPING, the G4 PASS
    record id the G5 run stood on, and the good source to restore.
    """
    sb.init()
    sb.new_wi()
    sb.advance("G4")
    wf = sb.root / "src/textstats/wordfreq.py"
    good = wf.read_text(encoding="utf-8")
    wf.write_text(good.replace("if n <= 0:", "if n < 0:"), encoding="utf-8")
    sb.review("G4")
    g4 = sb.gate("G4")[1]
    assert g4["status"] == "PASSED", json.dumps(g4, indent=2, ensure_ascii=False)
    res = sb.gate("G5")[1]
    assert res["status"] == "FAILED", json.dumps(res, indent=2, ensure_ascii=False)
    mapping = [c for c in res["checks"] if c["id"] == "G5.TEST_MAPPING"][0]
    failing = sorted(i.split(":")[0] for i in mapping["items"] if i.endswith((": failed", ": error")))
    assert failing
    return {"failed": res["record_id"], "failing": failing, "g4_pass": g4["record_id"], "wf": wf, "good": good,
            "evidence": res["evidence"]}


def fix_and_pass(sb: Sandbox, scenario: dict) -> str:
    """Restore the good source, re-review G4 and re-run G5 (the defect must already cite the failure)."""
    scenario["wf"].write_text(scenario["good"], encoding="utf-8")
    sb.regate_g4()
    res = sb.gate("G5")[1]
    assert res["status"] == "PASSED", json.dumps(res, indent=2, ensure_ascii=False)
    return res["record_id"]


# ---------------------------------------------------------------- released plugin copies (cross-version tests)
_OLD_RELEASES: dict[str, Path | None] = {}
_CORE_PREFIXES = ("validator/", "hooks/", "bin/")


def _sha256(path: Path) -> str:
    import hashlib
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _matches_record(plugin: Path, record: dict) -> bool:
    core = {k: v for k, v in record.get("files", {}).items() if k.startswith(_CORE_PREFIXES)}
    if not core:
        return False
    for rel, h in core.items():
        p = plugin / rel
        if not p.is_file() or _sha256(p) != h:
            return False
    return True


def old_release(version: str) -> Path | None:
    """A plugin copy of an earlier release whose core files match releases/vmodel-<version>.json byte for byte.

    Uses dist/vmodel-<version> when present (dist/ is not tracked), otherwise extracts plugins/vmodel from the git tag
    v<version>. Returns None when neither is available (e.g. an exported tree without .git); callers skip then.
    """
    if version in _OLD_RELEASES:
        return _OLD_RELEASES[version]
    found: Path | None = None
    rec_path = REPO / "releases" / f"vmodel-{version}.json"
    if rec_path.is_file():
        record = json.loads(rec_path.read_text(encoding="utf-8"))
        cand = REPO / "dist" / f"vmodel-{version}"
        if cand.is_dir() and _matches_record(cand, record):
            found = cand
        elif shutil.which("git") and (REPO / ".git").exists():
            import atexit
            import io
            import tarfile
            r = subprocess.run(["git", "-C", str(REPO), "archive", "--format=tar", f"v{version}", "plugins/vmodel"],
                               capture_output=True)
            if r.returncode == 0:
                dest = Path(tempfile.mkdtemp(prefix=f"vmodel-{version}-"))
                atexit.register(shutil.rmtree, dest, True)
                with tarfile.open(fileobj=io.BytesIO(r.stdout)) as tf:
                    try:
                        tf.extractall(dest, filter="data")
                    except TypeError:  # Python without extraction filters
                        tf.extractall(dest)
                plugin = dest / "plugins" / "vmodel"
                if _matches_record(plugin, record):
                    found = plugin
    _OLD_RELEASES[version] = found
    return found

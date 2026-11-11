"""Shared bases for the 0.3.0 G7 tests (docs/g7/G7-DESIGN.md section 5).

Each class builds one sandbox in setUpClass (G1-G6 PASSED by default, at fixed absolute paths) and restores a byte
copy before every test. Red-class assertions that must fail on the immutable 0.2.0 release carry RED-TARGET in their
message; helper assertions do not (scripts/red_green.py --marker).
Fixtures: gradecalc (one component, no interface -> G6 N/A, a CLI and an HTTP API, system tests in tests/system) and
pipeline (two components, G6 required) with the system test overlay tests/fixtures/pipeline_system.
"""
from __future__ import annotations

import json
import re
import shutil
import unittest
from pathlib import Path

from helpers import REPO, Sandbox, has_pytest

RED = "RED-TARGET"
GRADECALC = REPO / "tests" / "fixtures" / "gradecalc"
PIPELINE_SYSTEM = REPO / "tests" / "fixtures" / "pipeline_system"
GC_ENDPOINTS = ["CLI 사용자", "HTTP 클라이언트"]
GATES7 = ["G1", "G2", "G3", "G4", "G5", "G6", "G7"]
SYSTEM_IDS = ["TEST-101", "TEST-102", "TEST-103", "TEST-104", "TEST-105", "TEST-106"]
PYTEST = ["{python}", "-m", "pytest", "-q", "-p", "no:cacheprovider"]
# seeded defects only the system tests can see (the unit tests call the functions directly)
CLI_EXIT_BUG = ("    raise SystemExit(main())\n", "    main()\n")  # the process always exits 0
API_STATUS_BUG = ("        self.send_response(status)\n", "        self.send_response(200)\n")
BOUNDARY_BUG = ("    raise SystemExit(main())\n",
                "    raise SystemExit(main(['-1'] if sys.argv[1:] == ['0'] else sys.argv[1:]))\n")
# the Korean message loses its required wording (REQ-003); the unit tests only look for "오류"
MESSAGE_BUG = ('MESSAGE = "오류: 점수는 0에서 100 사이의 정수여야 합니다"\n', 'MESSAGE = "오류: 잘못된 점수"\n')


def check(tc: unittest.TestCase, res: dict, cid: str) -> dict:
    found = [c for c in res.get("checks") or [] if c["id"] == cid]
    tc.assertTrue(found, f"{RED} (check missing) {cid} not in {json.dumps(res, indent=1, ensure_ascii=False)[:3000]}")
    return found[0]


def ledger_records(sb: Sandbox) -> list[dict]:
    lines = (sb.root / ".vmodel/state/ledger.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(ln)["record"] for ln in lines]


def ledger_record(sb: Sandbox, rid: str) -> dict:
    return [r for r in ledger_records(sb) if r.get("record_id") == rid][0]


def wi_status(sb: Sandbox) -> dict:
    return [w for w in sb.status()["work_items"] if w["id"] == sb.wi][0]


def gate_view(sb: Sandbox, gate: str) -> dict:
    return [g for g in wi_status(sb)["gates"] if g["gate"] == gate][0]


def states(sb: Sandbox) -> dict:
    return {g["gate"]: g["status"] for g in wi_status(sb)["gates"]}


def applicability(endpoints: list[str]) -> dict:
    return {"integration_applicability": {"decision": "not_required",
                                          "reason": "single component; no interface to integrate",
                                          "endpoints_reviewed": endpoints}}


def set_test_commands(sb: Sandbox, mode: str, integration: str | None = None, system: str = "tests/system") -> None:
    """The harness plays the user (config is user-owned).

    mode "system": unit ignores the system (and integration) folder, system_test runs it.
    mode "nosystem": unit ignores the system folder, no system_test (G7 must stay BLOCKED misconfigured).
    mode "mixed": the unit command runs every test, including system tests, and there is no system_test (0.2.0 form).
    """
    cfg = sb.config()
    unit = list(PYTEST)
    if integration:
        unit.append(f"--ignore={integration}")
        cfg["integration_test"] = {"argv": [*PYTEST, integration, "--junitxml={junit}"], "timeout_s": 300}
    if mode in ("system", "nosystem"):
        unit.append(f"--ignore={system}")
    cfg["unit_test"]["argv"] = [*unit, "--junitxml={junit}"]
    cfg.pop("system_test", None)
    if mode == "system":
        cfg["system_test"] = {"argv": [*PYTEST, system, "--junitxml={junit}"], "timeout_s": 300}
    sb.set_config(cfg)


def replace_in(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not in {path}"
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def remove_function(path: Path, name: str) -> None:
    text = path.read_text(encoding="utf-8")
    pat = re.compile(rf"\n\n(@[^\n]*\n)*def {re.escape(name)}\(.*?(?=\n\n\n(?:@|def )|\Z)", re.S)
    assert pat.search(text), f"{name} not in {path}"
    path.write_text(pat.sub("", text, count=1).rstrip("\n") + "\n", encoding="utf-8")


def justify_test_change(sb: Sandbox, rel: str, affected: str, reqs: tuple = ("REQ-001",),
                        removed: list[str] | None = None) -> None:
    """A test file changed after a G5 PASS needs a test_changes entry (G5.NO_WEAKENING, unchanged rule)."""
    since = [r for r in ledger_records(sb) if r.get("type") == "gate" and r.get("gate") == "G5"
             and r.get("status") == "PASSED"][-1]["record_id"]
    path = sb.wi_dir / "change-requests.json"
    doc = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"work_item": sb.wi, "change_requests": []}
    n = len(doc["change_requests"]) + 1
    cr = {"id": f"CR-{900 + n:03d}", "description": f"{rel} 변경", "reason": "시스템 테스트 변경",
          "affected": [affected], "status": "applied",
          "test_changes": [{"file": rel, "since_record": since, "reason": "시나리오 변경", "requirements": list(reqs),
                            "impact": "시스템 테스트 내용만 바뀜"}]}
    if removed:
        cr["removed_ids"] = removed
    doc["change_requests"].append(cr)
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")


@unittest.skipUnless(has_pytest(), "pytest not installed")
class G7Class(unittest.TestCase):
    """One sandbox per class, restored before each test."""
    fixture: Path = GRADECALC
    overlay: Path | None = None  # extra code copied at G4 (pipeline system tests)
    mode = "system"
    integration: str | None = None
    na_endpoints: list[str] | None = GC_ENDPOINTS  # G2/G3 reviews confirm "integration not required" (G6 N/A)
    upto: str | None = "G6"

    @classmethod
    def setUpClass(cls):
        cls.sb = Sandbox(fixture=cls.fixture)
        try:
            cls.build(cls.sb)
            cls.sb.snapshot()
        except BaseException:
            cls.sb.cleanup()
            raise

    @classmethod
    def build(cls, sb: Sandbox) -> None:
        sb.init()
        assert sb.new_wi("G7 기능", "시스템 검증 대상 기능을 개발해줘") == "WI-001"
        set_test_commands(sb, cls.mode, integration=cls.integration)
        if cls.upto:
            cls.advance(sb, cls.upto)

    @classmethod
    def mutate(cls, sb: Sandbox, gate: str) -> None:
        """Hook: change the fixture right after the artifacts / code of `gate` were put in place."""

    @classmethod
    def advance(cls, sb: Sandbox, upto: str) -> None:
        for g in GATES7[: GATES7.index(upto) + 1]:
            sb.prepare(g)
            if g == "G4" and cls.overlay is not None:
                shutil.copytree(cls.overlay, sb.root, dirs_exist_ok=True)
            cls.mutate(sb, g)
            if g in ("G1", "G2", "G3", "G4"):
                sb.review(g, extra=cls.review_extra(g))
            res = sb.gate(g)[1]
            assert res["status"] == "PASSED", json.dumps(res, indent=2, ensure_ascii=False)[:4000]

    @classmethod
    def review_extra(cls, gate: str) -> dict | None:
        return applicability(cls.na_endpoints) if (cls.na_endpoints and gate in ("G2", "G3")) else None

    @classmethod
    def tearDownClass(cls):
        cls.sb.cleanup()

    def setUp(self):
        self.sb.restore()

    # ------------------------------------------------------------ shortcuts
    def check(self, res: dict, cid: str) -> dict:
        return check(self, res, cid)

    def regate(self, *gates: str, expect: str = "PASSED") -> dict:
        """Re-review (G1-G4) and re-run the given gates; each must reach `expect` (helper, not a RED target)."""
        res: dict = {}
        for g in gates:
            if g in ("G1", "G2", "G3", "G4"):
                self.sb.review(g, extra=self.review_extra(g))
            res = self.sb.gate(g)[1]
            assert res["status"] == expect, json.dumps(res, indent=1, ensure_ascii=False)[:4000]
        return res

    def g7(self) -> dict:
        return self.sb.gate("G7")[1]

    def set_system_argv(self, argv: list[str] | str | None, timeout_s=300, drop_timeout: bool = False) -> None:
        cfg = self.sb.config()
        if argv is None:
            cfg.pop("system_test", None)
        else:
            cfg["system_test"] = {"argv": argv, "timeout_s": timeout_s}
            if drop_timeout:
                del cfg["system_test"]["timeout_s"]
        self.sb.set_config(cfg)

    def g7_evidence_dirs(self) -> list[Path]:
        base = self.sb.root / ".vmodel" / "evidence" / "WI-001" / "G7"
        return sorted(p for p in base.iterdir() if p.is_dir()) if base.is_dir() else []

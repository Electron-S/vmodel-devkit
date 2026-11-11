"""Quality gate evaluation G1-G7 (SPEC section 3; G6 since 0.2.0, docs/g6; G7 since 0.3.0, docs/g7).

Only this module decides gate outcomes. Every evaluation is appended to the
signed ledger; preconditions that prevent an evaluation return BLOCKED
without a ledger record.
"""
from __future__ import annotations

import ast
import json
import os
import posixpath
import re
import tempfile
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

from . import VERSION, runner, wiring
from .hashing import hash_obj, sha256_file, short
from .integrity import IntegrityReport, check_against_lock, check_self
from .ledger import Entry, Ledger, LedgerError
from .project import ARTIFACTS, SCHEMA_FOR, Project
from .schema_lite import validate
from .textio import ArtifactError, display_decode, load_json, write_json
from .trace import TraceGraph, item_hashes, test_ids_in_text

DATA = Path(__file__).resolve().parent / "data"
TRACER_DIR = Path(__file__).resolve().parent / "tracer"  # G6 runtime tracer (sitecustomize), part of the Core
GATE_ORDER = ["G1", "G2", "G3", "G4", "G5", "G6", "G7"]
REVIEWER = "vmodel:verifier"
STATUS_RANK = {"blocked": 4, "fail": 3, "pending": 2, "warn": 1, "pass": 0, "skip": 0}
ID_KINDS = ("REQ", "ARCH", "IF", "DESIGN", "TEST", "DEFECT", "CR", "ISSUE", "ASM")


# ---------------------------------------------------------------- definitions
@lru_cache(maxsize=None)
def gates_def() -> dict:
    return json.loads((DATA / "gates.json").read_text(encoding="utf-8"))


def gate_def(gate: str) -> dict:
    for g in gates_def()["gates"]:
        if g["id"] == gate:
            return g
    raise KeyError(gate)


@lru_cache(maxsize=None)
def load_schema(name: str) -> dict:
    return json.loads((DATA / "schemas" / f"{name}.schema.json").read_text(encoding="utf-8"))


def implemented_gates() -> list[str]:
    return [g["id"] for g in gates_def()["gates"] if g["implemented"]]


def prev_gate(gate: str) -> str | None:
    i = GATE_ORDER.index(gate)
    return GATE_ORDER[i - 1] if i > 0 else None


# ---------------------------------------------------------------- data types
@dataclass
class Check:
    id: str
    kind: str
    status: str  # pass | warn | pending | fail | blocked | skip
    detail: str = ""
    items: list[str] = field(default_factory=list)
    data: dict = field(default_factory=dict)
    sig: list[str] | None = None  # stable identity for the 3-strike rule (defaults to items)

    def as_dict(self) -> dict:
        d: dict[str, Any] = {"id": self.id, "kind": self.kind, "status": self.status, "detail": self.detail}
        if self.items:
            d["items"] = self.items
        if self.data:
            d["data"] = self.data
        return d


@dataclass
class Ctx:
    project: Project
    wi: str
    ledger: Ledger
    entries: list[Entry]
    integrity: IntegrityReport
    arts: dict[str, Any]
    art_errors: dict[str, str]
    graph: TraceGraph
    foreign_ids: dict[str, str]


@dataclass
class GateRun:
    work_item: str
    gate: str
    status: str
    reasons: list[str] = field(default_factory=list)
    record: dict | None = None
    recorded: bool = False

    def as_dict(self) -> dict:
        d = {"work_item": self.work_item, "gate": self.gate, "status": self.status, "recorded": self.recorded,
             "reasons": self.reasons}
        if self.record:
            d["record_id"] = self.record.get("record_id")
            d["checks"] = self.record.get("checks")
            d["review_required_by"] = self.record.get("review_required_by")
            d["evidence"] = self.record.get("evidence")
            d["manifest_hash"] = self.record.get("manifest", {}).get("hash")
            if self.record.get("blocked_reason"):
                d["blocked_reason"] = self.record["blocked_reason"]
            if self.record.get("applicability"):  # G6 (0.2.0): required | not_applicable | unconfirmed
                d["applicability"] = self.record["applicability"]
        return d


# ---------------------------------------------------------------- context
def collect_ids(arts: dict[str, Any]) -> list[str]:
    out: list[str] = []
    spec = {"requirements.json": ["requirements"], "architecture.json": ["components", "interfaces"],
            "design.json": ["units"], "tests.json": ["tests"], "defects.json": ["defects"],
            "change-requests.json": ["change_requests"]}
    for name, keys in spec.items():
        art = arts.get(name)
        if not isinstance(art, dict):
            continue
        for key in keys:
            for item in art.get(key) or []:
                if isinstance(item, dict) and isinstance(item.get("id"), str):
                    out.append(item["id"])
                    if key == "requirements":
                        for ac in item.get("acceptance_criteria") or []:
                            if isinstance(ac, dict) and isinstance(ac.get("id"), str):
                                out.append(ac["id"])
    return out


def load_artifacts(project: Project, wi: str) -> tuple[dict[str, Any], dict[str, str]]:
    arts: dict[str, Any] = {}
    errors: dict[str, str] = {}
    for name in ARTIFACTS:
        data, err = project.load_artifact(wi, name)
        if err:
            errors[name] = err
        else:
            arts[name] = data
    return arts, errors


def integrity_for(project: Project) -> IntegrityReport:
    rep = check_self()
    try:
        lock = project.lock()
    except ArtifactError as exc:
        return IntegrityReport(False, rep.version, rep.core_hash, rep.mode, [*rep.problems, str(exc)])
    return check_against_lock(lock, rep)


def build_ctx(project: Project, wi: str, ledger: Ledger, entries: list[Entry], integrity: IntegrityReport) -> Ctx:
    arts, errors = load_artifacts(project, wi)
    foreign: dict[str, str] = {}
    for other in project.work_items():
        if other == wi:
            continue
        o_arts, _ = load_artifacts(project, other)
        for i in collect_ids(o_arts):
            foreign.setdefault(i, other)
    return Ctx(project, wi, ledger, entries, integrity, arts, errors, TraceGraph.build(arts), foreign)


# ---------------------------------------------------------------- manifests
def compute_manifest(project: Project, wi: str, gate: str) -> dict[str, str]:
    spec = gate_def(gate)["manifest"]
    files: dict[str, str] = {}
    for name in spec["artifacts"]:
        p = project.wi_root / wi / name
        files[project.rel(p)] = sha256_file(p) if p.is_file() else "MISSING"
    if spec["code"]:
        tree, links = project.project_files()
        for rel, p in tree.items():
            files[rel] = sha256_file(p)
        for rel in links:
            try:
                files[rel] = "SYMLINK:" + os.readlink(project.root / rel)
            except OSError:
                files[rel] = "SYMLINK:?"
        files[".vmodel/config.json"] = sha256_file(project.config_path)
        for name in ("defects.json", "change-requests.json"):  # rework justifications are reviewed at G4
            p = project.wi_root / wi / name
            files[project.rel(p)] = sha256_file(p) if p.is_file() else "MISSING"
    return dict(sorted(files.items()))


def test_roots(project: Project) -> list[str]:
    """Static directory prefixes of the configured test globs (e.g. 'tests/')."""
    roots = []
    for pat in project.config()["paths"]["tests"]:
        parts = []
        for part in pat.replace("\\", "/").split("/"):
            if any(ch in part for ch in "*?["):
                break
            parts.append(part)
        roots.append("/".join(parts) + "/" if parts else "")
    return roots


def diff_manifest(old: dict[str, str], new: dict[str, str]) -> list[str]:
    out = []
    for k in sorted(set(old) | set(new)):
        a, b = old.get(k), new.get(k)
        if a == b:
            continue
        if a is None:
            out.append(f"added: {k}")
        elif b is None:
            out.append(f"removed: {k}")
        else:
            out.append(f"changed: {k}")
    return out


# ---------------------------------------------------------------- ledger queries
def gate_entries(entries: list[Entry], wi: str, gate: str) -> list[Entry]:
    return [e for e in entries if e.record.get("work_item") == wi and e.record.get("gate") == gate
            and e.record.get("type") in ("gate", "unblock")]


def last_eval(entries: list[Entry], wi: str, gate: str) -> Entry | None:
    for e in reversed(gate_entries(entries, wi, gate)):
        if e.record.get("type") == "gate":
            return e
    return None


def last_with_status(entries: list[Entry], wi: str, gate: str, status: str) -> Entry | None:
    for e in reversed(gate_entries(entries, wi, gate)):
        if e.record.get("type") == "gate" and e.record.get("status") == status:
            return e
    return None


def unblocked_after(entries: list[Entry], wi: str, gate: str, seq: int) -> bool:
    return any(e.record.get("type") == "unblock" and e.seq > seq for e in gate_entries(entries, wi, gate))


def failing_tests(record: dict) -> list[str]:
    """TEST ids whose cases failed or errored in a signed G5 record (validator facts, not agent claims)."""
    ex = record.get("executed_tests")
    return sorted(t for t, s in ex.items() if s in ("failed", "error")) if isinstance(ex, dict) else []


def failed_checks(record: dict, limit: int = 8) -> list[dict]:
    return [{"id": c.get("id"), "status": c.get("status"), "detail": c.get("detail", ""),
             "items": (c.get("items") or [])[:limit]}
            for c in record.get("checks") or [] if isinstance(c, dict) and c.get("status") in ("fail", "blocked")]


def is_failure_record(rec: dict) -> bool:
    """A gate evaluation that requires a DEFECT before re-evaluation (the rework precondition) and is therefore the
    only valid failure evidence a DEFECT can cite (D35): FAILED, or BLOCKED after three identical failures."""
    return rec.get("status") == "FAILED" or (
        rec.get("status") == "BLOCKED" and rec.get("blocked_reason") == "three_consecutive_identical_failures")


# Gates whose records carry per-TEST results (G7 since 0.3.0). Other gates' failures are N/A for tests.
TEST_EXECUTING_GATES = ("G5", "G6", "G7")
NOT_EXECUTED = re.compile(r"^(TEST-\d{3,}): not executed$")
DEFECT_CHECK_CATEGORIES = {"evidence_integrity": "error", "invalid_citation": "error",
                           "unlinked_failing_test": "warning", "unknown_test_result": "warning"}


def _problem(category: str, record: str | None, detail: str, tests: list[str] | None = None) -> dict:
    p = {"severity": DEFECT_CHECK_CATEGORIES[category], "category": category, "record": record, "detail": detail}
    if tests is not None:
        p["tests"] = tests
    return p


def citation_view(entry: Entry | None, rid: str, wi: str) -> dict:
    """Is a cited record valid failure evidence, and what does its signed content say about each TEST?"""
    if entry is None:
        return {"record": rid, "valid": False, "reason": "is not in the signed ledger"}
    rec = entry.record
    c: dict[str, Any] = {"record": rid, "gate": rec.get("gate"), "status": rec.get("status")}
    if rec.get("type") != "gate":
        return {**c, "valid": False, "reason": f"is a {rec.get('type')} record, not a gate evaluation"}
    if rec.get("work_item") != wi:
        return {**c, "valid": False, "reason": f"is a gate evaluation of {rec.get('work_item')}, not of {wi}"}
    if not is_failure_record(rec):
        why = f" ({rec['blocked_reason']})" if rec.get("blocked_reason") else ""
        return {**c, "valid": False, "reason": f"is a {rec.get('gate')} {rec.get('status')}{why} record, not a failure"}
    c["valid"] = True
    if rec.get("gate") not in TEST_EXECUTING_GATES:
        return {**c, "test_results": "not_applicable", "failing_tests": [], "unknown_tests": [], "recorded_tests": []}
    mapping = [ch for ch in rec.get("checks") or [] if isinstance(ch, dict)
               and ch.get("id") == f"{rec.get('gate')}.TEST_MAPPING"]
    not_run = sorted({m.group(1) for ch in mapping for it in ch.get("items") or []
                      if isinstance(it, str) and (m := NOT_EXECUTED.match(it))})
    ex = rec.get("executed_tests")
    if not isinstance(ex, dict) or not ex:
        results = "unknown"  # no per-TEST results in the signed record (e.g. no JUnit produced)
    else:
        results = "partial" if not_run else "recorded"
    return {**c, "test_results": results, "failing_tests": failing_tests(rec), "unknown_tests": not_run,
            "recorded_tests": sorted(ex) if isinstance(ex, dict) else []}


def is_na_record(rec: dict) -> bool:
    """A G6 N/A evaluation (PASSED + applicability not_applicable): nothing was executed, so it never verifies a fix
    (REQ-G6-24)."""
    return rec.get("applicability") == "not_applicable"


def defect_trace(entries: list[Entry], wi: str, defects: list[dict],
                 evidence_check: Callable[[str, str | None], list[str]] | None = None,
                 ledger_error: str | None = None) -> list[dict]:
    """Defect view derived from the signed ledger (display only, never used for gate decisions).

    Per DEFECT: which cited records are valid failure evidence, the failing / UNKNOWN TEST ids they record, which
    failing TEST ids the DEFECT does not link, and the closure evidence `verified_by`: the first PASS, after the latest
    cited failure, of the most downstream gate that failed (a G5 PASS also implies G4 passed before it). For the
    display states (status.closure_view) it also keeps `verification_history` (that gate's PASSes since the DEFECT's
    first cited failure on it, i.e. past successes) and `last_verification`: over the gates the DEFECT cites failures
    of, each gate's latest PASSED-or-failure evaluation since the first cited failure; the most recent of those that is
    a failure, else the most recent one (`failure` = is_failure_record). Problems
    carry the categories of DEFECT_CHECK_CATEGORIES (one per DEFECT and category for the trace warnings): errors =
    evidence integrity and invalid citations, warnings = unlinked failing tests and unknown per-TEST results.
    `evidence_check(path, sha)` returns the problems of an evidence record (an exception counts as a problem); if the
    evidence behind a cited failure or the verifying PASS does not match the ledger, `verified_by` is withheld.
    `ledger_error` means the ledger itself failed verification.
    """
    by_id = {e.id: e for e in entries}
    checked: dict[tuple[str, Any], list[str]] = {}

    def check(path: str, sha: Any) -> list[str]:
        if (path, sha) not in checked:
            try:
                checked[(path, sha)] = list(evidence_check(path, sha)) if evidence_check else []
            except Exception as exc:  # a malformed evidence file must not break status/lint/report
                checked[(path, sha)] = [f"{path}: evidence check failed ({exc.__class__.__name__}: {exc})"]
        return checked[(path, sha)]

    out = []
    for d in defects:
        did = d.get("id")
        found = _str_list(d.get("found_in_records"))
        linked = set(_str_list(d.get("related")))
        view: dict[str, Any] = {"id": did, "gate": d.get("gate"), "claimed_status": d.get("status"),
                                "root_cause_phase": d.get("root_cause_phase"), "found_in_records": found}
        errors: list[dict] = []
        warnings: list[dict] = []
        if ledger_error:
            errors.append(_problem("evidence_integrity", None,
                                   f"{did}: the signed ledger failed its integrity check ({ledger_error}); "
                                   "the cited records cannot be verified"))
            view.update(citations=[{"record": r, "valid": None, "reason": "ledger integrity failed"} for r in found],
                        unknown_records=sorted(set(found)), failing_tests_by_record={}, failing_tests=[],
                        unlinked_failing_tests=[], unknown_tests=[], closure_gate=None, verified_by=None,
                        verification_withheld=None, verification_history=[], last_verification=None,
                        errors=errors, warnings=warnings)
            out.append(view)
            continue
        citations = [citation_view(by_id.get(r), r, wi) for r in dict.fromkeys(found)]
        valid = [by_id[c["record"]] for c in citations if c["valid"]]
        if not citations:
            errors.append(_problem("invalid_citation", None,
                                   f"{did} cites no record: found_in_records must list the failed gate record ids"))
        for c in citations:
            if not c["valid"]:
                errors.append(_problem("invalid_citation", c["record"],
                                       f"{did} cites {c['record']}, which {c['reason']}; it is not failure evidence "
                                       "(ignored for failing tests and closure)"))
        ok = [c for c in citations if c["valid"]]
        per_record = {c["record"]: c["failing_tests"] for c in ok}
        failing = sorted({t for ts in per_record.values() for t in ts})
        unlinked = [t for t in failing if t not in linked]
        if unlinked:  # one warning per DEFECT (a 3-strike chain repeats the same failing tests)
            recs = [c["record"] for c in ok if set(c["failing_tests"]) - linked]
            w = _problem("unlinked_failing_test", recs[0] if len(recs) == 1 else None,
                         f"{did} does not link failing test(s) of {', '.join(recs)} in 'related': {', '.join(unlinked)}",
                         unlinked)
            warnings.append({**w, "records": recs})
        # per TEST the latest cited G5 result counts: an older run's results never hide a newer run's UNKNOWNs
        runs = sorted((c for c in ok if c["test_results"] != "not_applicable"), key=lambda c: by_id[c["record"]].seq)
        latest: dict[str, str | None] = {}  # TEST id -> the latest cited run naming it as UNKNOWN (None: result known)
        for c in runs:
            latest.update({t: None for t in c.get("recorded_tests") or []})
            latest.update({t: c["record"] for t in c["unknown_tests"]})
        unknown = sorted(t for t, r in latest.items() if r)
        no_results = bool(runs) and runs[-1]["test_results"] == "unknown" and not runs[-1]["unknown_tests"]
        if unknown or no_results:
            named = set(latest.values()) | ({runs[-1]["record"]} if no_results else set())
            recs = [c["record"] for c in runs if c["record"] in named]
            w = _problem("unknown_test_result", recs[0] if len(recs) == 1 else None,
                         f"{did}: per-TEST results of {', '.join(recs)} are UNKNOWN (not executed or not recorded): "
                         + (", ".join(unknown) or "no per-TEST results recorded"), unknown)
            warnings.append({**w, "records": recs})
        closure_gate = verified_by = None
        history: list[str] = []  # PASSes of the closure gate since the defect's first failure on it (past successes)
        attempt: dict | None = None  # the latest decisive re-verification of the cited gates since the first failure
        if valid:
            # baseline = the latest cited failure; closure gate = the most downstream gate that failed, from the signed
            # records (not the agent-written `gate`), so a G4 re-pass cannot close a defect whose G5 still fails
            last = max(valid, key=lambda e: e.seq)
            closure_gate = max((str(e.record.get("gate")) for e in valid),
                               key=lambda g: GATE_ORDER.index(g) if g in GATE_ORDER else -1)
            first = min((e for e in valid if str(e.record.get("gate")) == closure_gate), key=lambda e: e.seq)
            for e in gate_entries(entries, wi, closure_gate):
                if e.seq > first.seq and e.record.get("type") == "gate" and e.record.get("status") == "PASSED" \
                        and not is_na_record(e.record):
                    history.append(e.id)
                    if verified_by is None and e.seq > last.seq:
                        verified_by = e.id
            # Decisive = PASSED or a failure record on a gate this DEFECT cites a failure of, after its first cited
            # failure. REVIEW_REQUIRED and environment BLOCKED are skipped, as in the 3-strike count
            # (consecutive_same_failures). Per gate the latest decisive result counts, so an upstream re-pass (G4)
            # does not hide a downstream failure (G5) that has not been re-run yet.
            cited_gates = {str(e.record.get("gate")) for e in valid}
            start = min(e.seq for e in valid)
            latest_by_gate: dict[str, tuple[int, dict]] = {}
            for e in entries:
                rec = e.record
                if (e.seq <= start or rec.get("type") != "gate" or rec.get("work_item") != wi
                        or str(rec.get("gate")) not in cited_gates):
                    continue
                if (rec.get("status") == "PASSED" and not is_na_record(rec)) or is_failure_record(rec):
                    a = {"record": e.id, "gate": rec.get("gate"), "status": rec.get("status"),
                         "failure": is_failure_record(rec)}
                    if rec.get("blocked_reason"):
                        a["blocked_reason"] = rec["blocked_reason"]
                    latest_by_gate[str(rec.get("gate"))] = (e.seq, a)
            failed_gates = [x for x in latest_by_gate.values() if x[1]["failure"]]
            pick = max(failed_gates or list(latest_by_gate.values()), key=lambda x: x[0], default=None)
            attempt = pick[1] if pick else None
        withheld = None
        if evidence_check is not None:
            relied = {e.id: e for e in [*valid, *([by_id[verified_by]] if verified_by else [])]}
            for e in relied.values():
                probs = [p for ev in e.record.get("evidence") or [] if isinstance(ev, dict)
                         for p in check(str(ev.get("path")), ev.get("sha256"))]
                if probs:
                    errors.append(_problem("evidence_integrity", e.id,
                                           f"{did} relies on {e.id}, whose evidence does not match the signed ledger: "
                                           + "; ".join(probs[:4])))
            if verified_by and any(p["category"] == "evidence_integrity" for p in errors):
                withheld, verified_by = verified_by, None
        view.update(citations=citations,
                    unknown_records=sorted(r for r in set(found) if not (
                        r in by_id and by_id[r].record.get("work_item") == wi and by_id[r].record.get("type") == "gate")),
                    failing_tests_by_record=per_record, failing_tests=failing, unlinked_failing_tests=unlinked,
                    unknown_tests=unknown, closure_gate=closure_gate, verified_by=verified_by, verification_withheld=withheld,
                    verification_history=history, last_verification=attempt, errors=errors, warnings=warnings)
        out.append(view)
    return out


# ---------------------------------------------------------------- state (shared with status)
def gate_state(ctx: Ctx, gate: str, current_manifests: dict[str, dict] | None = None) -> dict:
    st = _gate_state(ctx, gate, current_manifests)
    if gate == "G6" and st["status"] != "NOT_IMPLEMENTED":
        _g6_state(ctx, st)
    if gate == "G7" and st["status"] != "NOT_IMPLEMENTED":
        _g7_state(ctx, st)
    return st


def _g6_state(ctx: Ctx, st: dict) -> None:
    """G6 display facts from its last record (0.2.0): not evaluated yet, N/A, interface coverage."""
    last = last_eval(ctx.entries, ctx.wi, "G6")
    if last is None:
        if st["status"] in ("IN_PROGRESS", "NOT_STARTED"):
            st["not_evaluated"] = True
        return
    rec = last.record
    app = rec.get("applicability")
    if app:
        st["applicability"] = app
    if st["status"] == "PASSED" and app == "not_applicable":
        st["display_status"] = "N/A"
        basis = rec.get("applicability_basis") or {}
        st["na_reason"] = basis.get("g2_reason") or basis.get("na_reason") or basis.get("approach")
        st["external_endpoints"] = basis.get("external_endpoints") or []
    elif st["status"] == "PASSED" and app == "required":
        ifs = [i for i in rec.get("interfaces") or [] if isinstance(i, dict)]
        levels = rec.get("executed_levels") or {}
        st["coverage"] = {"interfaces": len(ifs), "covered": sum(1 for i in ifs if i.get("covered")),
                          "integration_tests_passed": sum(1 for t, s in (rec.get("executed_tests") or {}).items()
                                                          if s == "passed" and levels.get(t) == "integration"),
                          # D44: passed tests whose evidence is below test level are shown, never counted
                          "not_counted": [f"{t} ({i.get('id')}): {EVIDENCE_LABELS.get(v.get('evidence_level'), '?')}"
                                          for i in ifs for t, v in sorted((i.get("tests") or {}).items())
                                          if isinstance(v, dict) and v.get("status") == "passed"
                                          and v.get("evidence_level") not in (None, "test_level")]}


def _g7_state(ctx: Ctx, st: dict) -> None:
    """G7 display facts from its last record (0.3.0): not evaluated yet, acceptance criteria verified by this PASS."""
    last = last_eval(ctx.entries, ctx.wi, "G7")
    if last is None:
        if st["status"] in ("IN_PROGRESS", "NOT_STARTED"):
            st["not_evaluated"] = True
        return
    rec = last.record
    if st["status"] != "PASSED":
        return
    cov = rec.get("requirements_coverage") if isinstance(rec.get("requirements_coverage"), dict) else {}
    acs = [(ac, v) for r in cov.values() if isinstance(r, dict)
           for ac, v in (r.get("acceptance_criteria") or {}).items() if isinstance(v, dict)]
    levels = rec.get("executed_levels") or {}
    st["acceptance"] = {"requirements": len(cov), "acceptance_criteria": len(acs),
                        "verified": sum(1 for _a, v in acs if v.get("verified")),
                        "system_tests_passed": sum(1 for t, s in (rec.get("executed_tests") or {}).items()
                                                   if s == "passed" and levels.get(t) == "system"),
                        "not_system_tested": sorted(a for a, v in acs if not v.get("tests"))}


def _gate_state(ctx: Ctx, gate: str, current_manifests: dict[str, dict] | None = None) -> dict:
    gd = gate_def(gate)
    st: dict[str, Any] = {"gate": gate, "name": gd["name"], "status": None, "notes": []}
    if not gd["implemented"]:
        st["status"] = "NOT_IMPLEMENTED"
        st["notes"].append("extension gate, not implemented in the MVP")
        return st
    if not ctx.integrity.ok:
        st["status"] = "BLOCKED"
        st["notes"].extend(ctx.integrity.problems)
        return st
    last = last_eval(ctx.entries, ctx.wi, gate)
    cache = current_manifests if current_manifests is not None else {}
    if gate not in cache:
        cache[gate] = compute_manifest(ctx.project, ctx.wi, gate)
    current = cache[gate]
    st["manifest_hash_current"] = hash_obj(current)
    if last is None:
        own = [a for a in gd["required_artifacts"] if (ctx.project.wi_root / ctx.wi / a).is_file()]
        pg = prev_gate(gate)
        prev_ok = pg is None or gate_state(ctx, pg, cache)["status"] == "PASSED"
        st["status"] = "IN_PROGRESS" if (own or (pg is not None and prev_ok)) else "NOT_STARTED"
        return st
    rec = last.record
    st.update({"record_id": rec.get("record_id"), "evaluated_at": rec.get("evaluated_at"),
               "manifest_hash_recorded": rec.get("manifest", {}).get("hash"),
               "review_required_by": rec.get("review_required_by") or []})
    changed = diff_manifest(rec.get("manifest", {}).get("files", {}), current)
    core_changed = rec.get("validator", {}).get("core_hash") != ctx.integrity.core_hash
    status = rec.get("status")
    if status == "PASSED":
        if changed or core_changed:
            st["status"] = "STALE"
            st["changed_files"] = changed
            if core_changed:
                st["notes"].append("validator core changed since this PASS")
            return st
        pg = prev_gate(gate)
        upstream = gate_state(ctx, pg, cache)["status"] if pg else "PASSED"
        if upstream != "PASSED":
            st["status"] = "STALE"
            st["notes"].append(f"upstream {pg} is {upstream}; this PASS no longer stands on a passed gate")
        else:
            st["status"] = "PASSED"
        return st
    if status == "BLOCKED" and rec.get("blocked_reason") == "three_consecutive_identical_failures" \
            and unblocked_after(ctx.entries, ctx.wi, gate, last.seq):
        status = "FAILED"
        st["notes"].append("unblocked by the user; rework and re-evaluate")
    st["status"] = status
    if status in ("FAILED", "BLOCKED"):
        st["failed_checks"] = failed_checks(rec)
        st["failing_tests"] = failing_tests(rec)
    if rec.get("blocked_reason"):
        st["blocked_reason"] = rec["blocked_reason"]
    if changed:
        st["notes"].append("inputs changed since this evaluation; re-evaluate")
        st["changed_files"] = changed
    return st


# ---------------------------------------------------------------- shared checks
def _schema_check(ctx: Ctx, cid: str, names: list[str]) -> Check:
    problems: list[str] = []
    for name in names:
        if name in ctx.art_errors:
            err = ctx.art_errors[name]
            problems.append(f"{name}: required artifact missing" if err == "missing" else err)
            continue
        errs = validate(ctx.arts[name], load_schema(SCHEMA_FOR[name]))
        problems.extend(f"{name} {e}" for e in errs)
        art = ctx.arts[name]
        if isinstance(art, dict) and "work_item" in art and art["work_item"] != ctx.wi:
            problems.append(f"{name}: work_item is {art['work_item']!r}, expected {ctx.wi!r}")
        if name == "workitem.json" and isinstance(art, dict) and art.get("id") != ctx.wi:
            problems.append(f"workitem.json: id is {art.get('id')!r}, expected {ctx.wi!r}")
    if problems:
        return Check(cid, "mechanical", "fail", "schema validation failed", problems[:50])
    return Check(cid, "mechanical", "pass", f"{', '.join(names)} valid")


def _optional_schema(ctx: Ctx, name: str) -> list[str]:
    if name in ctx.art_errors:
        err = ctx.art_errors[name]
        return [] if err == "missing" else [err]
    return [f"{name} {e}" for e in validate(ctx.arts[name], load_schema(SCHEMA_FOR[name]))]


def _ids_check(ctx: Ctx, cid: str, ids: list[str], extra: list[str] | None = None) -> Check:
    problems = list(extra or [])
    for i, n in Counter(ids).items():
        if n > 1:
            problems.append(f"{i} defined {n} times")
    for i in ids:
        if i in ctx.foreign_ids:
            problems.append(f"{i} already used by {ctx.foreign_ids[i]} (ids are project-unique; use 'vmodel next-id')")
    if problems:
        return Check(cid, "mechanical", "fail", "id problems", sorted(set(problems)))
    return Check(cid, "mechanical", "pass", f"{len(ids)} ids unique")


def check_review(ctx: Ctx, gate: str, mhash: str) -> Check:
    cid = f"{gate}.REVIEW"
    path = ctx.project.wi_root / ctx.wi / "reviews" / f"{gate}.json"
    base = {"machine_verified": False, "review_required_by": REVIEWER}
    if not path.is_file():
        return Check(cid, "ai_review", "pending", f"no review yet: run the {REVIEWER} subagent for {gate}",
                     data={**base, "target_hash_expected": mhash})
    try:
        rv = load_json(path, f"reviews/{gate}.json")
    except ArtifactError as exc:
        return Check(cid, "ai_review", "fail", str(exc), data=base)
    errs = validate(rv, load_schema("review"))
    if errs:
        return Check(cid, "ai_review", "fail", "review file invalid", errs[:20], data=base)
    data = {**base, "reviewer": rv["reviewer"], "verdict": rv["verdict"], "review_sha256": sha256_file(path),
            "reviewed_at": rv["reviewed_at"]}
    if rv["gate"] != gate or rv["work_item"] != ctx.wi:
        return Check(cid, "ai_review", "fail", f"review is for {rv['work_item']}/{rv['gate']}", data=data)
    if rv["reviewer"] != REVIEWER:
        return Check(cid, "ai_review", "fail", f"reviewer must be {REVIEWER}, got {rv['reviewer']!r}", data=data)
    if rv["target_hash"] != mhash:
        return Check(cid, "ai_review", "pending",
                     f"review targets {short(rv['target_hash'])}, current inputs are {short(mhash)}; re-review needed",
                     data={**data, "target_hash_expected": mhash})
    submitted = [e for e in ctx.entries if e.record.get("type") == "review" and e.record.get("work_item") == ctx.wi
                 and e.record.get("gate") == gate and e.record.get("review_sha256") == data["review_sha256"]]
    if not submitted:
        return Check(cid, "ai_review", "pending",
                     f"review file not submitted: the {REVIEWER} subagent must run 'vmodel review-submit {ctx.wi} "
                     f"{gate}' after writing it", data={**data, "target_hash_expected": mhash})
    data["submitted_in"] = submitted[-1].id
    open_major = [f["id"] for f in rv["findings"] if f["severity"] == "major" and f["status"] == "open"]
    if rv["verdict"] == "reject":
        return Check(cid, "ai_review", "fail", f"verifier rejected: {rv['summary'][:300]}", open_major, data=data)
    if open_major:
        return Check(cid, "ai_review", "fail", "approve verdict with open major findings is inconsistent", open_major,
                     data=data)
    return Check(cid, "ai_review", "pass", f"approved by {REVIEWER} (AI review, not machine-verified)", data=data)


def _items(doc: Any, key: str) -> list[dict]:
    """Defensive accessor: artifacts are agent-written and may have any JSON shape."""
    if not isinstance(doc, dict) or not isinstance(doc.get(key), list):
        return []
    return [x for x in doc[key] if isinstance(x, dict)]


def _str_list(value: Any) -> list[str]:
    return [x for x in value if isinstance(x, str)] if isinstance(value, list) else []


def _change_requests(ctx: Ctx) -> list[dict]:
    return _items(ctx.arts.get("change-requests.json"), "change_requests")


def _defects(ctx: Ctx) -> list[dict]:
    return _items(ctx.arts.get("defects.json"), "defects")


# ---------------------------------------------------------------- G1
VAGUE_RE = re.compile(
    r"\b(appropriate(ly)?|fast|quick(ly)?|user[- ]friendly|easy|easily|efficient(ly)?|etc\.?|as needed|tbd|"
    r"flexible|robust|optimal|adequate|reasonabl[ey]|several|some)\b"
    r"|적절|빠르게|신속|쉽게|편리|효율적|가능한 한|충분히|유연|최적|추후|(?:^|\s)등(?=[\s,.)]|$)",
    re.IGNORECASE,
)


def eval_g1(ctx: Ctx, files: dict, mhash: str) -> tuple[list[Check], dict, list[dict]]:
    checks = [_schema_check(ctx, "G1.SCHEMA", ["workitem.json", "requirements.json"])]
    cr_errs = _optional_schema(ctx, "change-requests.json")
    if cr_errs:
        checks.append(Check("G1.SCHEMA", "mechanical", "fail", "change-requests.json invalid", cr_errs[:20]))
    if any(c.status == "fail" for c in checks):
        return checks, {}, []
    rq = ctx.arts["requirements.json"]
    g = ctx.graph
    reqs = rq["requirements"]

    # IDS
    ids = [r["id"] for r in reqs]
    ac_ids, extra = [], []
    for r in reqs:
        num = r["id"].split("-", 1)[1]
        for ac in r["acceptance_criteria"]:
            ac_ids.append(ac["id"])
            if not ac["id"].startswith(f"AC-{num}-"):
                extra.append(f"{ac['id']} should be named AC-{num}-n (belongs to {r['id']})")
    checks.append(_ids_check(ctx, "G1.IDS", ids + ac_ids, extra))

    # ACCEPTANCE
    missing = [rid for rid in g.active("functional") if not g.reqs[rid]["acceptance_criteria"]]
    checks.append(Check("G1.ACCEPTANCE", "mechanical", "fail" if missing else "pass",
                        "functional requirements without acceptance criteria" if missing
                        else f"{len(g.active('functional'))} functional requirements have acceptance criteria", missing))

    # CONFLICTS
    ca = rq["conflict_analysis"]
    probs = []
    if not ca["performed"]:
        probs.append("conflict_analysis.performed is false")
    for i, c in enumerate(ca["conflicts"]):
        for rid in c["ids"]:
            if rid not in g.reqs:
                probs.append(f"conflicts[{i}] references unknown {rid}")
        if c["status"] != "resolved" or not c.get("resolution", "").strip():
            probs.append(f"conflicts[{i}] ({'/'.join(c['ids'])}) is not resolved")
    checks.append(Check("G1.CONFLICTS", "mechanical", "fail" if probs else "pass",
                        "conflict analysis incomplete" if probs else f"{len(ca['conflicts'])} conflict(s), all resolved",
                        probs))

    # OPEN_ISSUES
    pending_user, bad, open_minor = [], [], []
    for iss in rq["open_issues"]:
        if iss["critical"] and iss["status"] == "open":
            pending_user.append(f"{iss['id']}: {iss['description'][:120]}")
        elif iss["critical"] and iss["status"] == "resolved" and (
                iss.get("decided_by") != "user" or not iss.get("resolution", "").strip()):
            bad.append(f"{iss['id']}: critical issue must be decided_by 'user' with a resolution")
        elif not iss["critical"] and iss["status"] == "open":
            open_minor.append(iss["id"])
    if bad:
        checks.append(Check("G1.OPEN_ISSUES", "mechanical", "fail", "critical issues resolved without the user", bad))
    elif pending_user:
        checks.append(Check("G1.OPEN_ISSUES", "mechanical", "pending",
                            "critical issues need a user decision (ask the user once, record decided_by='user')",
                            pending_user, data={"review_required_by": "user"}))
    elif open_minor:
        checks.append(Check("G1.OPEN_ISSUES", "mechanical", "warn",
                            "non-critical open issues remain (recorded, not blocking)", open_minor))
    else:
        checks.append(Check("G1.OPEN_ISSUES", "mechanical", "pass", "no open critical issues"))

    # CHANGE_CONTROL
    cur_items = item_hashes(ctx.arts, ["requirements.json"])
    checks.append(_change_control(ctx, "G1", "G1.CHANGE_CONTROL", cur_items, prefixes=("REQ-",)))

    # AMBIGUITY (warning only)
    vague = []
    for r in reqs:
        texts = [r["description"], *[a["criterion"] for a in r["acceptance_criteria"]]]
        for t in texts:
            m = VAGUE_RE.search(t)
            if m:
                vague.append(f"{r['id']}: '{m.group(0).strip()}' in \"{t[:80]}\"")
                break
    checks.append(Check("G1.AMBIGUITY", "mechanical", "warn" if vague else "pass",
                        "possibly vague wording; make it measurable or record why it is fine" if vague
                        else "no vague wording detected", vague))

    checks.append(check_review(ctx, "G1", mhash))
    return checks, {"item_hashes": cur_items}, []


def _change_control(ctx: Ctx, gate: str, cid: str, cur_items: dict[str, str], prefixes: tuple[str, ...]) -> Check:
    last_pass = last_with_status(ctx.entries, ctx.wi, gate, "PASSED")
    if not last_pass:
        return Check(cid, "mechanical", "pass", "first evaluation; no baseline")
    old = {k: v for k, v in (last_pass.record.get("item_hashes") or {}).items() if k.startswith(prefixes)}
    new = {k: v for k, v in cur_items.items() if k.startswith(prefixes)}
    changed = sorted(k for k in set(old) | set(new) if old.get(k) != new.get(k))
    if not changed:
        return Check(cid, "mechanical", "pass", f"no change since {last_pass.id}")
    covered: set[str] = set()
    for cr in _change_requests(ctx):
        if cr.get("status") == "rejected":
            continue
        covered.update(_str_list(cr.get("affected")))
        covered.update(_str_list(cr.get("removed_ids")))
    uncovered = [k for k in changed if k not in covered]
    if uncovered:
        return Check(cid, "mechanical", "fail",
                     f"changed since {last_pass.id} without a change request (add a CR listing them in 'affected')",
                     uncovered)
    return Check(cid, "mechanical", "pass", f"{len(changed)} change(s) since {last_pass.id} covered by change requests",
                 changed)


# ---------------------------------------------------------------- G2
def eval_g2(ctx: Ctx, files: dict, mhash: str) -> tuple[list[Check], dict, list[dict]]:
    checks = [_schema_check(ctx, "G2.SCHEMA", ["architecture.json"])]
    if checks[0].status == "fail":
        return checks, {}, []
    ar = ctx.arts["architecture.json"]
    g = ctx.graph
    checks.append(_ids_check(ctx, "G2.IDS", [c["id"] for c in ar["components"]] + [i["id"] for i in ar["interfaces"]]))

    unmapped = [rid for rid in g.active("functional") if not g.comps_for_req(rid)]
    dangling = [d for d in g.dangling() if d.startswith("ARCH-")]
    checks.append(Check("G2.REQ_MAPPING", "mechanical", "fail" if unmapped or dangling else "pass",
                        "requirements not mapped to components / dangling references" if unmapped or dangling
                        else "all functional requirements mapped", unmapped + dangling))

    probs = [d for d in g.dangling() if d.startswith("IF-")]
    if len(ar["components"]) > 1 and not ar["interfaces"]:
        probs.append("2+ components but no interface defined")
    checks.append(Check("G2.INTERFACES", "mechanical", "fail" if probs else "pass",
                        "interface problems" if probs else f"{len(ar['interfaces'])} interface(s) consistent", probs))

    nfr_ids = g.active("non-functional") + g.active("constraint")
    mapped = {m["requirement"] for m in ar["nfr_mapping"]}
    probs = [f"{rid} not addressed in nfr_mapping" for rid in nfr_ids if rid not in mapped]
    for m in ar["nfr_mapping"]:
        if m["requirement"] not in g.reqs:
            probs.append(f"nfr_mapping references unknown {m['requirement']}")
        for c in m["components"]:
            if c not in g.comps:
                probs.append(f"nfr_mapping {m['requirement']} references unknown {c}")
    checks.append(Check("G2.NFR", "mechanical", "fail" if probs else "pass",
                        "non-functional requirements not reflected" if probs
                        else f"{len(nfr_ids)} non-functional/constraint requirement(s) addressed", probs))

    its = ar["integration_test_strategy"]
    covered = set(its["interfaces_covered"])
    probs = [f"{iid} not covered by integration_test_strategy" for iid in g.ifaces if iid not in covered]
    probs += [f"integration_test_strategy covers unknown {i}" for i in covered if i not in g.ifaces]
    checks.append(Check("G2.INTEGRATION_STRATEGY", "mechanical", "fail" if probs else "pass",
                        "integration test strategy incomplete" if probs else "integration test strategy covers all interfaces",
                        probs))

    checks.append(Check("G2.TRADEOFFS", "mechanical", "pass" if ar["tradeoffs"] else "warn",
                        f"{len(ar['tradeoffs'])} trade-off(s) recorded" if ar["tradeoffs"] else "no trade-off recorded"))
    checks.append(check_review(ctx, "G2", mhash))
    return checks, {"item_hashes": item_hashes(ctx.arts, ["architecture.json"])}, []


# ---------------------------------------------------------------- G3
def eval_g3(ctx: Ctx, files: dict, mhash: str) -> tuple[list[Check], dict, list[dict]]:
    checks = [_schema_check(ctx, "G3.SCHEMA", ["design.json", "tests.json"])]
    for name in ("change-requests.json", "defects.json"):
        errs = _optional_schema(ctx, name)
        if errs:
            checks.append(Check("G3.SCHEMA", "mechanical", "fail", f"{name} invalid", errs[:20]))
    if any(c.status == "fail" for c in checks):
        return checks, {}, []
    g = ctx.graph
    units = ctx.arts["design.json"]["units"]
    tests = ctx.arts["tests.json"]["tests"]
    checks.append(_ids_check(ctx, "G3.IDS", [u["id"] for u in units] + [t["id"] for t in tests]))

    probs = []
    for cid in g.comps:
        if not any(u["component"] == cid for u in units):
            probs.append(f"{cid} has no design unit")
    for rid in g.active("functional"):
        if not g.units_for_req(rid):
            probs.append(f"{rid} is not realised by any design unit")
    probs += [d for d in g.dangling() if d.startswith("DESIGN-")]
    checks.append(Check("G3.DESIGN_COVERAGE", "mechanical", "fail" if probs else "pass",
                        "design coverage gaps" if probs else f"{len(units)} unit(s) cover all components and requirements",
                        probs))

    probs = []
    for u in units:
        leaf = u["name"].split(".")[-1]
        if leaf not in u["signature"]:
            probs.append(f"{u['id']}: signature does not mention '{leaf}'")
        if not u["module"].endswith(".py"):
            probs.append(f"{u['id']}: module must be a .py path relative to the project root")
    checks.append(Check("G3.CONTRACTS", "mechanical", "fail" if probs else "pass",
                        "contract problems" if probs else "every unit has signature, contract, errors and boundaries",
                        probs))

    probs = []
    for u in units:
        uts = g.tests_for_unit(u["id"])
        cats = {g.tests[t]["category"] for t in uts}
        if not uts:
            probs.append(f"{u['id']}: no unit test")
            continue
        if "normal" not in cats:
            probs.append(f"{u['id']}: no normal-case unit test")
        if u["errors"] and "abnormal" not in cats:
            probs.append(f"{u['id']}: declares errors but has no abnormal unit test")
        if u["boundary_conditions"] and "boundary" not in cats:
            probs.append(f"{u['id']}: declares boundary conditions but has no boundary unit test")
    checks.append(Check("G3.UNIT_TESTS", "mechanical", "fail" if probs else "pass",
                        "unit test design gaps" if probs else f"{len(g.unit_tests())} unit test spec(s) cover all units",
                        probs))

    probs = []
    for iid in g.ifaces:
        if not any(t["level"] == "integration" and iid in t["verifies"] for t in tests):
            probs.append(f"{iid}: no integration test spec")
    for rid in g.active("functional"):
        for ac in g.reqs[rid]["acceptance_criteria"]:
            if not any(t["level"] == "system" and ac["id"] in (t.get("acceptance_criteria") or []) for t in tests):
                probs.append(f"{ac['id']} ({rid}): no system test spec")
    checks.append(Check("G3.INTEGRATION_SYSTEM_TESTS", "mechanical", "fail" if probs else "pass",
                        "integration/system test planning gaps" if probs
                        else "integration and system test specs cover interfaces and acceptance criteria", probs))

    probs = [d for d in g.dangling() if d.startswith("TEST-")]
    probs += [f"{rid} is not covered by any test" for rid in g.active("functional") if not g.tests_for_req(rid)]
    checks.append(Check("G3.TRACE", "mechanical", "fail" if probs else "pass",
                        "traceability problems" if probs else "requirements, design and tests are linked", probs))

    cur_items = item_hashes(ctx.arts, ["design.json", "tests.json"])
    checks.append(_no_silent_removal(ctx, cur_items))
    checks.append(check_review(ctx, "G3", mhash))
    return checks, {"item_hashes": cur_items}, []


def _no_silent_removal(ctx: Ctx, cur_items: dict[str, str]) -> Check:
    last_pass = last_with_status(ctx.entries, ctx.wi, "G3", "PASSED")
    if not last_pass:
        return Check("G3.NO_SILENT_REMOVAL", "mechanical", "pass", "first evaluation; no baseline")
    removed = sorted(set(last_pass.record.get("item_hashes") or {}) - set(cur_items))
    allowed: set[str] = set()
    for cr in _change_requests(ctx):
        if cr.get("status") != "rejected":
            allowed.update(_str_list(cr.get("removed_ids")))
    for d in _defects(ctx):
        allowed.update(_str_list(d.get("removed_ids")))
    silent = [r for r in removed if r not in allowed]
    if silent:
        return Check("G3.NO_SILENT_REMOVAL", "mechanical", "fail",
                     f"removed since {last_pass.id} without a CR/defect listing them in removed_ids", silent)
    return Check("G3.NO_SILENT_REMOVAL", "mechanical", "pass",
                 f"{len(removed)} justified removal(s)" if removed else "nothing removed", removed)


# ---------------------------------------------------------------- G4
def _find_symbol(tree: ast.AST, name: str, kind: str) -> bool:
    parts = name.split(".")
    body = getattr(tree, "body", [])
    if len(parts) == 1:
        for node in body:
            if kind == "class" and isinstance(node, ast.ClassDef) and node.name == parts[0]:
                return True
            if kind != "class" and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == parts[0]:
                return True
        return False
    for node in body:
        if isinstance(node, ast.ClassDef) and node.name == parts[0]:
            return any(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == parts[1] for n in node.body)
    return False


RESULT_HOOKS = {
    "pytest_sessionfinish", "pytest_unconfigure", "pytest_runtest_makereport", "pytest_runtest_logreport",
    "pytest_report_teststatus", "pytest_terminal_summary", "pytest_runtestloop", "pytest_collection_modifyitems",
    "pytest_collection_finish", "pytest_runtest_protocol", "pytest_pyfunc_call", "pytest_itemcollected",
    "pytest_collectreport", "pytest_make_collect_report", "pytest_cmdline_main", "pytest_load_initial_conftests",
}
RESULT_ATTRS = {"exitstatus", "xmlpath", "testsfailed", "testscollected", "longrepr", "junitxml", "_xml"}


def _test_functions(tree: ast.AST | None) -> list[str]:
    if tree is None:
        return []
    names = []
    for node in getattr(tree, "body", []):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test"):
            names.append(node.name)
        elif isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
            names += [f"{node.name}.{n.name}" for n in node.body
                      if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith("test")]
    return names


def _result_tampering(tree: ast.AST) -> list[str]:
    out = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and (
                node.name in RESULT_HOOKS or node.name.startswith("pytest_junit")):
            out.append(f"line {node.lineno}: defines pytest hook {node.name}")
        elif isinstance(node, ast.Attribute) and node.attr in RESULT_ATTRS:
            out.append(f"line {node.lineno}: uses .{node.attr}")
        elif isinstance(node, ast.Attribute) and node.attr == "_exit" and isinstance(node.value, ast.Name) \
                and node.value.id == "os":
            out.append(f"line {node.lineno}: calls os._exit")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and (
                "junitxml" in node.value or "PYTEST_ADDOPTS" in node.value or "VMODEL_TRACE" in node.value):
            out.append(f"line {node.lineno}: string mentions {node.value[:40]!r}")
    return out


def _substitute(argv: list[str], mapping: dict[str, str | list[str]]) -> list[str]:
    out: list[str] = []
    for a in argv:
        if a in mapping and isinstance(mapping[a], list):
            out.extend(mapping[a])  # type: ignore[arg-type]
            continue
        for k, v in mapping.items():
            if isinstance(v, str):
                a = a.replace(k, v)
        out.append(a)
    return out


def eval_g4(ctx: Ctx, files: dict, mhash: str) -> tuple[list[Check], dict, list[dict]]:
    checks = [_schema_check(ctx, "G4.FILES", ["design.json", "tests.json"])]
    if checks[0].status == "fail":
        checks[0].id = "G4.FILES"
        return checks, {}, []
    p = ctx.project
    src, tst = p.source_files(), p.test_files()
    probs = []
    if not src:
        probs.append(f"no source files match {p.config()['paths']['source']}")
    if not tst:
        probs.append(f"no test files match {p.config()['paths']['tests']}")
    checks[0] = Check("G4.FILES", "mechanical", "fail" if probs else "pass",
                      "code files missing" if probs else f"{len(src)} source / {len(tst)} test file(s)", probs)
    evidence: list[dict] = []

    # UNEXPECTED_CODE: every .py file in the tree must be under a configured (designed or reviewed) path
    support = p.build_config_files() + p.other_code_files()
    allowed = {p.rel(f) for f in src + tst + support}
    probs = [f"{rel}: Python file outside the configured source/tests/build_config/other paths"
             for rel in files if rel.endswith(".py") and rel not in allowed]
    probs += [f"{rel}: symlink in the project tree (not allowed for verified code)"
              for rel, h in files.items() if h.startswith("SYMLINK:")]
    checks.append(Check("G4.UNEXPECTED_CODE", "mechanical", "fail" if probs else "pass",
                        "code outside the verified paths could change test results" if probs
                        else "no Python code outside the configured paths, no symlinks", probs))

    # SYNTAX (built-in)
    trees: dict[str, ast.AST] = {}
    probs = []
    for f in dict.fromkeys(src + tst + [x for x in support if x.suffix == ".py"]):
        rel = p.rel(f)
        try:
            trees[rel] = ast.parse(f.read_bytes(), filename=rel)
        except SyntaxError as exc:
            probs.append(f"{rel}:{exc.lineno}: {exc.msg}")
        except (ValueError, OSError, RecursionError, MemoryError) as exc:
            probs.append(f"{rel}: {exc.__class__.__name__}: {exc}")
    checks.append(Check("G4.SYNTAX", "execution", "fail" if probs else "pass",
                        "syntax errors" if probs else f"{len(trees)} file(s) parsed by the validator (Python AST)",
                        probs, data={"tool": "python-ast (built-in)", "python": runner.runtime_info()["validator_python"]}))

    # LINT (executed by the validator)
    checks.append(_lint(ctx, src + tst, mhash, evidence))

    # DESIGN_CONFORMANCE
    g = ctx.graph
    found_units: set[str] = set()
    probs = []
    src_rel = {p.rel(f) for f in src}
    for uid, u in sorted(g.units.items()):
        mod = u["module"].replace("\\", "/")
        if mod not in src_rel:
            probs.append(f"{uid}: module {mod} is not a source file under the configured paths")
            continue
        tree = trees.get(mod)
        if tree is None:
            probs.append(f"{uid}: module {mod} could not be parsed")
        elif not _find_symbol(tree, u["name"], u["kind"]):
            probs.append(f"{uid}: {u['kind']} '{u['name']}' not defined in {mod}")
        else:
            found_units.add(uid)
    checks.append(Check("G4.DESIGN_CONFORMANCE", "mechanical", "fail" if probs else "pass",
                        "code does not match the design" if probs else f"{len(found_units)} design unit(s) implemented",
                        probs))

    # TEST_CODE: test functions (AST, not comments) named with exactly one TEST id
    present: set[str] = set()
    multi: list[str] = []
    for f in tst:
        tree = trees.get(p.rel(f))
        for fn in _test_functions(tree):
            ids = test_ids_in_text(fn)
            if len(ids) > 1:
                multi.append(f"{p.rel(f)}::{fn} names more than one TEST id {sorted(ids)}")
            present |= ids if len(ids) == 1 else set()
    integ = g.integration_tests()  # 0.2.0 (REQ-G6-09): integration specs need test functions too
    missing = sorted(t for t in [*g.unit_tests(), *integ] if t not in present)
    orphans = sorted(present - set(g.tests))
    status = "fail" if missing or multi else ("warn" if orphans else "pass")
    what = "unit/integration test specs" if integ else "unit test specs"
    done = (f"{len(g.unit_tests())} unit and {len(integ)} integration test spec(s) implemented" if integ
            else f"{len(g.unit_tests())} unit test spec(s) implemented")
    checks.append(Check("G4.TEST_CODE", "mechanical", status,
                        f"{what} without a test function test_TEST_nnn_... / ambiguous test names"
                        if missing or multi else ("test code references TEST ids not in tests.json" if orphans
                                                  else done),
                        multi + missing if (missing or multi) else orphans))

    # TEST_INTEGRITY: test/support code must not tamper with how results are reported
    probs = []
    for f in dict.fromkeys(tst + [x for x in support if x.suffix == ".py"]):
        tree = trees.get(p.rel(f))
        if tree is not None:
            probs += [f"{p.rel(f)}: {x}" for x in _result_tampering(tree)]
    checks.append(Check("G4.TEST_INTEGRITY", "mechanical", "fail" if probs else "pass",
                        "test code touches result reporting (pytest result hooks, exit status, junit, os._exit)"
                        if probs else "no result-reporting hooks in test or support code", probs))

    # REQ_IMPLEMENTED
    probs = [rid for rid in g.active("functional") if not (set(g.units_for_req(rid)) & found_units)]
    checks.append(Check("G4.REQ_IMPLEMENTED", "mechanical", "fail" if probs else "pass",
                        "requirements without implemented design units" if probs
                        else "every functional requirement reaches implemented code", probs))

    # 0.2.0: integration readiness, only for work items with interfaces / integration specs (REQ-G6-10-13)
    review = check_review(ctx, "G4", mhash)
    accepted = load_review(ctx, "G4") if review.status == "pass" else None
    if g.ifaces:
        checks.append(_interface_implemented(ctx, trees))
    if integ:
        wd, _ix = g6_wiring(ctx, trees)
        checks.append(_integration_wiring(ctx, wd, accepted, mhash))
    if g.ifaces and review.status == "pass":
        review = _review_interfaces(ctx, review, accepted, trees, mhash)
    checks.append(review)
    return checks, {}, evidence


# ---------------------------------------------------------------- G4 integration readiness (0.2.0)
def load_review(ctx: Ctx, gate: str) -> dict | None:
    path = ctx.project.wi_root / ctx.wi / "reviews" / f"{gate}.json"
    try:
        rv = load_json(path, f"reviews/{gate}.json")
    except (ArtifactError, OSError):
        return None
    return rv if isinstance(rv, dict) else None


def _defines(tree: ast.AST | None, sym: str) -> bool:
    if tree is None or not sym:
        return False
    if "." in sym:
        return _find_symbol(tree, sym, "method")
    if _find_symbol(tree, sym, "class") or _find_symbol(tree, sym, "function"):
        return True
    return any(isinstance(n, ast.ClassDef) and any(isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))
                                                   and m.name == sym for m in n.body)
               for n in getattr(tree, "body", []))


def _component_modules(ctx: Ctx, component: Any) -> list[str]:
    return sorted({u["module"].replace("\\", "/") for u in ctx.graph.units.values()
                   if u.get("component") == component and isinstance(u.get("module"), str)})


def _parse_trees(ctx: Ctx, files: list[Path]) -> dict[str, ast.AST]:
    trees: dict[str, ast.AST] = {}
    for f in files:
        rel = ctx.project.rel(f)
        try:
            trees[rel] = ast.parse(f.read_bytes(), filename=rel)
        except (SyntaxError, ValueError, OSError, RecursionError, MemoryError):
            continue
    return trees


def g6_wiring(ctx: Ctx, trees: dict[str, ast.AST] | None = None) -> tuple[dict, wiring.Index]:
    """The static integration analysis G4 and G6 judge from (G6 recomputes it from the files it verifies)."""
    p = ctx.project
    src, tst = p.source_files(), p.test_files()
    if trees is None:
        trees = _parse_trees(ctx, src + tst)
    ix = wiring.Index.build(p.root, p.rel, src, tst, trees, roots=import_roots(p))
    return wiring.interface_wiring(ix, ctx.graph, [p.rel(f) for f in tst]), ix


def _is_file(path: Path) -> bool:
    try:
        return path.is_file()
    except OSError:
        return False


def _is_dir(path: Path) -> bool:
    try:
        return path.is_dir()
    except OSError:
        return False


def import_roots(p: Project) -> list[tuple[str, bool]]:
    """Directories the project's code is imported from: the project root and pyproject [tool.pytest.ini_options]
    pythonpath entries (explicit), the static prefixes of the configured source globs and top-level directories
    without __init__.py (inferred; review 3 R6: src/__init__.py with pythonpath = ["src"], nested source roots)."""
    roots: dict[str, bool] = {"": True}

    def explicit(entries) -> None:
        for entry in entries:
            if isinstance(entry, str):
                rel = posixpath.normpath(entry.replace("\\", "/")).strip("/")
                if rel and rel != "." and not rel.startswith(".."):
                    roots[rel] = True

    try:
        import tomllib
        data = tomllib.loads((p.root / "pyproject.toml").read_text(encoding="utf-8"))
        pp = data.get("tool", {}).get("pytest", {}).get("ini_options", {}).get("pythonpath", [])
        explicit([pp] if isinstance(pp, str) else pp if isinstance(pp, list) else [])
    except (OSError, ValueError, ImportError, AttributeError):
        pass
    # pytest's ini files (review 4 L1): pythonpath is a whitespace-separated list of paths
    import configparser
    for name, section in (("pytest.ini", "pytest"), ("tox.ini", "pytest"), ("setup.cfg", "tool:pytest")):
        try:
            cp = configparser.ConfigParser(interpolation=None)
            cp.read_string((p.root / name).read_text(encoding="utf-8"))
            if cp.has_option(section, "pythonpath"):
                explicit(cp.get(section, "pythonpath").split())
        except (OSError, ValueError, configparser.Error):
            pass
    for pat in p.config()["paths"]["source"]:
        parts = []
        for part in pat.replace("\\", "/").split("/"):
            if any(ch in part for ch in "*?[") or part.endswith(".py"):
                break
            parts.append(part)
        while parts and _is_file(p.root.joinpath(*parts) / "__init__.py"):
            parts.pop()  # a package directory: its parent is the root
        if parts:
            roots.setdefault("/".join(parts), False)
    try:
        tops = sorted(p.root.iterdir())
    except OSError:
        tops = []
    for d in tops:
        # an unreadable directory (e.g. a database volume of another user) is skipped, never a crash (review 4 M4)
        if _is_dir(d) and not d.name.startswith(".") and not _is_file(d / "__init__.py"):
            roots.setdefault(d.name, False)
    return sorted(roots.items())


def _interface_implemented(ctx: Ctx, trees: dict[str, ast.AST]) -> Check:
    probs, warns = [], []
    for iid, i in sorted(ctx.graph.ifaces.items()):
        sym = wiring.signature_symbol(i.get("signature"))
        mods = _component_modules(ctx, i.get("provider"))
        if not mods:
            probs.append(f"{iid}: provider {i.get('provider')} has no design unit module")
        elif not sym:
            warns.append(f"{iid}: the signature names no def/class; the G4 review's provider_symbols decide")
        elif not any(_defines(trees.get(m), sym) for m in mods):
            probs.append(f"{iid}: '{sym}' from the interface signature is not defined in {', '.join(mods)} "
                         f"(provider {i.get('provider')})")
    if probs:
        return Check("G4.INTERFACE_IMPLEMENTED", "mechanical", "fail", "interfaces not implemented by their provider",
                     probs + warns)
    if warns:
        return Check("G4.INTERFACE_IMPLEMENTED", "mechanical", "warn", "interface symbols to be confirmed by the review",
                     warns)
    return Check("G4.INTERFACE_IMPLEMENTED", "mechanical", "pass",
                 f"{len(ctx.graph.ifaces)} interface symbol(s) defined in their provider modules")


def declared_runtime_paths(review: dict | None) -> dict[tuple[str, str], dict]:
    out: dict[tuple[str, str], dict] = {}
    for e in _items(review, "interfaces"):
        for rp in _items(e, "runtime_paths"):
            if isinstance(e.get("id"), str) and isinstance(rp.get("test"), str):
                out[(e["id"], rp["test"])] = rp
    return out


def _runtime_declaration_problem(decl: dict | None, fv: dict, sha: str) -> str | None:
    """Is the verifier's runtime_paths entry valid for this test function (kind it uses, its file's current hash)?"""
    if decl is None:
        return "not declared"
    if decl.get("kind") not in fv.get("mechanisms", []):
        return (f"declared kind {decl.get('kind')!r} is not a mechanism the test uses "
                f"({', '.join(fv.get('mechanisms') or []) or 'none'})")
    if decl.get("test_file_sha256") != sha:
        return f"declared test_file_sha256 does not match the current {fv.get('file')} ({sha}); re-review"
    return None


def _integration_wiring(ctx: Ctx, wd: dict, review: dict | None, mhash: str) -> Check:
    """REQ-G6-11'/29/30 (D42): every function carrying an integration TEST id must reach each interface it verifies by
    a call path (A) or a runtime mechanism the verifier declared (B); judging only the best function would let an
    uncollected or disabled copy stand in for the test that really runs (review F1)."""
    p = ctx.project
    declared = declared_runtime_paths(review)
    fails, pend, warns = [], [], []
    shas: dict[str, str] = {}

    def sha(rel: str) -> str:
        if rel not in shas:
            shas[rel] = sha256_file(p.root / rel)
        return shas[rel]

    for tid, views in sorted(wd["tests"].items()):
        for v in views:
            if v["placeholder"]:
                fails.append(f"{tid}: placeholder test {v['function']} (no calls: it cannot verify an interface)")
    data: dict[str, dict] = {}
    for iid, iv in sorted(wd["interfaces"].items()):
        cons = "" if iv["consumer_modules"] is None else f" and consumer {', '.join(iv['consumer_modules'])}"
        data[iid] = {}
        if not iv["tests"]:
            fails.append(f"{iid}: no integration test spec verifies it")
        for tid, tv in sorted(iv["tests"].items()):
            if not tv["functions"]:
                continue  # no function: G4.TEST_CODE reports it
            best = tv["best"]
            fviews = []
            for fv in tv["functions"]:
                fsha = sha(fv["file"])
                path = fv["path"]
                if path == "static":
                    if fv["patched_provider"]:
                        warns.append(f"{tid} ({iid}): {fv['function']} patches the provider "
                                     f"({', '.join(fv['patched_provider'])}); the G4 review decides whether the "
                                     "interface is still exercised")
                elif path == "runtime_candidate":
                    why = _runtime_declaration_problem(declared.get((iid, tid)), fv, fsha)
                    if why is None:
                        path = "runtime_declared"
                    else:
                        pend.append(f"{tid} ({iid}): {fv['function']} has no static call path into the provider "
                                    f"{', '.join(iv['provider_modules'])}{cons}; runtime path "
                                    f"({', '.join(fv['mechanisms'])}) {why}: {REVIEWER} declares it in "
                                    f"reviews/G4.json interfaces[{iid}].runtime_paths as {{\"test\": \"{tid}\", "
                                    f"\"kind\": \"{fv['mechanisms'][0]}\", \"test_file_sha256\": \"{fsha}\"}} "
                                    f"({fv['file']}); G6 then needs runtime proof")
                elif path == "none":
                    fails.append(f"{tid} ({iid}): {fv['function']} neither calls into the provider "
                                 f"{', '.join(iv['provider_modules'])}{cons} nor uses a runtime integration mechanism "
                                 "(subprocess, IPC, API, dynamic import); reaches provider: "
                                 f"{'yes' if fv['reaches_provider'] else 'no'}, consumer: "
                                 f"{'yes' if fv['reaches_consumer'] else 'no'}")
                fviews.append({"function": fv["function"], "path": path, "test_file_sha256": fsha,
                               "reaches_provider": fv["reaches_provider"], "reaches_consumer": fv["reaches_consumer"],
                               "mechanisms": fv["mechanisms"], "patched_provider": fv["patched_provider"]})
            data[iid][tid] = {"path": tv["path"], "function": best["function"], "functions": fviews,
                              "test_file_sha256": sha(best["file"]), "reaches_provider": best["reaches_provider"],
                              "reaches_consumer": best["reaches_consumer"], "mechanisms": best["mechanisms"],
                              "patched_provider": best["patched_provider"]}
    out = {"interfaces": data}
    if fails:
        return Check("G4.INTEGRATION_WIRING", "mechanical", "fail",
                     "integration tests that cannot verify their interface (placeholder, or no call path)",
                     fails + pend + warns, data=out)
    if pend:
        return Check("G4.INTEGRATION_WIRING", "mechanical", "pending",
                     "runtime integration paths need the verifier's declaration (reviews/G4.json "
                     "interfaces[].runtime_paths)", pend + warns,
                     data={**out, "review_required_by": REVIEWER, "target_hash_expected": mhash})
    if warns:
        return Check("G4.INTEGRATION_WIRING", "mechanical", "warn",
                     "interfaces reached; provider patching to be judged by the G4 review", warns, data=out)
    return Check("G4.INTEGRATION_WIRING", "mechanical", "pass",
                 f"{len(wd['interfaces'])} interface(s): every integration test function reaches its provider by a "
                 "call path or a declared runtime path", data=out)


def _review_interfaces(ctx: Ctx, review: Check, rv: dict | None, trees: dict[str, ast.AST], mhash: str) -> Check:
    """REQ-G6-12: an approving G4 review of a work item with interfaces reviews every IF."""
    entries = {e["id"]: e for e in _items(rv, "interfaces") if isinstance(e.get("id"), str)}
    pend, issues = [], []
    for iid, i in sorted(ctx.graph.ifaces.items()):
        e = entries.get(iid)
        if e is None:
            pend.append(f"{iid}: not reviewed (add it to the review's 'interfaces')")
            continue
        if e.get("result") not in ("ok", "issue"):
            pend.append(f"{iid}: result must be 'ok' or 'issue'")
            continue
        syms = e.get("provider_symbols")
        mods = _component_modules(ctx, i.get("provider"))
        if not isinstance(syms, list) or not syms or not all(isinstance(x, str) and x.strip() for x in syms):
            pend.append(f"{iid}: provider_symbols must list the provider symbols implementing the interface")
        else:
            missing = [x for x in syms if not any(_defines(trees.get(m), x.strip()) for m in mods)]
            if missing:
                pend.append(f"{iid}: provider_symbols {missing} are not defined in the provider modules "
                            f"{', '.join(mods)}")
        if e.get("result") == "issue":
            issues.append(f"{iid}: {str(e.get('note') or 'interface issue')[:200]}")
    data = {**review.data, "interfaces_reviewed": sorted(k for k in entries if isinstance(k, str))}
    if issues:
        return Check("G4.REVIEW", "ai_review", "fail", "verifier reported interface issues", issues, data=data)
    if pend:
        return Check("G4.REVIEW", "ai_review", "pending",
                     f"the review must cover every interface ({', '.join(sorted(ctx.graph.ifaces))}) with result and "
                     "existing provider_symbols", pend, data={**data, "target_hash_expected": mhash})
    return Check("G4.REVIEW", "ai_review", "pass",
                 f"{review.detail}; {len(ctx.graph.ifaces)} interface(s) reviewed", data=data)


def _lint(ctx: Ctx, code_files: list[Path], mhash: str, evidence: list[dict]) -> Check:
    p = ctx.project
    cfg = p.config()["static_analysis"]
    lint = cfg.get("lint")
    reduced = cfg.get("on_missing_lint") == "syntax-only"
    if not lint:
        if reduced:
            return Check("G4.LINT", "execution", "pass",
                         "REDUCED SCOPE: no linter configured; user configured on_missing_lint=syntax-only "
                         "(only the built-in syntax check ran)", data={"reduced_scope": True})
        return Check("G4.LINT", "execution", "blocked",
                     "no static analyzer configured and on_missing_lint=block; configure one (e.g. ruff) "
                     "or let the user explicitly choose syntax-only", data={"blocked_reason": "tool_unavailable"})
    argv = _substitute(lint["argv"], {"{python}": p.python_exe(), "{files}": [p.rel(f) for f in code_files]})
    exe = runner.executable_info(argv[0])
    if exe["resolved"] is None:
        if reduced:
            return Check("G4.LINT", "execution", "pass",
                         f"REDUCED SCOPE: linter '{argv[0]}' not found; user configured on_missing_lint=syntax-only",
                         data={"reduced_scope": True})
        return Check("G4.LINT", "execution", "blocked", f"linter '{argv[0]}' not found on PATH",
                     data={"blocked_reason": "tool_unavailable"})
    argv[0] = exe["resolved"]
    with tempfile.TemporaryDirectory(prefix="vmodel-pyc-") as pyc:
        env, dropped = runner.scrubbed_env(Path(pyc))
        run = runner.run_command(argv, p.root, timeout_s=600, env=env)
    run_dir = runner.new_run_dir(p.evidence_dir, ctx.wi, "G4", "lint")
    ev = runner.write_evidence(p, ctx.ledger, run_dir, wi=ctx.wi, gate="G4", kind="static_analysis", run=run, exe=exe,
                               git=runner.git_info(p.root), manifest_hash=mhash, core_hash=ctx.integrity.core_hash,
                               extra={"tool": lint["name"], "environment": {"scrubbed": dropped}})
    evidence.append(ev)
    if run.error:
        return Check("G4.LINT", "execution", "blocked", f"{lint['name']} could not start: {run.error}",
                     data={"blocked_reason": "tool_unavailable", "evidence": ev["path"]})
    if run.exit_code != 0:
        tail = display_decode(run.stdout + run.stderr, limit=3000)
        lines = [ln for ln in tail.splitlines() if ln.strip()][-30:]
        return Check("G4.LINT", "execution", "fail", f"{lint['name']} exit code {run.exit_code}", lines,
                     data={"evidence": ev["path"]}, sig=[ln for ln in lines if " in " not in ln and "Found" not in ln])
    return Check("G4.LINT", "execution", "pass", f"{lint['name']} passed (exit 0)",
                 data={"evidence": ev["path"], "tool": lint["name"]})


# ---------------------------------------------------------------- G5
def _distributions(python: str) -> dict:
    """Installed distributions of the test interpreter (recorded, not used for staleness)."""
    code = ("import importlib.metadata as m, json; print(json.dumps(sorted({(d.metadata['Name'] or '?') + '==' + "
            "d.version for d in m.distributions()})))")
    try:
        res = __import__("subprocess").run([python, "-I", "-c", code], capture_output=True, timeout=60,
                                           stdin=__import__("subprocess").DEVNULL)
        items = json.loads(res.stdout.decode("utf-8", errors="replace") or "[]")
        return {"count": len(items), "sha256": hash_obj(items), "items": items[:400]}
    except Exception as exc:  # recording only; never fail the gate on this
        return {"error": f"{exc.__class__.__name__}: {exc}"}


def parse_junit(path: Path) -> dict:
    root = ET.parse(path).getroot()
    cases = []
    for tc in root.iter("testcase"):
        status, msg = "passed", ""
        for tag in ("failure", "error", "skipped"):
            el = tc.find(tag)
            if el is not None:
                status = {"failure": "failed", "error": "error", "skipped": "skipped"}[tag]
                msg = (el.get("message") or el.text or "")[:500]
                break
        cases.append({"classname": tc.get("classname", ""), "name": tc.get("name", ""), "status": status,
                      "message": msg})
    counts = Counter(c["status"] for c in cases)
    return {"tests": len(cases), "passed": counts["passed"], "failures": counts["failed"],
            "errors": counts["error"], "skipped": counts["skipped"], "cases": cases}


def eval_g5(ctx: Ctx, files: dict, mhash: str) -> tuple[list[Check], dict, list[dict]]:
    p = ctx.project
    g = ctx.graph
    checks = [Check("G5.PREREQ", "mechanical", "pass", "G4 PASSED for the current manifest hash")]
    evidence: list[dict] = []
    cfg = p.config()["unit_test"]
    if "{junit}" not in " ".join(cfg["argv"]):
        checks.append(Check("G5.EXECUTION", "execution", "blocked",
                            "unit_test.argv must contain {junit} so the validator can collect results",
                            data={"blocked_reason": "misconfigured"}))
        return checks, {}, evidence
    run_dir = runner.new_run_dir(p.evidence_dir, ctx.wi, "G5", "unit")
    junit = run_dir / "junit.xml"
    argv = _substitute(cfg["argv"], {"{python}": p.python_exe(), "{junit}": str(junit)})
    exe = runner.executable_info(argv[0])
    if exe["resolved"]:
        argv[0] = exe["resolved"]
    with tempfile.TemporaryDirectory(prefix="vmodel-pyc-") as pyc:
        env, dropped = runner.scrubbed_env(Path(pyc))
        if cfg.get("plugin_autoload"):
            env.pop("PYTEST_DISABLE_PLUGIN_AUTOLOAD", None)
        run = runner.run_command(argv, p.root, timeout_s=int(cfg["timeout_s"]), env=env)
    after = compute_manifest(p, ctx.wi, "G5")
    env_info = {"scrubbed": dropped, "set": {"PYTHONDONTWRITEBYTECODE": "1", "PYTHONPYCACHEPREFIX": "<validator temp>",
                                             "PYTEST_DISABLE_PLUGIN_AUTOLOAD": env.get("PYTEST_DISABLE_PLUGIN_AUTOLOAD")},
                "distributions": _distributions(argv[0])}
    junit_summary = None
    junit_error = None
    if junit.is_file():
        try:
            junit_summary = parse_junit(junit)
        except ET.ParseError as exc:
            junit_error = f"junit.xml unparseable: {exc}"
    else:
        junit_error = "junit.xml was not produced by the test run"
    ev = runner.write_evidence(
        p, ctx.ledger, run_dir, wi=ctx.wi, gate="G5", kind="unit_test", run=run, exe=exe,
        git=runner.git_info(p.root), manifest_hash=mhash, core_hash=ctx.integrity.core_hash,
        extra={"junit_summary": {k: v for k, v in (junit_summary or {}).items() if k != "cases"} or None,
               "junit_error": junit_error, "verified_files": files, "environment": env_info},
        extra_files={"junit.xml": junit})
    evidence.append(ev)
    tail = [ln for ln in display_decode(run.stdout + run.stderr, limit=4000).splitlines() if ln.strip()][-40:]

    if run.error:
        checks.append(Check("G5.EXECUTION", "execution", "blocked", f"test command could not start: {run.error}",
                            data={"blocked_reason": "tool_unavailable", "evidence": ev["path"]}))
        return checks, {}, evidence
    if run.timed_out:
        checks.append(Check("G5.EXECUTION", "execution", "fail", f"timed out after {cfg['timeout_s']}s", tail,
                            data={"evidence": ev["path"]}, sig=["timeout"]))
    elif run.exit_code != 0:
        checks.append(Check("G5.EXECUTION", "execution", "fail", f"test command exit code {run.exit_code}", tail,
                            data={"evidence": ev["path"], "exit_code": run.exit_code}, sig=[f"exit {run.exit_code}"]))
    elif junit_error:
        checks.append(Check("G5.EXECUTION", "execution", "fail", junit_error, data={"evidence": ev["path"]}))
    else:
        checks.append(Check("G5.EXECUTION", "execution", "pass", "exit code 0, junit produced",
                            data={"evidence": ev["path"], "exit_code": 0}))

    cases = (junit_summary or {}).get("cases", [])
    failed_cases = [f"{c['classname']}::{c['name']} [{c['status']}] {c['message'][:200]}"
                    for c in cases if c["status"] in ("failed", "error")]
    if junit_summary is None:
        checks.append(Check("G5.RESULTS", "execution", "fail", junit_error or "no results"))
    elif junit_summary["tests"] == 0:
        checks.append(Check("G5.RESULTS", "execution", "fail", "0 tests executed"))
    elif failed_cases:
        checks.append(Check("G5.RESULTS", "execution", "fail",
                            f"{junit_summary['failures']} failed, {junit_summary['errors']} error(s) of {junit_summary['tests']}",
                            failed_cases, sig=[f"{c['classname']}::{c['name']}" for c in cases
                                               if c["status"] in ("failed", "error")]))
    else:
        checks.append(Check("G5.RESULTS", "execution", "pass",
                            f"{junit_summary['passed']} passed, {junit_summary['skipped']} skipped of {junit_summary['tests']}"))

    executed: dict[str, str] = {}
    rank = {"passed": 0, "skipped": 1, "failed": 2, "error": 2}
    ambiguous = []
    for c in cases:
        ids = test_ids_in_text(c["name"])
        if len(ids) > 1:
            ambiguous.append(f"{c['classname']}::{c['name']} names more than one TEST id")
            continue
        for tid in ids:
            prev = executed.get(tid)
            if prev is None or rank[c["status"]] > rank[prev]:
                executed[tid] = c["status"]
    probs = list(ambiguous)
    for tid in g.unit_tests():
        st = executed.get(tid)
        if st is None:
            probs.append(f"{tid}: not executed")
        elif st != "passed":
            probs.append(f"{tid}: {st}")
    checks.append(Check("G5.TEST_MAPPING", "mechanical", "fail" if probs else "pass",
                        "unit test specs not verified by passing tests" if probs
                        else f"{len(g.unit_tests())} unit test spec(s) passed", probs))
    # 0.2.0 (REQ-G6-05/07): only a project that configured integration_test separates the levels in G5;
    # 0.3.0 (REQ-G7-06): likewise system tests once system_test is configured
    all_cfg = p.config()
    sep_int, sep_sys = "integration_test" in all_cfg, "system_test" in all_cfg
    separated = sep_int or sep_sys
    levels = project_test_levels(ctx) if separated else {}
    if separated:
        wrong = {**({"integration": "G6"} if sep_int else {}), **({"system": "G7"} if sep_sys else {})}
        checks.append(_scope_check("G5.SCOPE", executed, levels, wrong, command="unit_test"))

    passed_ids = {t for t, s in executed.items() if s == "passed"}
    probs = [rid for rid in g.active("functional") if not (set(g.tests_for_req(rid)) & passed_ids)]
    checks.append(Check("G5.REQ_COVERAGE", "mechanical", "fail" if probs else "pass",
                        "functional requirements without a passed test" if probs
                        else "every functional requirement has a passed test", probs))

    roots = test_roots(p)
    test_files = {k: v for k, v in files.items() if any(k.startswith(r) for r in roots if r)}
    checks.append(_no_weakening(ctx, test_files, executed,
                                skip={t for t, lvl in levels.items()
                                      if (lvl == "integration" and sep_int) or (lvl == "system" and sep_sys)}))

    changed = diff_manifest(files, after)
    checks.append(Check("G5.INPUTS_UNCHANGED", "mechanical", "fail" if changed else "pass",
                        "verified files changed during the test run" if changed else "inputs unchanged during the run",
                        changed))
    extra = {"test_files": test_files, "executed_tests": dict(sorted(executed.items())),
             "junit": {k: v for k, v in (junit_summary or {}).items() if k != "cases"}, "failed_cases": failed_cases[:50]}
    return checks, extra, evidence


def _no_weakening(ctx: Ctx, test_files: dict[str, str], executed: dict[str, str],
                  skip: set[str] | None = None) -> Check:
    # Baseline = last PASSED G5 run, or the very first G5 run if none passed yet. Using the latest run
    # instead would let a second attempt silently accept a test changed after a failure.
    runs = [e for e in gate_entries(ctx.entries, ctx.wi, "G5")
            if e.record.get("type") == "gate" and "test_files" in e.record]
    if not runs:
        return Check("G5.NO_WEAKENING", "mechanical", "pass", "first G5 run; baseline recorded")
    passed = [e for e in runs if e.record.get("status") == "PASSED"]
    prev = passed[-1] if passed else runs[0]
    old_files = prev.record.get("test_files") or {}
    changed = sorted(f for f in old_files if test_files.get(f) != old_files[f])
    justified: dict[str, dict] = {}
    for src in [*_defects(ctx), *_change_requests(ctx)]:
        for tc in _items(src, "test_changes"):
            if tc.get("since_record") == prev.id and isinstance(tc.get("file"), str):
                justified[tc["file"].replace("\\", "/")] = tc
    probs = []
    for f in changed:
        tc = justified.get(f)
        state = "removed" if f not in test_files else "changed"
        if tc is None:
            probs.append(f"{f} {state} since {prev.id} without a test_changes justification (since_record={prev.id})")
        elif not _str_list(tc.get("requirements")) or not set(_str_list(tc.get("requirements"))) <= set(ctx.graph.reqs) \
                or not all(isinstance(tc.get(k), str) and tc[k].strip() for k in ("reason", "impact")):
            probs.append(f"{f}: test_changes entry needs reason, impact and existing requirement ids")
    removed_ok: set[str] = set()
    for cr in _change_requests(ctx):
        if cr.get("status") != "rejected":
            removed_ok.update(_str_list(cr.get("removed_ids")))
    for d in _defects(ctx):
        removed_ok.update(_str_list(d.get("removed_ids")))
    old_exec = prev.record.get("executed_tests") or {}
    lost = sorted(t for t in old_exec if t not in executed and t not in removed_ok and t not in (skip or ()))
    probs += [f"{t} was executed in {prev.id} but not now" for t in lost]
    if probs:
        return Check("G5.NO_WEAKENING", "mechanical", "fail", "possible test weakening", probs)
    detail = f"{len(changed)} justified test file change(s) since {prev.id}" if changed else f"no test change since {prev.id}"
    return Check("G5.NO_WEAKENING", "mechanical", "pass", detail, changed)


def project_test_levels(ctx: Ctx) -> dict[str, str]:
    """TEST id -> level over every work item's tests.json (TEST ids are project-unique; this work item wins)."""
    levels: dict[str, str] = {}
    for w in ctx.project.work_items():
        if w == ctx.wi:
            continue
        data, _err = ctx.project.load_artifact(w, "tests.json")
        for t in _items(data, "tests"):
            if isinstance(t.get("id"), str) and isinstance(t.get("level"), str):
                levels.setdefault(t["id"], t["level"])
    for tid, t in ctx.graph.tests.items():
        if isinstance(t.get("level"), str):
            levels[tid] = t["level"]
    return levels


def _scope_check(cid: str, executed: dict[str, str], levels: dict[str, str], wrong: dict[str, str],
                 command: str, own: str | None = None) -> Check:
    """`wrong`: level -> the gate that owns it; those levels must not run under `command` (fail). A system-level id
    that is not in `wrong` (no system_test configured) only warns, unless the command is the system command itself
    (`own`). With one wrong level the wording is the 0.2.0 one (REQ-G7-07)."""
    bad = sorted(t for t in executed if levels.get(t) in wrong)
    warn_system = "system" not in wrong and own != "system"
    system = sorted(t for t in executed if levels.get(t) == "system") if warn_system else []
    sys_items = [f"{t}: system test executed by the {command} command (it belongs to G7, which runs the separate "
                 "system_test command; system_test is not configured)" for t in system]
    if bad:
        lv = [x for x in wrong if any(levels.get(t) == x for t in bad)]
        bad_items = [f"{t}: {levels[t]} test executed by the {command} command (it belongs to {wrong[levels[t]]})"
                     for t in bad]
        # the failure signature keeps the 0.2.0 wording of the system lines, so the 3-strike count of a project
        # without system_test is the same as before the upgrade (design review L5); the display says what is true now
        return Check(cid, "mechanical", "fail",
                     f"{' and '.join(lv)} tests executed by the {command} command (they belong to "
                     f"{', '.join(wrong[x] for x in lv)})", bad_items + sys_items,
                     sig=bad_items + [f"{t}: system test executed (G7, not implemented)" for t in system])
    if system:
        return Check(cid, "mechanical", "warn", "system tests executed (they belong to G7; system_test is not configured)",
                     sys_items)
    names = [*wrong, *(["system"] if warn_system else [])]
    return Check(cid, "mechanical", "pass", f"no {' or '.join(names)} test in this run")


# ---------------------------------------------------------------- G6 (0.2.0, docs/g6/G6-DESIGN.md, WORKITEM)
ARCH_ID = re.compile(r"^ARCH-\d{3,}$")


def removed_interfaces(ctx: Ctx) -> dict[str, list[str]]:
    """Interfaces of earlier G2 PASSes that are gone now -> the CRs (not rejected) / DEFECTs listing them in
    removed_ids (empty list: removed without justification)."""
    before: set[str] = set()
    for e in gate_entries(ctx.entries, ctx.wi, "G2"):
        if e.record.get("type") == "gate" and e.record.get("status") == "PASSED":
            before |= {k for k in (e.record.get("item_hashes") or {}) if k.startswith("IF-")}
    srcs: dict[str, list[str]] = {}
    for cr in _change_requests(ctx):
        if cr.get("status") != "rejected":
            for i in _str_list(cr.get("removed_ids")):
                srcs.setdefault(i, []).append(str(cr.get("id")))
    for d in _defects(ctx):
        for i in _str_list(d.get("removed_ids")):
            srcs.setdefault(i, []).append(str(d.get("id")))
    return {i: srcs.get(i, []) for i in sorted(before - set(ctx.graph.ifaces))}


def g6_applicability(ctx: Ctx) -> dict:
    """REQ-G6-14-16: required | not_applicable | unconfirmed, with the basis. Pure: reads artifacts, reviews, ledger."""
    g = ctx.graph
    arch = ctx.arts.get("architecture.json") if isinstance(ctx.arts.get("architecture.json"), dict) else {}
    its = arch.get("integration_test_strategy") if isinstance(arch.get("integration_test_strategy"), dict) else {}
    integ = g.integration_tests()
    basis: dict[str, Any] = {"interfaces": len(g.ifaces), "integration_specs": len(integ), "components": sorted(g.comps),
                             "approach": its.get("approach"), "na_reason": its.get("na_reason")}
    if g.ifaces or integ:
        return {"applicability": "required", "basis": basis, "problems": []}
    problems: list[str] = []
    ends: list[str] = []
    for f in _items(arch, "data_flows"):
        ends += [v for v in (f.get("from"), f.get("to")) if isinstance(v, str)]
    arch_ends = sorted({e for e in ends if ARCH_ID.match(e)})
    external = list(dict.fromkeys(e for e in ends if not ARCH_ID.match(e)))
    basis["external_endpoints"] = external
    if len(g.comps) != 1:
        problems.append(f"{len(g.comps)} components: N/A needs exactly one component")
    others = [a for a in arch_ends if a not in g.comps]
    if others:
        problems.append(f"data_flows connect to other components {others}: integration is not ruled out")
    for gate in ("G2", "G3"):
        lp = last_with_status(ctx.entries, ctx.wi, gate, "PASSED")
        if lp is None:
            problems.append(f"{gate}: no PASSED evaluation")
            continue
        basis[f"{gate.lower()}_record"] = lp.id
        rc = [c for c in lp.record.get("checks") or [] if isinstance(c, dict) and c.get("id") == f"{gate}.REVIEW"]
        accepted = (rc[0].get("data") or {}).get("review_sha256") if rc else None
        path = ctx.project.wi_root / ctx.wi / "reviews" / f"{gate}.json"
        if not path.is_file():
            problems.append(f"{gate}: reviews/{gate}.json is missing")
            continue
        current = sha256_file(path)
        basis[f"{gate.lower()}_review_sha256"] = current
        if accepted != current:
            problems.append(f"{gate}: reviews/{gate}.json is not the review accepted by {lp.id}; submit it "
                            f"('vmodel review-submit') and re-run {gate}")
            continue
        rv = load_review(ctx, gate) or {}
        ia = rv.get("integration_applicability")
        if not isinstance(ia, dict) or ia.get("decision") != "not_required":
            problems.append(f"{gate}: the review does not confirm integration_applicability.decision 'not_required'")
            continue
        reason = ia.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            problems.append(f"{gate}: integration_applicability.reason is empty")
            continue
        basis[f"{gate.lower()}_reason"] = reason.strip()
        reviewed = _str_list(ia.get("endpoints_reviewed"))
        basis[f"{gate.lower()}_endpoints_reviewed"] = reviewed
        missing = [e for e in external if e not in reviewed]
        if missing:
            problems.append(f"{gate}: external data flow endpoints not in integration_applicability.endpoints_reviewed: "
                            f"{missing}")
    removed = removed_interfaces(ctx)
    unjust = [i for i, src in removed.items() if not src]
    if unjust:
        problems.append(f"interfaces of earlier G2 PASSes removed without a CR/DEFECT listing them in removed_ids: "
                        f"{unjust}")
    basis["removed_interfaces"] = {i: src for i, src in removed.items() if src}
    return {"applicability": "unconfirmed" if problems else "not_applicable", "basis": basis, "problems": problems}


def integration_config_problems(cfg: Any) -> list[str]:
    """REQ-G6-01b: the integration_test object is checked on every evaluation (config is schema-checked at init only)."""
    if cfg is None:
        return ["integration_test is not configured in .vmodel/config.json"]
    errs = validate(cfg, load_schema("config")["properties"]["integration_test"])
    if errs:
        return [f"integration_test {e}" for e in errs[:10]]
    probs = []
    if isinstance(cfg["timeout_s"], bool) or cfg["timeout_s"] <= 0:
        probs.append("integration_test.timeout_s must be a positive integer")
    if "{junit}" not in " ".join(cfg["argv"]):
        probs.append("integration_test.argv must contain {junit} so the validator can collect results")
    return probs


TRACE_FILE_LIMIT = 32 * 1024 * 1024


def trace_files(trace_dir: Path) -> tuple[list[Path], list[str], int]:
    """Regular, non-symlink *.jsonl files up to the size limit; anything else planted in the folder is reported, not
    read or hashed (a directory, FIFO or device there must not crash or hang the validator, review F4). Also returns
    how many files were too large to read (they make the trace truncated, review 3 R8)."""
    files, errors, oversized = [], [], 0
    for f in sorted(trace_dir.glob("*.jsonl")) if trace_dir.is_dir() else []:
        try:
            if f.is_symlink() or not f.is_file():
                errors.append(f"{f.name}: not a regular file (ignored)")
            elif f.stat().st_size > TRACE_FILE_LIMIT:
                errors.append(f"{f.name}: larger than {TRACE_FILE_LIMIT} bytes (not read; trace counted as truncated)")
                oversized += 1
            else:
                files.append(f)
        except OSError as exc:
            errors.append(f"{f.name}: {exc.__class__.__name__}")
    return files, errors, oversized


TRACE_LINE_LIMIT = 64 * 1024


def _trace_json(line: str):
    """One tracer line, or None: planted lines (huge, deeply nested, not JSON) never raise (review N3)."""
    if len(line) > TRACE_LINE_LIMIT:
        return None
    try:
        return json.loads(line)
    except (ValueError, RecursionError, MemoryError):
        return None


def snapshot_trace(live: Path, snap: Path) -> tuple[list[str], int]:
    """Read each acceptable tracer file of the run's live folder once and write those bytes into `snap`: the copy the
    validator judges and hashes into the signed evidence. A process that outlives the test command (a leaked server)
    keeps writing to its live file, never to the signed copy (review 4 M5). Returns the live folder's problems and
    how many files were too large (they make the trace truncated)."""
    files, errors, oversized = trace_files(live)
    snap.mkdir(exist_ok=True)
    for f in files:
        try:
            with open(f, "rb") as fh:
                data = fh.read(TRACE_FILE_LIMIT + 1)
        except OSError as exc:
            errors.append(f"{f.name}: {exc.__class__.__name__}")
            continue
        if len(data) > TRACE_FILE_LIMIT:
            errors.append(f"{f.name}: larger than {TRACE_FILE_LIMIT} bytes (not read; trace counted as truncated)")
            oversized += 1
            continue
        (snap / f.name).write_bytes(data)
        try:
            f.unlink()  # best effort: a still-open file may not be removable (Windows); it is never read again
        except OSError:
            pass
    try:
        live.rmdir()
    except OSError:
        pass
    return errors, oversized


def _ts(v) -> float | None:
    return float(v) if type(v) in (int, float) else None


NOT_INTERFACE_METHODS = {"__init__", "__new__", "__post_init__", "__init_subclass__", "__set_name__", "__del__",
                         "__repr__", "__str__", "__format__", "__hash__", "__eq__", "__ne__", "__sizeof__",
                         "__reduce__", "__reduce_ex__", "__getstate__", "__setstate__", "__copy__", "__deepcopy__",
                         "__class_getitem__"}


def _patches_symbol(target: str, syms: set[str]) -> bool:
    """Whether a patch target (dotted module path + attribute path) is an interface symbol or one of its methods; with
    no known symbol every provider patch counts (conservative)."""
    parts = target.split(".")
    return not syms or any(_is_symbol_function(".".join(parts[-k:]), s)
                           for k in range(1, min(len(parts), 4) + 1) for s in syms)


def _is_symbol_function(func: str, sym: str) -> bool:
    """Whether a traced function (co_qualname) is the interface symbol `sym`: the function itself, a method of a class
    symbol (not its constructor or object protocol: review 5 N3), or, for a method-named signature, that method of any
    class in the provider file (review 5 N2)."""
    if func == sym:
        return True
    if func.startswith(sym + "."):
        return func[len(sym) + 1:].split(".", 1)[0] not in NOT_INTERFACE_METHODS
    return func.endswith("." + sym) and "<locals>" not in func


def _test_windows(boundaries: dict[str, list[tuple[float, str, str]]]) -> dict[str, list[dict]]:
    """test id -> its runs, each {setup, call, teardown, end} (wall clock), from the boundary lines the validator's
    pytest plugin writes in the pytest process(es). A run without an end ends at the next boundary of its file."""
    out: dict[str, list[dict]] = {}
    for seq in boundaries.values():
        open_runs: dict[str, dict] = {}
        runs: list[dict] = []
        for ts, t, ph in seq:  # file order is time order
            if ph == "setup" or t not in open_runs:
                run = {"test": t, "setup": None, "call": None, "teardown": None, "end": None, "last": ts}
                open_runs[t] = run
                runs.append(run)
                out.setdefault(t, []).append(run)
            run = open_runs[t]
            if ph in ("setup", "call", "teardown", "end") and run[ph] is None:
                run[ph] = ts
            run["last"] = ts
            if ph == "end":
                del open_runs[t]
        times = [ts for ts, _t, _p in seq]
        for run in runs:
            if run["end"] is None:  # never finished (crash, timeout, older format): until the next boundary
                run["end"] = next((x for x in times if x > run["last"]), float("inf"))
            if run["setup"] is None:
                run["setup"] = run["call"] if run["call"] is not None else run["last"]
    return out


def _phase_in(runs: list[dict], ts: float) -> str:
    """The phase of `ts` inside one of the test's runs; a time on a boundary is never credited (review 5 N8: equal
    clock ticks): on the call start -> setup, on the teardown start -> teardown, on the setup start or end -> detached."""
    for r in runs:
        lo, hi = r["setup"], r["end"]
        if not lo < ts < hi:
            continue
        call, td = r["call"], r["teardown"]
        call_end = td if td is not None else hi
        if call is not None and call < ts < call_end:
            return "call"
        if td is not None and ts >= td:
            return "teardown"
        return "setup"
    return "detached"


def _provider_defs(ix, rel: str, component: set | frozenset = frozenset()) -> dict:
    """D48: the names a provider module defines, for the tracer's run-time patch check. "strict": a plain def or a
    class that is the name's last module-level binding (anything else bound there is a replacement); "weak": decorated
    or rebound names (only a mock, test-tree code or code from a string counts as a replacement)."""
    m = ix.modules.get(rel)
    strict, weak = [], []
    if m is None:
        return {"strict": strict, "weak": weak, "imported": []}
    # names a function rebinds through `global` (lazy initialisation) are rebound by the provider itself (review 23)
    rebound = {n for node in ast.walk(m.tree) if isinstance(node, ast.Global) for n in node.names}
    for name, node in m.functions.items():
        decos = {d.id if isinstance(d, ast.Name) else d.attr if isinstance(d, ast.Attribute) else ""
                 for d in getattr(node, "decorator_list", [])}
        if "." in name:
            (strict if decos <= {"staticmethod", "classmethod"} else weak).append(name)
        else:
            b = m.bindings.get(name)
            (strict if not decos and b and b[0] == "def" and b[1] is node and name not in rebound else weak).append(name)
    for name in m.classes:
        b = m.bindings.get(name)
        (strict if b and b[0] == "class" and name not in rebound else weak).append(name)
    # names imported from outside the provider component are its dependencies: replacing one (stubbing an external
    # service or another component) stays a G4 warning (D44 item 2 / review 8 P1); names the module binds itself and
    # names imported from the same component's modules are checked for a test-tree replacement. An absolute import is
    # kept as ("dotted", name) in the bindings, so it is resolved first (review 28).
    def outside(tgt) -> bool:
        t = ix.normal(tgt) if isinstance(tgt, tuple) and tgt else None
        return not (isinstance(t, tuple) and len(t) > 1 and t[0] == "src" and t[1] in component)

    imported = sorted(n for n, b in m.bindings.items() if b and b[0] == "import" and outside(b[1]))
    return {"strict": sorted(strict), "weak": sorted(weak), "imported": imported}


def read_runtime_trace(trace_dir: Path, prior_errors: list[str] | None = None, prior_oversized: int = 0) -> dict:
    """The tracer files (written inside the processes under test, hashed into the signed evidence). In memory:
    `_events` (pytest node id, phase, process file, watched file, function), `_edges` (node id, phase, process file,
    provider file, provider entry function, consumer file or None, anchors, started function, anchors of the stacks
    that started the process (D45)), `_ran` (watched file, function) run
    anywhere. A process started during a test
    keeps that test id for its whole life, so its lines are re-read against the pytest process's test boundaries:
    after the test ended -> "detached", during its call -> "call" (review 4 H3/M1). `truncated`: some process hit the
    record limit, so the absence of a record is not evidence that something did not run."""
    files, errors, oversized = trace_files(trace_dir)
    errors = [*(prior_errors or []), *errors]
    oversized += prior_oversized
    procs, methods, truncated = oversized, set(), oversized > 0
    tests: dict[str, set[str]] = {}
    ran_files: set[str] = set()  # watched files with a function run anywhere in the run, any test or none
    ran: set[tuple[str, str]] = set()
    raw_events: list[tuple] = []
    raw_edges: list[tuple] = []
    boundaries: dict[str, list[tuple[float, str, str]]] = {}
    capped: set[str] = set()
    spawn_lines: dict[str, tuple[tuple[str, ...], str]] = {}  # D45: token -> (anchors of the starting stack, file)
    raw_cons: list[tuple] = []  # consumer runs with their stack anchors (review 12 H2)
    raw_patched: list[tuple] = []  # D48: provider names replaced at run time
    raw_starts: list[tuple] = []  # D48: threads, pool work items and processes started during a test, with anchors
    file_origin: dict[str, str] = {}  # process file -> the spawn token it was started with (subprocess.Popen)
    spawned_files = 0
    windows_complete = oversized == 0  # a lost or truncated pytest-process file may have lost test boundaries
    for f in files:
        try:
            lines = f.read_bytes().decode("utf-8", "replace").splitlines()
        except OSError as exc:
            errors.append(f"{f.name}: {exc.__class__.__name__}")
            windows_complete = False
            continue
        head = _trace_json(lines[0]) if lines else None
        if not isinstance(head, dict):
            errors.append(f"{f.name}: no header")
            windows_complete = False
            continue
        procs += 1
        methods.add(str(head.get("method")))
        spawned = isinstance(head.get("spawned_in"), list)
        spawned_files += spawned
        if isinstance(head.get("origin"), str):
            file_origin[f.name] = head["origin"]
        for ln in lines[1:]:
            r = _trace_json(ln)
            if not isinstance(r, dict):
                errors.append(f"{f.name}: unreadable line")
                continue
            t, ts = r.get("t"), (_ts(r.get("ts")), r.get("tc") if type(r.get("tc")) is int else None)
            if r.get("truncated") is True:
                truncated = True
                windows_complete = windows_complete and spawned
            elif isinstance(r.get("b"), str):
                if not spawned and ts[0] is not None:
                    boundaries.setdefault(f.name, []).append((ts, r["b"], str(r.get("p") or "")))
            elif r.get("edge_scan_capped") is True:
                if isinstance(t, str):
                    capped.add(t)
            elif isinstance(r.get("spawn"), str):
                a = r.get("a")
                sa = tuple(sorted(x for x in a if isinstance(x, str))) if isinstance(a, list) else ()
                spawn_lines.setdefault(r["spawn"], (sa, f.name))
                if isinstance(t, str) and sa:
                    raw_starts.append((t, str(r.get("p") or ""), f.name, "process", sa, ts, spawned))
            elif isinstance(r.get("fs"), str):  # D48: a thread or pool work item started during a test
                a = r.get("a")
                sa = tuple(sorted(x for x in a if isinstance(x, str))) if isinstance(a, list) else ()
                if isinstance(t, str) and sa:
                    raw_starts.append((t, str(r.get("p") or ""), f.name, r["fs"], sa, ts, spawned))
            elif isinstance(r.get("x"), str):  # D48: provider-defined names replaced when a provider function started
                n = r.get("n")
                names = tuple(sorted(x for x in n if isinstance(x, str))) if isinstance(n, list) else ()
                if isinstance(t, str) and names:
                    raw_patched.append((t, str(r.get("p") or ""), f.name, r["x"], names, ts, spawned))
            elif isinstance(r.get("origin"), str):  # a multiprocessing child names its start (overrides the header)
                file_origin[f.name] = r["origin"]
            elif isinstance(r.get("k"), str):  # a consumer ran, with the anchors of its stack (review 12 H2)
                a = r.get("a")
                if isinstance(t, str):
                    raw_cons.append((t, str(r.get("p") or ""), f.name, r["k"],
                                     tuple(sorted(x for x in a if isinstance(x, str))) if isinstance(a, list) else (),
                                     ts, spawned, r.get("mt") == 1))
            elif isinstance(r.get("e"), str):  # a provider function ran (c absent) or a consumer called it (c)
                c, anchor = r.get("c"), r.get("a")
                anchors = (anchor,) if isinstance(anchor, str) else tuple(
                    sorted(x for x in anchor if isinstance(x, str))) if isinstance(anchor, list) else ()
                if isinstance(t, str) and (c is None or isinstance(c, str)):
                    start = r.get("s") if isinstance(r.get("s"), str) else str(r.get("f") or "")
                    raw_edges.append((t, str(r.get("p") or ""), f.name, r["e"], str(r.get("f") or ""), c, anchors, start,
                                      ts, spawned, r.get("mt") == 1))
            elif isinstance(r.get("m"), str):
                ran_files.add(r["m"])
                ran.add((r["m"], str(r.get("f"))))
                if isinstance(t, str):
                    tests.setdefault(t, set()).add(r["m"])
                    raw_events.append((t, str(r.get("p") or ""), f.name, r["m"], str(r.get("f")), ts, spawned))
    # review 6 M5/M6: compare on the monotonic high-resolution counter when every boundary carries it (a coarse wall
    # clock would put child lines on boundary ticks, never credited); otherwise on the wall clock
    use_tc = bool(boundaries) and all(ts[1] is not None for seq in boundaries.values() for ts, _t, _p in seq)
    key = 1 if use_tc else 0
    windows = _test_windows({f: [(ts[key], t, ph) for ts, t, ph in seq] for f, seq in boundaries.items()})
    if spawned_files and (spawned_files == procs - oversized or not boundaries):
        windows_complete = False  # no pytest-process boundaries (plugin not loaded, not pytest): not attributable
    moved: dict[str, int] = {}

    def phase_of(t: str, ph: str, tsc: tuple, spawned: bool) -> str:
        """A line of a process started during a test is re-read against that test's runs (review 4 H3, review 5 N1):
        its inherited phase says only when the process started."""
        if not spawned:
            return ph
        ts = tsc[key]
        new = _phase_in(windows.get(t) or [], ts) if windows_complete and ts is not None else "detached"
        if new != ph:
            moved[new] = moved.get(new, 0) + 1
        return new

    def origin_of(fname: str) -> tuple[str, ...]:
        """D45: the anchors of the stacks that started this process (its spawn line, then the starting process's own
        origin, and so on); () when it was not started through subprocess.Popen in a traced process."""
        out, seen = set(), set()
        while fname in file_origin and fname not in seen:
            seen.add(fname)
            line = spawn_lines.get(file_origin[fname])
            if line is None:
                break
            out.update(line[0])
            fname = line[1]
        return tuple(sorted(out))

    origins = {fn: origin_of(fn) for fn in file_origin}
    events = [(t, phase_of(t, ph, ts, sp), fn, m, func) for t, ph, fn, m, func, ts, sp in raw_events]
    edges = [(t, phase_of(t, ph, ts, sp), fn, e, func, c, a, st, origins.get(fn, ()), mt)
             for t, ph, fn, e, func, c, a, st, ts, sp, mt in raw_edges]
    cons = [(t, phase_of(t, ph, ts, sp), fn, lab, tuple(sorted(set(a) | set(origins.get(fn, ())))), mt)
            for t, ph, fn, lab, a, ts, sp, mt in raw_cons]
    patched = [(t, phase_of(t, ph, ts, sp), fn, lab, names) for t, ph, fn, lab, names, ts, sp in raw_patched]
    starts = [(t, phase_of(t, ph, ts, sp), fn, kind, tuple(sorted(set(a) | set(origins.get(fn, ())))))
              for t, ph, fn, kind, a, ts, sp in raw_starts]
    return {"active": procs > 0, "processes": procs, "spawned_processes": spawned_files, "methods": sorted(methods),
            "truncated": truncated, "ran_files": sorted(ran_files),
            "tests": {t: sorted(v) for t, v in sorted(tests.items())}, "edges": len(edges),
            "edge_scan_capped": sorted(capped)[:20], "test_boundaries": sum(len(v) for v in boundaries.values()),
            "boundary_clock": "perf_counter_ns" if use_tc else "wall",
            "spawned_lines_reattributed": moved, "errors": errors[:20], "_events": events, "_edges": edges,
            "_cons": cons, "_capped": sorted(capped), "_patched": patched, "_starts": starts, "_ran": ran}


def test_function_of(nodeid: str) -> str:
    """The test function name of a pytest node id: after the file part, before parameters (which may contain '::');
    a '[' in the file path is not a parameter (review 4 M3)."""
    i = nodeid.find(".py::")
    rest = nodeid[i + 5:] if i >= 0 else nodeid
    return rest.split("[", 1)[0].split("::")[-1]


def trace_by_test(rt: dict) -> dict[str, dict]:
    """TEST id -> what ran during the pytest tests named with exactly that id: `functions` (file::qualname, any
    phase) with the processes they ran in, `ran` ((file, function) in any phase of the test's own execution), `call`
    ((file, function) -> processes, call phase), `edges` ((provider file, entry function, consumer file, anchors)),
    `prov_runs` ((provider file, entry function, anchors)) and `prov_calls` ((provider file, entry function, started
    function) -> {(process, anchors on its stack plus the anchors of the stacks that started its process)}, call phase,
    D45). The tracer attributes another thread to the test that started it and a pool work item to the test that
    submitted it."""
    out: dict[str, dict] = {}

    def entry(nodeid: str) -> dict | None:
        ids = test_ids_in_text(test_function_of(nodeid))
        if len(ids) != 1:
            return None
        return out.setdefault(next(iter(ids)), {"functions": {}, "call": {}, "ran": set(), "edges": set(),
                                                "prov_runs": set(), "prov_calls": {}, "cons_calls": set(),
                                                "mt": {"edges": set(), "prov_runs": set(), "prov_calls": {},
                                                       "cons_calls": set()},
                                                "rpatched": set(), "starts": set()})

    for nodeid, phase, proc, label, func in rt.get("_events") or []:
        d = entry(nodeid)
        if d is None:
            continue
        d["functions"].setdefault(f"{label}::{func}", set()).add(proc)
        if phase != "detached":  # a thread or process of this test still running after the test: not attributable
            d["ran"].add((label, func))
        if phase == "call":
            d["call"].setdefault((label, func), set()).add(proc)
    for nodeid, phase, proc, provider, func, consumer, anchors, start, origin, mt in rt.get("_edges") or []:
        d = entry(nodeid)
        if d is None or phase == "detached":
            continue
        for view in ((d, d["mt"]) if mt else (d,)):  # D48: "mt" keeps what ran in the test's main thread only
            if consumer is None:
                view["prov_runs"].add((provider, func, anchors, start))
                if phase == "call":
                    view["prov_calls"].setdefault((provider, func, start), set()).add(
                        (proc, tuple(sorted(set(anchors) | set(origin)))))
            else:
                view["edges"].add((provider, func, consumer, anchors))
    for nodeid, phase, proc, label, anchors, mt in rt.get("_cons") or []:
        d = entry(nodeid)
        if d is not None and phase == "call":
            for view in ((d, d["mt"]) if mt else (d,)):
                view["cons_calls"].add((proc, label, anchors))
    for nodeid, phase, proc, label, names in rt.get("_patched") or []:
        d = entry(nodeid)
        if d is not None and phase in ("setup", "call"):
            d["rpatched"].add((label, names))
    for nodeid, phase, proc, kind, anchors in rt.get("_starts") or []:
        d = entry(nodeid)
        if d is not None and phase in ("setup", "call"):
            d["starts"].add((kind, anchors))
    return out


EVIDENCE_LABELS = {"test_level": "Test-level Verified", "suite_level": "Suite-level Evidence Only",
                   "insufficient": "Insufficient Evidence"}
EVIDENCE_RANK = {"test_level": 2, "suite_level": 1, "insufficient": 0}


def _g6_no_weakening(ctx: Ctx, executed: dict[str, str]) -> Check:
    """REQ-G6-23: baseline = last required PASSED G6, else the first G6 run that executed anything."""
    runs = [e for e in gate_entries(ctx.entries, ctx.wi, "G6")
            if e.record.get("type") == "gate" and e.record.get("executed_tests")]
    passed = [e for e in runs if e.record.get("status") == "PASSED" and e.record.get("applicability") == "required"]
    base = passed[-1] if passed else (runs[0] if runs else None)
    removed_ok: set[str] = set()
    for cr in _change_requests(ctx):
        if cr.get("status") != "rejected":
            removed_ok.update(_str_list(cr.get("removed_ids")))
    for d in _defects(ctx):
        removed_ok.update(_str_list(d.get("removed_ids")))
    probs = []
    if base is not None:
        old = base.record.get("executed_tests") or {}
        specs = _str_list(base.record.get("integration_specs"))
        probs += [f"{t} was executed in {base.id} but not now" for t in specs
                  if t in old and t not in executed and t not in removed_ok]
    probs += [f"{i} passed G2 earlier but is no longer in architecture.json and no CR/DEFECT lists it in removed_ids"
              for i, src in removed_interfaces(ctx).items() if not src]
    if probs:
        return Check("G6.NO_WEAKENING", "mechanical", "fail", "possible integration test weakening", probs)
    return Check("G6.NO_WEAKENING", "mechanical", "pass",
                 f"no integration test or interface lost since {base.id}" if base else "first G6 run; baseline recorded")


def _inputs_unchanged(ctx: Ctx, gate: str, files: dict) -> Check:
    changed = diff_manifest(files, compute_manifest(ctx.project, ctx.wi, gate))
    return Check(f"{gate}.INPUTS_UNCHANGED", "mechanical", "fail" if changed else "pass",
                 "verified files changed during the evaluation" if changed else "inputs unchanged during the run",
                 changed)


G6_RUN_CHECKS = (("G6.CONFIG", "mechanical"), ("G6.EXECUTION", "execution"), ("G6.RESULTS", "execution"),
                 ("G6.SCOPE", "mechanical"), ("G6.TEST_MAPPING", "mechanical"), ("G6.IF_COVERAGE", "mechanical"))


def eval_g6(ctx: Ctx, files: dict, mhash: str) -> tuple[list[Check], dict, list[dict]]:
    p = ctx.project
    g = ctx.graph
    checks = [Check("G6.PREREQ", "mechanical", "pass", "G5 PASSED for the current manifest hash")]
    evidence: list[dict] = []
    app = g6_applicability(ctx)
    extra: dict[str, Any] = {"applicability": app["applicability"], "applicability_basis": app["basis"],
                             "executed_tests": {}, "interfaces": []}
    if app["applicability"] == "unconfirmed":
        checks.append(Check("G6.APPLICABILITY", "mechanical", "blocked",
                            "no interface and no integration test spec, but N/A is not confirmed (REQ-G6-15)",
                            app["problems"], data={"blocked_reason": "applicability_unconfirmed",
                                                   "applicability": "unconfirmed", "basis": app["basis"]}))
        return checks, extra, evidence
    if app["applicability"] == "not_applicable":
        b = app["basis"]
        checks.append(Check("G6.APPLICABILITY", "mechanical", "pass",
                            f"N/A: one component ({', '.join(b['components'])}), no interface, no integration test "
                            f"spec; confirmed by the G2 ({b.get('g2_record')}) and G3 ({b.get('g3_record')}) reviews",
                            data={"applicability": "not_applicable", "basis": b}))
        checks += [Check(cid, kind, "skip", "not executed: not applicable (no integration test was run)")
                   for cid, kind in G6_RUN_CHECKS]
        checks.append(_g6_no_weakening(ctx, {}))
        checks.append(_inputs_unchanged(ctx, "G6", files))
        return checks, extra, evidence
    checks.append(Check("G6.APPLICABILITY", "mechanical", "pass",
                        f"required: {len(g.ifaces)} interface(s), {len(g.integration_tests())} integration test spec(s)",
                        data={"applicability": "required", "basis": app["basis"]}))
    all_cfg = p.config()
    cfg = all_cfg.get("integration_test")
    cfg_data = {"config_sha256": sha256_file(p.config_path),
                "integration_test_sha256": hash_obj(cfg) if cfg is not None else None,
                "unit_test_sha256": hash_obj(all_cfg.get("unit_test"))}
    probs = integration_config_problems(cfg)
    if probs:
        checks.append(Check("G6.CONFIG", "mechanical", "blocked",
                            "integration_test is not usable: the user must add or fix it in .vmodel/config.json (the "
                            "agent cannot edit it; the unit_test command is never used instead)", probs,
                            data={"blocked_reason": "misconfigured", **cfg_data}))
        return checks, extra, evidence
    checks.append(Check("G6.CONFIG", "mechanical", "pass", "integration_test configured",
                        data={"argv": cfg["argv"], **cfg_data}))

    # static analysis of the verified files, before running anything
    wd, ix = g6_wiring(ctx)
    g4_pass = last_with_status(ctx.entries, ctx.wi, "G4", "PASSED")
    rc = [c for c in (g4_pass.record.get("checks") if g4_pass else None) or []
          if isinstance(c, dict) and c.get("id") == "G4.REVIEW"]
    accepted_sha = (rc[0].get("data") or {}).get("review_sha256") if rc else None
    rv_path = p.wi_root / ctx.wi / "reviews" / "G4.json"
    review_note = None
    review = None
    if rv_path.is_file() and sha256_file(rv_path) == accepted_sha:
        review = load_review(ctx, "G4")
    elif g.ifaces:
        review_note = (f"reviews/G4.json is not the review accepted by {g4_pass.id if g4_pass else 'a G4 PASS'}: "
                       "re-run G4")
    declared = declared_runtime_paths(review)
    units = list(g.units.values())
    watch_rels = {u["module"].replace("\\", "/") for u in units if isinstance(u.get("module"), str)}
    watch_rels &= {p.rel(f) for f in p.source_files()}
    test_labels = {v["file"] for views in wd["tests"].values() for v in views}
    # conftest.py files under the test roots: their fixtures can be anchors (review 5 N7: never counted unless the test
    # requested them, but they must be seen so an autouse fixture is not mistaken for the test body)
    test_labels |= {p.rel(f) for f in p.test_files() if f.name == "conftest.py"}
    watch_rels |= test_labels

    run_dir = runner.new_run_dir(p.evidence_dir, ctx.wi, "G6", "integration")
    junit = run_dir / "junit.xml"
    trace_dir = run_dir / "trace"  # the signed snapshot the validator judges (review 4 M5)
    live_dir = run_dir / "trace-live"  # where the processes under test write
    live_dir.mkdir()
    spec_path = run_dir / "trace-spec.json"
    prov_map: dict[str, set[str]] = {}  # D44: provider file -> consumer files whose call into it is recorded
    for iv in wd["interfaces"].values():
        for prov in iv["provider_modules"]:
            if prov in watch_rels:
                prov_map.setdefault(prov, set()).update(c for c in iv["consumer_modules"] or []
                                                        if c in watch_rels and c != prov)
    comp_of: dict[str, set[str]] = {}  # provider module -> the modules of its provider component(s)
    for iv in wd["interfaces"].values():
        for prov in iv["provider_modules"]:
            comp_of.setdefault(prov, set()).update(iv["provider_modules"])
    test_tree = {str(f.resolve()) for f in p.test_files()}
    test_tree |= {str(f.resolve()) for f in p.root.glob("conftest.py") if f.is_file()}
    write_json(spec_path, {"out": str(live_dir), "watch": {str((p.root / r).resolve()): r for r in sorted(watch_rels)},
                           "providers": {k: sorted(v) for k, v in sorted(prov_map.items())},
                           "tests": sorted(test_labels & watch_rels),
                           "provider_defs": {k: _provider_defs(ix, k, comp_of.get(k, frozenset())) for k in sorted(prov_map)},
                           "test_files": sorted(test_tree)})
    argv = _substitute(cfg["argv"], {"{python}": p.python_exe(), "{junit}": str(junit)})
    exe = runner.executable_info(argv[0])
    if exe["resolved"]:
        argv[0] = exe["resolved"]
    with tempfile.TemporaryDirectory(prefix="vmodel-pyc-") as pyc:
        env, dropped = runner.scrubbed_env(Path(pyc))
        if cfg.get("plugin_autoload"):
            env.pop("PYTEST_DISABLE_PLUGIN_AUTOLOAD", None)
        env["PYTHONPATH"] = str(TRACER_DIR)  # validator-owned: the agent's PYTHONPATH was dropped above
        env["VMODEL_TRACE_SPEC"] = str(spec_path)
        env["PYTEST_PLUGINS"] = "vmodel_trace_plugin"  # exact test phase boundaries (review 5); the agent's was dropped
        run = runner.run_command(argv, p.root, timeout_s=int(cfg["timeout_s"]), env=env)
    live_errors, live_oversized = snapshot_trace(live_dir, trace_dir)
    rt = read_runtime_trace(trace_dir, live_errors, live_oversized)
    env_info = {"scrubbed": dropped, "set": {"PYTHONDONTWRITEBYTECODE": "1", "PYTHONPYCACHEPREFIX": "<validator temp>",
                                             "PYTEST_DISABLE_PLUGIN_AUTOLOAD": env.get("PYTEST_DISABLE_PLUGIN_AUTOLOAD"),
                                             "PYTEST_PLUGINS": "vmodel_trace_plugin",
                                             "PYTHONPATH": "<validator tracer>", "VMODEL_TRACE_SPEC": "trace-spec.json"},
                "distributions": _distributions(argv[0])}
    junit_summary, junit_error = None, None
    if junit.is_file():
        try:
            junit_summary = parse_junit(junit)
        except ET.ParseError as exc:
            junit_error = f"junit.xml unparseable: {exc}"
    else:
        junit_error = "junit.xml was not produced by the test run"
    traced_files = {f"trace/{f.name}": f for f in trace_files(trace_dir)[0]}
    ev = runner.write_evidence(
        p, ctx.ledger, run_dir, wi=ctx.wi, gate="G6", kind="integration_test", run=run, exe=exe,
        git=runner.git_info(p.root), manifest_hash=mhash, core_hash=ctx.integrity.core_hash,
        extra={"command_source": "integration_test", **cfg_data,
               "junit_summary": {k: v for k, v in (junit_summary or {}).items() if k != "cases"} or None,
               "junit_error": junit_error, "verified_files": files, "environment": env_info,
               "runtime_trace": {k: v for k, v in rt.items() if k != "tests" and not k.startswith("_")}
               | {"tests_traced": len(rt["tests"])}},
        extra_files={"junit.xml": junit, "trace-spec.json": spec_path, **traced_files})
    evidence.append(ev)
    tail = [ln for ln in display_decode(run.stdout + run.stderr, limit=4000).splitlines() if ln.strip()][-40:]

    if run.error:
        checks.append(Check("G6.EXECUTION", "execution", "blocked", f"test command could not start: {run.error}",
                            data={"blocked_reason": "tool_unavailable", "evidence": ev["path"]}))
        return checks, {**extra, "runtime_trace": {k: v for k, v in rt.items() if not k.startswith("_")}}, evidence
    if run.timed_out:
        checks.append(Check("G6.EXECUTION", "execution", "fail", f"timed out after {cfg['timeout_s']}s", tail,
                            data={"evidence": ev["path"]}, sig=["timeout"]))
    elif run.exit_code != 0:
        checks.append(Check("G6.EXECUTION", "execution", "fail", f"test command exit code {run.exit_code}", tail,
                            data={"evidence": ev["path"], "exit_code": run.exit_code}, sig=[f"exit {run.exit_code}"]))
    elif junit_error:
        checks.append(Check("G6.EXECUTION", "execution", "fail", junit_error, data={"evidence": ev["path"]}))
    else:
        checks.append(Check("G6.EXECUTION", "execution", "pass", "exit code 0, junit produced",
                            data={"evidence": ev["path"], "exit_code": 0}))
    cases = (junit_summary or {}).get("cases", [])
    failed_cases = [f"{c['classname']}::{c['name']} [{c['status']}] {c['message'][:200]}"
                    for c in cases if c["status"] in ("failed", "error")]
    if junit_summary is None:
        checks.append(Check("G6.RESULTS", "execution", "fail", junit_error or "no results"))
    elif junit_summary["tests"] == 0:
        checks.append(Check("G6.RESULTS", "execution", "fail", "0 tests executed"))
    elif failed_cases:
        checks.append(Check("G6.RESULTS", "execution", "fail",
                            f"{junit_summary['failures']} failed, {junit_summary['errors']} error(s) of {junit_summary['tests']}",
                            failed_cases, sig=[f"{c['classname']}::{c['name']}" for c in cases
                                               if c["status"] in ("failed", "error")]))
    else:
        checks.append(Check("G6.RESULTS", "execution", "pass",
                            f"{junit_summary['passed']} passed, {junit_summary['skipped']} skipped of {junit_summary['tests']}"))

    executed: dict[str, str] = {}
    rank = {"passed": 0, "skipped": 1, "failed": 2, "error": 2}
    ambiguous, unmapped = [], []
    levels = project_test_levels(ctx)
    for c in cases:
        ids = test_ids_in_text(c["name"])
        if len(ids) > 1:
            ambiguous.append(f"{c['classname']}::{c['name']} names more than one TEST id")
            continue
        if not ids or not ids <= set(levels):
            unmapped.append(f"{c['classname']}::{c['name']}")
        for tid in ids:
            prev = executed.get(tid)
            if prev is None or rank[c["status"]] > rank[prev]:
                executed[tid] = c["status"]
    checks.append(_scope_check("G6.SCOPE", executed, levels,
                               {"unit": "G5", **({"system": "G7"} if "system_test" in all_cfg else {})},
                               command="integration_test"))
    if unmapped:
        checks[-1].data["unmapped_cases"] = unmapped[:50]
    probs = list(ambiguous)
    for tid in g.integration_tests():
        st = executed.get(tid)
        if st is None:
            probs.append(f"{tid}: not executed")
        elif st != "passed":
            probs.append(f"{tid}: {st}")
    checks.append(Check("G6.TEST_MAPPING", "mechanical", "fail" if probs else "pass",
                        "integration test specs not verified by passing tests" if probs
                        else f"{len(g.integration_tests())} integration test spec(s) passed", probs))

    ran = trace_by_test(rt)
    fails, blocks, warns = [], [], []
    if_view = []
    levels_data: dict[str, dict] = {}
    ran_all: set[tuple[str, str]] = set(rt.get("_ran") or set())
    ran_entries = {(e, fn, st) for _t, _ph, _f, e, fn, c, _a, st, _o, _mt in rt.get("_edges") or [] if c is None}
    # TEST ids of the capped pytest node ids (review 13: the node ids were compared with TEST ids, so the "not certain"
    # note never showed)
    capped = {i for n in rt.get("_capped") or rt.get("edge_scan_capped") or []
              for i in test_ids_in_text(test_function_of(n))}
    if not rt["active"]:  # the validator injected its tracer: no trace at all is missing evidence (review N4)
        blocks.append("no runtime trace was written although the validator injected its tracer (Python started with "
                      "-I/-E/-S, PYTHONPATH replaced, or the trace removed): which test functions ran and whether the "
                      "providers ran cannot be shown")
    empty = {"functions": {}, "call": {}, "ran": set(), "edges": set(), "prov_runs": set(), "prov_calls": {},
             "cons_calls": set(), "mt": {"edges": set(), "prov_runs": set(), "prov_calls": {}, "cons_calls": set()},
             "rpatched": set(), "starts": set()}
    for iid, iv in sorted(wd["interfaces"].items()):
        prov_rels = set(iv["provider_modules"])
        # review 4 H4: the provider is the interface's own symbols (the signature's def/class and the accepted G4
        # review's provider_symbols, with their methods and nested functions), not any function of the provider file
        syms = {wiring.signature_symbol((g.ifaces.get(iid) or {}).get("signature"))} - {None}
        for e in (review or {}).get("interfaces") or [] if isinstance((review or {}).get("interfaces"), list) else []:
            if isinstance(e, dict) and e.get("id") == iid and isinstance(e.get("provider_symbols"), list):
                syms |= {x for x in e["provider_symbols"] if isinstance(x, str) and x}

        def is_prov(label: str, func: str, _p=prov_rels, _s=frozenset(syms)) -> bool:
            return label in _p and (not _s or any(_is_symbol_function(func, x) for x in _s))

        sym_text = f" ({', '.join(sorted(syms))})" if syms else " (any function: the provider symbol is unknown)"
        # review 9 Q1: what a patch can replace in the provider: its symbols and every def/class/method of its modules
        prov_defined = {n for rel in prov_rels if rel in ix.modules
                        for n in (*ix.modules[rel].functions, *ix.modules[rel].classes)}
        cons_rels = set(iv["consumer_modules"] or [])  # empty: EXTERNAL consumers only
        # D44: with an architecture consumer the connection is a consumer function on the provider's call stack (or on
        # the stack that started its thread / submitted its pool work item); a provider file that is also a consumer
        # file cannot show one, so there the provider running in the test is the most that can be observed
        needs_edge = bool(cons_rels) and not (prov_rels & cons_rels)
        # E2E-A (589c779): when the provider file is also a consumer file the entry (outermost function of that file)
        # is the consumer's own function, so there the function that started is what can be observed
        same_file = bool(prov_rels & cons_rels)

        def pfn(entry_fn: str, start_fn: str, _sf=same_file) -> str:
            return start_fn if _sf else entry_fn

        prov_anywhere = any(is_prov(e, pfn(fn, st)) for e, fn, st in ran_entries) if ran_entries else \
            any(is_prov(lab, fn) for lab, fn in ran_all)
        covered_by, tests_view = [], {}
        credited: list[str] = []  # passed tests with a call path whose function ran: their level decides
        not_counted: list[tuple[str, str, str]] = []  # (test, level, reason)
        for tid, tv in sorted(iv["tests"].items()):
            st = executed.get(tid, "not executed")
            seen = ran.get(tid, empty)
            call_files = seen["call"]
            prov_here = any(is_prov(e, pfn(fn, st)) for e, fn, _a, st in seen["prov_runs"]) or \
                any(is_prov(lab, fn) for lab, fn in seen["ran"] if not seen["prov_runs"])
            cons_here = (not cons_rels) or any(lab in cons_rels for lab, _fn in seen["ran"])
            # review 5 N7: only what the test itself ran counts: the anchor (outermost test-file function on the stack)
            # must be the test function or a fixture / setUp it requested, never an autouse or unrequested fixture
            own_fns = {fv["name"] for fv in tv["functions"]}
            anchors = {a for fv in tv["functions"] for a in (fv.get("anchors") or [fv["name"]])}
            # D48 (policy B): a thread, pool work item or process that code the test did not request (an autouse or
            # unrequested fixture) started in this test may be what drove the connection (a request over a socket,
            # work handed to a server): then only what ran in the test's own main thread counts
            foreign_starts = sorted({f"{k} started by {'/'.join(a)}" for k, a in seen["starts"] if not set(a) & anchors})
            if foreign_starts:
                seen = {**seen, **seen["mt"]}
            # review 8 P1 / review 9 Q1: a patch of an interface symbol or of any def/class/method defined in a
            # provider module is a mock of the provider; a constant or an imported name there (a limit, a clock) is not
            # (G4 still warns about every provider patch)
            patch_targets = sorted({t for fv in tv["functions"] for t in fv.get("patched_provider") or []
                                    if isinstance(t, str) and (_patches_symbol(t, syms) or any(
                                        ".".join(t.split(".")[-k:]) in prov_defined for k in (1, 2)))})
            # D48 (policy A at run time): provider-defined names found replaced when the provider ran in this test
            # (a patch from any fixture, plugin, MonkeyPatch.context or the child's own code)
            patch_targets += [f"{n} (replaced at run time)" for n in sorted(
                {n for lab, names in seen["rpatched"] if lab in prov_rels for n in names})]
            patched = bool(patch_targets)
            if needs_edge:
                linked = [a for e, fn, c, a in seen["edges"] if is_prov(e, fn) and c in cons_rels]
            else:
                linked = [a for e, fn, a, st in seen["prov_runs"] if is_prov(e, pfn(fn, st))] if cons_here else []
            # review 6 M5 (decision): a connection run only by a requested fixture does not count when the test
            # function itself patches the provider; the test body's own run always counts
            direct = any(set(a) & own_fns for a in linked)
            via_fixture = any(set(a) & (anchors - own_fns) for a in linked)
            # review 7 R4 (decision, Case B): a test function that patches the provider (G4's static detection) is not
            # test-level evidence, even when part of the real provider also ran in it
            connected = (direct or via_fixture) and not patched
            foreign = sorted({x for a in linked for x in a} - anchors)
            not_own = None if connected or not linked else (
                f"ran from its consumer in this test, but the test patches the provider ({', '.join(patch_targets)}): "
                "a test that replaces part of the provider does not verify the real connection by itself"
                if (direct or via_fixture) else
                f"ran {'from its consumer ' if needs_edge else ''}in this test only from code the test did not request "
                f"({', '.join(foreign) or '?'}: an autouse or unrequested fixture), not from the test function or a "
                "fixture it requested")
            cons_call = (not cons_rels) or any(lab in cons_rels for lab, _fn in call_files)
            pick, fviews = None, []  # (level, reason, path, function view) of the best credited function
            for fv in tv["functions"]:
                procs = seen["functions"].get(f"{fv['file']}::{fv['name']}")
                r = {"function": fv["function"], "path": fv["path"], "executed": procs is not None}
                fviews.append(r)
                if procs is None:
                    continue
                if fv["path"] == "static":
                    # path A: the static call path of a function that ran, and in this test's own execution the
                    # consumer called the provider (EXTERNAL consumer: the provider ran in it)
                    cand = ("test_level", None) if connected else \
                        ("insufficient" if patched and (direct or via_fixture) else "suite_level",
                         f"the provider{sym_text} {not_own}") if not_own else \
                        ("insufficient", f"the provider{sym_text} ran in this test but was not called from the consumer (no "
                                         "consumer function on its call stack, the stack that started its thread or "
                                         "submitted its pool work item): running both is not a connection")\
                        if prov_here and cons_here and needs_edge else \
                        ("insufficient", "the consumer did not run in this test") if prov_here and not cons_here else \
                        ("suite_level", f"the provider{sym_text} ran in this run, but not in this test's own execution (mocked "
                                        "here? run by another test, a session/module fixture, or a thread this test "
                                        "did not start)") if prov_anywhere else \
                        ("insufficient", f"the provider{sym_text} never ran in this integration run (mocked everywhere, or a "
                                         "data-only interface)")
                    if cand[0] != "test_level" and tid in capped:
                        cand = (cand[0], cand[1] + "; the call-stack scan limit was reached, so this is not certain")
                elif fv["path"] == "runtime_candidate":
                    why = review_note or _runtime_declaration_problem(declared.get((iid, tid)), fv,
                                                                       sha256_file(p.root / fv["file"]))
                    if why is not None:
                        r["path"] = "runtime_undeclared"
                        (blocks if review_note else fails).append(
                            f"{tid} ({iid}): {review_note}" if review_note else
                            f"{tid} ({iid}): {fv['function']} has no static call path and no valid runtime path in "
                            f"the G4 review accepted by {g4_pass.id if g4_pass else '?'} ({why})")
                        continue
                    r["path"] = "runtime"
                    kind = (declared.get((iid, tid)) or {}).get("kind")
                    # entries of the provider during the call (review 6 M1) with the anchors of the stack they ran on
                    # plus those of the stacks that started their process (D45)
                    other = kind in ("subprocess", "ipc")  # proof must come from another process (review F6)
                    runs = [(k[0], a) for k, v in seen["prov_calls"].items() if is_prov(k[0], pfn(k[1], k[2]))
                            for proc, a in v if not other or proc not in procs]
                    # D45 policy B: only what the test function or a fixture it requested ran or started counts, never
                    # what an autouse / unrequested fixture started (thread, server, process) or an unlinked process
                    p_ok = any(set(a) & anchors for _e, a in runs)
                    # review 12 H2: and the consumer evidence must be the test's own consumer run as well
                    cons_own = (not cons_rels) or any(lab in cons_rels and set(a) & anchors
                                                      for _proc, lab, a in seen["cons_calls"]) or \
                        any(e in cons_rels and set(a) & anchors for e, a in runs)  # review 13 SF1 / 14 SF2: a provider
                    # run of the test itself in a module that is also a consumer module is the consumer's run too
                    where = " in a process other than the test's" if other else ""
                    started_by = sorted({x for _e, a in runs for x in a} - anchors)
                    cand = ("insufficient", f"runtime path ({kind}) declared at G4 and the provider ran{where} during the "
                                            f"test call, but the test patches the provider ({', '.join(patch_targets)}): "
                                            "a test that replaces part of the provider does not verify the real "
                                            "connection by itself") if runs and patched else \
                        ("test_level", None) if p_ok and cons_own else \
                        ("insufficient", f"runtime path ({kind}) declared at G4 and the provider ran{where} during the "
                                         "test call, but no consumer function ran in it" + (
                                             " from the test function or a fixture it requested (only from an "
                                             "autouse or unrequested fixture)" if cons_call else "")) if p_ok else \
                        ("suite_level", f"runtime path ({kind}) declared at G4 and the provider{sym_text} ran{where} "
                                        "during the test call, but only in a thread or process the test function or a "
                                        "fixture it requested did not start ("
                                        f"{', '.join(started_by) or 'not linked to any test function'}: an autouse or "
                                        "unrequested fixture, or a process not started through subprocess.Popen)") \
                        if runs else \
                        ("suite_level", f"runtime path ({kind}) declared at G4, but no provider function{sym_text} ran{where} "
                                        "during this test's call; it ran elsewhere in the run") if prov_anywhere else \
                        ("insufficient", f"runtime path ({kind}) declared at G4, but no provider function{sym_text} ran{where} "
                                         "during this test's call or anywhere in the run (the child not traced: "
                                         "-I/-E/-S, replaced PYTHONPATH or environment?)")
                    if cand[0] != "test_level" and tid in capped:  # review 13 C5
                        cand = (cand[0], cand[1] + "; the call-stack scan limit was reached, so this is not certain")
                else:
                    fails.append(f"{tid} ({iid}): {fv['function']} has no call path into the interface "
                                 f"({fv['path']})")
                    continue
                if pick is None or EVIDENCE_RANK[cand[0]] > EVIDENCE_RANK[pick[0]]:
                    pick = (cand[0], cand[1], r["path"], fv)
            if st == "passed" and tv["functions"] and not any(x["executed"] for x in fviews) and rt["active"]:
                msg = (f"{tid} ({iid}): passed, but none of the analysed functions carrying {tid} ran "
                       f"({', '.join(x['function'] for x in fviews)})")
                if rt["truncated"]:
                    blocks.append(msg + "; the runtime trace was truncated, so this is not certain")
                else:
                    fails.append(msg + ": the passing case is another function")
            level, reason, path_used = pick[:3] if pick else ("insufficient", None, None)
            if foreign_starts and level != "test_level" and reason:
                reason += (f"; code the test did not request started work in it ({', '.join(foreign_starts[:3])}), so "
                           "only the test's own main-thread evidence was counted")
            if not rt["active"]:
                level, reason = "insufficient", "no runtime trace"
            elif st != "passed":
                level, reason = "insufficient", f"the test {st}"
            elif pick is None:
                reason = "no analysed function of this test with a call path ran"
            else:
                credited.append(tid)
                if level == "test_level":
                    covered_by.append(tid)
                else:
                    if rt["truncated"]:
                        reason += "; the runtime trace was truncated"
                    not_counted.append((tid, level, reason))
            best = (pick[3] if pick else None) or tv["best"] or {}
            tests_view[tid] = {"status": st, "path": path_used or (fviews[0]["path"] if len(fviews) == 1 else tv["path"]),
                               "function": best.get("function"), "functions": fviews,
                               "evidence_level": level, "evidence_reason": reason,
                               "reaches_provider": best.get("reaches_provider", False),
                               "reaches_consumer": best.get("reaches_consumer", False),
                               "patched_provider": best.get("patched_provider", []),
                               "runtime": {"traced": bool(seen["functions"]), "provider_ran": prov_here,
                                           "consumer_ran": cons_here, "consumer_called_provider": connected
                                           if needs_edge else None}}
        covered = bool(covered_by)
        verification = "test_level" if covered else max(
            (lv for t, lv, _r in not_counted), key=EVIDENCE_RANK.get, default="insufficient")
        if covered:
            warns.extend(f"{t} ({iid}): {EVIDENCE_LABELS[lv]}, not counted ({why}); {iid} is test-level verified by "
                         f"{', '.join(covered_by)}" for t, lv, why in not_counted)
        elif credited:
            blocks.extend(f"{t} ({iid}): {EVIDENCE_LABELS[lv]}: {why}" for t, lv, why in not_counted)
            blocks.append(f"{iid}: {EVIDENCE_LABELS[verification]}: no passed integration test shows the connection "
                          "in its own execution, so the interface is not verified at test level")
        elif rt["active"] and not any(b.startswith(tuple(f"{t} ({iid})" for t in iv["tests"])) for b in blocks):
            fails.append(f"{iid}: not covered by a passed integration test that reaches its provider "
                         f"({', '.join(iv['provider_modules']) or 'no module'})")
        levels_data[iid] = {"verification": verification, "covered_by": covered_by,
                            "tests": {t: v["evidence_level"] for t, v in tests_view.items()}}
        if_view.append({"id": iid, "provider": iv["provider"], "consumers": iv["consumers"],
                        "provider_modules": iv["provider_modules"], "consumer_modules": iv["consumer_modules"],
                        "covered": covered, "covered_by": covered_by, "verification": verification,
                        "provider_symbols": sorted(syms),
                        "tests": tests_view})
    n_cov = sum(1 for v in if_view if v["covered"])
    head = f"{n_cov}/{len(if_view)} interface(s) test-level verified"
    data = {"levels": levels_data}
    if fails:
        checks.append(Check("G6.IF_COVERAGE", "mechanical", "fail", f"interfaces not verified ({head})",
                            fails + blocks + warns, data=data))
    elif blocks:
        checks.append(Check("G6.IF_COVERAGE", "mechanical", "blocked",
                            f"{head}; insufficient runtime evidence for the rest (REQ-G6-32/33, D44)", blocks + warns,
                            data={"blocked_reason": "integration_evidence_insufficient", **data}))
    elif warns:
        checks.append(Check("G6.IF_COVERAGE", "mechanical", "warn", f"{head}; some tests not counted", warns, data=data))
    else:
        checks.append(Check("G6.IF_COVERAGE", "mechanical", "pass",
                            f"{head} (passed integration tests whose own execution shows the connection)", data=data))
    checks.append(_g6_no_weakening(ctx, executed))
    checks.append(_inputs_unchanged(ctx, "G6", files))
    roots = test_roots(p)
    g5_pass = last_with_status(ctx.entries, ctx.wi, "G5", "PASSED")
    extra.update({
        "test_files": {k: v for k, v in files.items() if any(k.startswith(r) for r in roots if r)},
        "executed_tests": dict(sorted(executed.items())),
        "executed_levels": {t: levels.get(t) for t in sorted(executed)},
        "unmapped_cases": unmapped[:50],
        "integration_specs": g.integration_tests(),
        "integration_test_functions": {t: [v["function"] for v in vs] for t, vs in sorted(wd["tests"].items())},
        "interfaces": if_view,
        "basis_records": {"G4": g4_pass.id if g4_pass else None, "G5": g5_pass.id if g5_pass else None},
        "runtime_trace": {k: v for k, v in rt.items() if not k.startswith("_")},
        "junit": {k: v for k, v in (junit_summary or {}).items() if k != "cases"},
        "failed_cases": failed_cases[:50],
    })
    return checks, extra, evidence


# ---------------------------------------------------------------- G7 (0.3.0, docs/g7/G7-DESIGN.md)
def system_config_problems(cfg: Any) -> list[str]:
    """REQ-G7-01: the system_test object is checked on every evaluation (config is schema-checked at init only)."""
    if cfg is None:
        return ["system_test is not configured in .vmodel/config.json"]
    errs = validate(cfg, load_schema("config")["properties"]["system_test"])
    if errs:
        return [f"system_test {e}" for e in errs[:10]]
    probs = []
    if isinstance(cfg["timeout_s"], bool) or cfg["timeout_s"] <= 0:
        probs.append("system_test.timeout_s must be a positive integer")
    if "{junit}" not in " ".join(cfg["argv"]):
        probs.append("system_test.argv must contain {junit} so the validator can collect results")
    return probs


def system_specs(ctx: Ctx) -> list[str]:
    return sorted(tid for tid, t in ctx.graph.tests.items() if t.get("level") == "system")


def system_tests_without_function(ctx: Ctx) -> list[str]:
    """Display only (status / next action, design review M2): system TEST specs with no test function named with that
    one id in the project's test files (the G4.TEST_CODE scan; G4 itself does not judge system tests)."""
    present: set[str] = set()
    p = ctx.project
    for f in p.test_files():
        try:
            tree = ast.parse(f.read_bytes(), filename=p.rel(f))
        except (SyntaxError, ValueError, OSError, RecursionError, MemoryError):
            continue
        for fn in _test_functions(tree):
            ids = test_ids_in_text(fn)
            if len(ids) == 1:
                present |= ids
    return [t for t in system_specs(ctx) if t not in present]


def _read_junit(junit: Path) -> tuple[dict | None, str | None]:
    if not junit.is_file():
        return None, "junit.xml was not produced by the test run"
    try:
        return parse_junit(junit), None
    except ET.ParseError as exc:
        return None, f"junit.xml unparseable: {exc}"


def _suite_checks(gate: str, run: runner.RunResult, timeout_s: Any, junit_summary: dict | None,
                  junit_error: str | None, ev_path: str) -> list[Check]:
    """EXECUTION and RESULTS with the G5/G6 rules (G5 and G6 keep their own unchanged copies). A command that cannot
    start is the only BLOCKED (tool_unavailable); every other execution problem is a FAILED; exit 0 is not enough."""
    tail = [ln for ln in display_decode(run.stdout + run.stderr, limit=4000).splitlines() if ln.strip()][-40:]
    if run.error:
        return [Check(f"{gate}.EXECUTION", "execution", "blocked", f"test command could not start: {run.error}",
                      data={"blocked_reason": "tool_unavailable", "evidence": ev_path})]
    if run.timed_out:
        out = [Check(f"{gate}.EXECUTION", "execution", "fail", f"timed out after {timeout_s}s", tail,
                     data={"evidence": ev_path}, sig=["timeout"])]
    elif run.exit_code != 0:
        out = [Check(f"{gate}.EXECUTION", "execution", "fail", f"test command exit code {run.exit_code}", tail,
                     data={"evidence": ev_path, "exit_code": run.exit_code}, sig=[f"exit {run.exit_code}"])]
    elif junit_error:
        out = [Check(f"{gate}.EXECUTION", "execution", "fail", junit_error, data={"evidence": ev_path})]
    else:
        out = [Check(f"{gate}.EXECUTION", "execution", "pass", "exit code 0, junit produced",
                     data={"evidence": ev_path, "exit_code": 0})]
    cases = (junit_summary or {}).get("cases", [])
    failed = [c for c in cases if c["status"] in ("failed", "error")]
    if junit_summary is None:
        out.append(Check(f"{gate}.RESULTS", "execution", "fail", junit_error or "no results"))
    elif junit_summary["tests"] == 0:
        out.append(Check(f"{gate}.RESULTS", "execution", "fail", "0 tests executed"))
    elif failed:
        out.append(Check(f"{gate}.RESULTS", "execution", "fail",
                         f"{junit_summary['failures']} failed, {junit_summary['errors']} error(s) of "
                         f"{junit_summary['tests']}",
                         [f"{c['classname']}::{c['name']} [{c['status']}] {c['message'][:200]}" for c in failed],
                         sig=[f"{c['classname']}::{c['name']}" for c in failed]))
    else:
        out.append(Check(f"{gate}.RESULTS", "execution", "pass",
                         f"{junit_summary['passed']} passed, {junit_summary['skipped']} skipped of "
                         f"{junit_summary['tests']}"))
    return out


def _map_cases(cases: list[dict], levels: dict[str, str]) -> tuple[dict[str, str], list[str], list[str]]:
    """JUnit cases -> TEST id -> worst status (G5/G6 rule: a name must carry exactly one id), ambiguous and
    unmapped case names."""
    executed: dict[str, str] = {}
    rank = {"passed": 0, "skipped": 1, "failed": 2, "error": 2}
    ambiguous, unmapped = [], []
    for c in cases:
        ids = test_ids_in_text(c["name"])
        if len(ids) > 1:
            ambiguous.append(f"{c['classname']}::{c['name']} names more than one TEST id")
            continue
        if not ids or not ids <= set(levels):
            unmapped.append(f"{c['classname']}::{c['name']}")
        for tid in ids:
            prev = executed.get(tid)
            if prev is None or rank[c["status"]] > rank[prev]:
                executed[tid] = c["status"]
    return executed, ambiguous, unmapped


def _ac_coverage(ctx: Ctx, specs: list[str], executed: dict[str, str]) -> tuple[dict, Check]:
    """REQ-G7-09/10: every acceptance criterion of every active functional requirement is verified when every system
    spec naming it passed in this run (and there is at least one). Non-functional / constraint criteria without a
    system spec warn (G3 does not require one); with a spec they are judged like the functional ones."""
    g = ctx.graph
    by_ac: dict[str, list[str]] = {}
    for tid in specs:
        for ac in _str_list(g.tests[tid].get("acceptance_criteria")):
            by_ac.setdefault(ac, []).append(tid)
    coverage: dict[str, dict] = {}
    fails: list[str] = []
    warns: list[str] = []
    total = verified_n = 0
    for rid in sorted(g.reqs):
        r = g.reqs[rid]
        if r.get("status") != "active":
            continue
        rtype = r.get("type")
        functional = rtype == "functional"
        acs = [a for a in r.get("acceptance_criteria") or [] if isinstance(a, dict) and isinstance(a.get("id"), str)]
        ac_ids = {a["id"] for a in acs}
        cats: dict[str, list[str]] = {}
        for tid in specs:
            t = g.tests[tid]
            if rid in _str_list(t.get("verifies")) or ac_ids & set(_str_list(t.get("acceptance_criteria"))):
                cats.setdefault(str(t.get("category")), []).append(tid)
        entry: dict[str, Any] = {"type": rtype, "priority": r.get("priority"), "acceptance_criteria": {},
                                 "categories": cats}
        if functional and not acs:
            fails.append(f"{rid}: active functional requirement without an acceptance criterion")
        for a in acs:
            tests = {t: executed.get(t, "not executed") for t in by_ac.get(a["id"], [])}
            ok = bool(tests) and all(s == "passed" for s in tests.values())
            entry["acceptance_criteria"][a["id"]] = {"tests": tests, "verified": ok}
            total += 1
            verified_n += ok
            if ok:
                continue
            label = f"{a['id']} ({rid})" if functional else f"{a['id']} ({rid}, {rtype})"
            if not tests and not functional:
                warns.append(f"{label}: no system test spec; not verified by an executed system test (G3 does not "
                             "require one for non-functional/constraint requirements)")
            elif not tests:
                fails.append(f"{label}: no system test spec")
            else:
                fails.append(f"{label}: " + ", ".join(f"{t} {s}" for t, s in sorted(tests.items()) if s != "passed"))
        coverage[rid] = entry
    head = f"{verified_n}/{total} acceptance criteria verified by system tests that passed in this run"
    if fails:
        return coverage, Check("G7.AC_COVERAGE", "mechanical", "fail", f"acceptance criteria not verified ({head})",
                               fails + warns)
    if warns:
        return coverage, Check("G7.AC_COVERAGE", "mechanical", "warn",
                               f"{head}; some non-functional criteria have no system test", warns)
    return coverage, Check("G7.AC_COVERAGE", "mechanical", "pass", head)


def _g7_no_weakening(ctx: Ctx, executed: dict[str, str]) -> Check:
    """REQ-G7-12: baseline = last PASSED G7, else the first G7 run that executed anything."""
    runs = [e for e in gate_entries(ctx.entries, ctx.wi, "G7")
            if e.record.get("type") == "gate" and e.record.get("executed_tests")]
    passed = [e for e in runs if e.record.get("status") == "PASSED"]
    base = passed[-1] if passed else (runs[0] if runs else None)
    if base is None:
        return Check("G7.NO_WEAKENING", "mechanical", "pass", "first G7 run; baseline recorded")
    removed_ok: set[str] = set()
    for cr in _change_requests(ctx):
        if cr.get("status") != "rejected":
            removed_ok.update(_str_list(cr.get("removed_ids")))
    for d in _defects(ctx):
        removed_ok.update(_str_list(d.get("removed_ids")))
    old = base.record.get("executed_tests") or {}
    lost = [t for t in _str_list(base.record.get("system_specs"))
            if t in old and t not in executed and t not in removed_ok]
    if lost:
        return Check("G7.NO_WEAKENING", "mechanical", "fail", "possible system test weakening",
                     [f"{t} was executed in {base.id} but not now" for t in lost])
    return Check("G7.NO_WEAKENING", "mechanical", "pass", f"no system test lost since {base.id}")


def eval_g7(ctx: Ctx, files: dict, mhash: str) -> tuple[list[Check], dict, list[dict]]:
    """System verification (black box): run the configured system_test command and judge the acceptance criteria of
    the requirements from this run's own results only. No runtime tracer: missing internal call evidence is never a
    reason to block (REQ-G7-03)."""
    p = ctx.project
    checks = [Check("G7.PREREQ", "mechanical", "pass", "G6 PASSED (or N/A) for the current manifest hash")]
    evidence: list[dict] = []
    specs = system_specs(ctx)
    extra: dict[str, Any] = {"system_specs": specs, "executed_tests": {}}
    all_cfg = p.config()
    cfg = all_cfg.get("system_test")
    cfg_data = {"config_sha256": sha256_file(p.config_path),
                "system_test_sha256": hash_obj(cfg) if cfg is not None else None,
                "unit_test_sha256": hash_obj(all_cfg.get("unit_test")),
                "integration_test_sha256": hash_obj(all_cfg["integration_test"]) if "integration_test" in all_cfg
                else None}
    probs = system_config_problems(cfg)
    if probs:
        checks.append(Check("G7.CONFIG", "mechanical", "blocked",
                            "system_test is not usable: the user must add or fix it in .vmodel/config.json ('vmodel "
                            "configure-tests --system <path>' in a terminal; the agent cannot edit it). The unit_test "
                            "and integration_test commands are never used instead", probs,
                            data={"blocked_reason": "misconfigured", **cfg_data}))
        return checks, extra, evidence
    checks.append(Check("G7.CONFIG", "mechanical", "pass", "system_test configured",
                        data={"argv": cfg["argv"], **cfg_data}))
    run_dir = runner.new_run_dir(p.evidence_dir, ctx.wi, "G7", "system")
    junit = run_dir / "junit.xml"
    argv = _substitute(cfg["argv"], {"{python}": p.python_exe(), "{junit}": str(junit)})
    exe = runner.executable_info(argv[0])
    if exe["resolved"]:
        argv[0] = exe["resolved"]
    with tempfile.TemporaryDirectory(prefix="vmodel-pyc-") as pyc:
        env, dropped = runner.scrubbed_env(Path(pyc))
        if cfg.get("plugin_autoload"):
            env.pop("PYTEST_DISABLE_PLUGIN_AUTOLOAD", None)
        # files, not pipes: a server a system test left running must not hang or time out the run (review M1)
        run = runner.run_command_files(argv, p.root, timeout_s=int(cfg["timeout_s"]), env=env)
    env_info = {"scrubbed": dropped, "set": {"PYTHONDONTWRITEBYTECODE": "1", "PYTHONPYCACHEPREFIX": "<validator temp>",
                                             "PYTEST_DISABLE_PLUGIN_AUTOLOAD": env.get("PYTEST_DISABLE_PLUGIN_AUTOLOAD")},
                "output_capture": "files; POSIX: own session, process group killed after the run",
                "distributions": _distributions(argv[0])}
    junit_summary, junit_error = _read_junit(junit)
    ev = runner.write_evidence(
        p, ctx.ledger, run_dir, wi=ctx.wi, gate="G7", kind="system_test", run=run, exe=exe,
        git=runner.git_info(p.root), manifest_hash=mhash, core_hash=ctx.integrity.core_hash,
        extra={"command_source": "system_test", **cfg_data,
               "junit_summary": {k: v for k, v in (junit_summary or {}).items() if k != "cases"} or None,
               "junit_error": junit_error, "verified_files": files, "environment": env_info},
        extra_files={"junit.xml": junit})
    evidence.append(ev)
    checks += _suite_checks("G7", run, cfg["timeout_s"], junit_summary, junit_error, ev["path"])
    if run.error:
        return checks, extra, evidence
    cases = (junit_summary or {}).get("cases", [])
    levels = project_test_levels(ctx)
    executed, ambiguous, unmapped = _map_cases(cases, levels)
    checks.append(_scope_check("G7.SCOPE", executed, levels, {"unit": "G5", "integration": "G6"},
                               command="system_test", own="system"))
    if unmapped:
        checks[-1].data["unmapped_cases"] = unmapped[:50]
    probs = list(ambiguous)
    if not specs:
        probs.append("no system test spec in tests.json: G7 needs at least one (G3 plans one per acceptance criterion "
                     "of every active functional requirement)")
    for tid in specs:
        st = executed.get(tid)
        if st is None:
            probs.append(f"{tid}: not executed")
        elif st != "passed":
            probs.append(f"{tid}: {st}")
    checks.append(Check("G7.TEST_MAPPING", "mechanical", "fail" if probs else "pass",
                        "system test specs not verified by passing tests" if probs
                        else f"{len(specs)} system test spec(s) passed", probs))
    coverage, cov_check = _ac_coverage(ctx, specs, executed)
    checks.append(cov_check)
    checks.append(_g7_no_weakening(ctx, executed))
    checks.append(_inputs_unchanged(ctx, "G7", files))
    roots = test_roots(p)
    g5_pass = last_with_status(ctx.entries, ctx.wi, "G5", "PASSED")
    g6_pass = last_with_status(ctx.entries, ctx.wi, "G6", "PASSED")
    extra.update({
        "test_files": {k: v for k, v in files.items() if any(k.startswith(r) for r in roots if r)},
        "executed_tests": dict(sorted(executed.items())),
        "executed_levels": {t: levels.get(t) for t in sorted(executed)},
        "unmapped_cases": unmapped[:50],
        "requirements_coverage": coverage,
        "basis_records": {"G5": g5_pass.id if g5_pass else None, "G6": g6_pass.id if g6_pass else None},
        "junit": {k: v for k, v in (junit_summary or {}).items() if k != "cases"},
        "failed_cases": [f"{c['classname']}::{c['name']} [{c['status']}] {c['message'][:200]}"
                         for c in cases if c["status"] in ("failed", "error")][:50],
    })
    return checks, extra, evidence


EVALUATORS: dict[str, Callable[[Ctx, dict, str], tuple[list[Check], dict, list[dict]]]] = {
    "G1": eval_g1, "G2": eval_g2, "G3": eval_g3, "G4": eval_g4, "G5": eval_g5, "G6": eval_g6, "G7": eval_g7,
}


# ---------------------------------------------------------------- orchestration
def preconditions(ctx: Ctx, gate: str, cache: dict) -> list[str]:
    reasons: list[str] = []
    gd = gate_def(gate)
    if not gd["implemented"]:
        return [f"{gate} ({gd['name']}) is an extension gate and is not implemented in this DevKit version"]
    if not ctx.integrity.ok:
        return [f"validator integrity: {p}" for p in ctx.integrity.problems]
    pg = prev_gate(gate)
    if pg:
        ps = gate_state(ctx, pg, cache)
        if ps["status"] != "PASSED":
            reasons.append(f"{pg} must be PASSED for the current inputs first (now {ps['status']})")
    last = last_eval(ctx.entries, ctx.wi, gate)
    if last is not None:
        rec = last.record
        if rec.get("status") == "BLOCKED" and rec.get("blocked_reason") == "three_consecutive_identical_failures" \
                and not unblocked_after(ctx.entries, ctx.wi, gate, last.seq):
            reasons.append(f"{gate} is BLOCKED after 3 identical failures ({last.id}); stop and report to the user. "
                           "Only the user can resume with 'vmodel unblock' in a terminal")
        if is_failure_record(rec):  # needs a DEFECT; the same definition decides valid failure evidence (D35)
            refs = {r for d in _defects(ctx) for r in _str_list(d.get("found_in_records"))}
            if last.id not in refs:
                reasons.append(f"rework record missing: {last.id} ({gate} {rec.get('status')}) must be referenced by a "
                               f"DEFECT in defects.json (found_in_records) with root_cause_phase, root_cause and fix_scope")
            else:
                errs = _optional_schema(ctx, "defects.json")
                if errs:
                    reasons.append("defects.json invalid: " + "; ".join(errs[:5]))
    return reasons


def failure_signature(checks: list[Check]) -> str:
    sig = sorted((c.id, sorted(c.sig if c.sig is not None else c.items)) for c in checks if c.status == "fail")
    return hash_obj(sig)


def derive_status(checks: list[Check]) -> str:
    worst = max((STATUS_RANK[c.status] for c in checks), default=0)
    return {4: "BLOCKED", 3: "FAILED", 2: "REVIEW_REQUIRED"}.get(worst, "PASSED")


# environment / input blocks: no DEFECT needed, not counted by the 3-strike rule (G6 adds the last two, 0.2.0)
NEUTRAL_BLOCKS = {"tool_unavailable", "misconfigured", "blocked", "applicability_unconfirmed",
                  "integration_evidence_insufficient"}


def consecutive_same_failures(entries: list[Entry], wi: str, gate: str, sig: str) -> int:
    """Identical FAILED evaluations since the last PASS/unblock/different failure.

    REVIEW_REQUIRED and environment BLOCKED records are skipped rather than resetting the streak, so the 3-strike
    rule cannot be dodged by interleaving them.
    """
    n = 0
    for e in reversed(gate_entries(entries, wi, gate)):
        r = e.record
        if r.get("type") == "unblock":
            break
        st = r.get("status")
        if st == "REVIEW_REQUIRED" or (st == "BLOCKED" and r.get("blocked_reason") in NEUTRAL_BLOCKS):
            continue
        if st == "FAILED" and r.get("failure_signature") == sig:
            n += 1
            continue
        break
    return n


def open_context(project: Project, wi: str) -> tuple[Ctx | None, list[str]]:
    integrity = integrity_for(project)
    ledger = Ledger(project)
    try:
        entries = ledger.entries()
    except LedgerError as exc:
        return None, [f"ledger integrity: {exc}"]
    project.wi_dir(wi)
    return build_ctx(project, wi, ledger, entries, integrity), []


def run_gate(project: Project, wi: str, gate: str) -> GateRun:
    if gate not in GATE_ORDER:
        return GateRun(wi, gate, "BLOCKED", [f"unknown gate {gate}"])
    # One evaluation at a time per project, so history-based rules see a consistent ledger.
    from .ledger import _Lock

    try:
        with _Lock(project.state_dir / ".gate.lock", timeout=900):
            return _run_gate_locked(project, wi, gate)
    except LedgerError as exc:
        return GateRun(wi, gate, "BLOCKED", [f"ledger: {exc}"])


def _run_gate_locked(project: Project, wi: str, gate: str) -> GateRun:
    ctx, errs = open_context(project, wi)
    if ctx is None:
        return GateRun(wi, gate, "BLOCKED", errs)
    cache: dict[str, dict] = {}
    reasons = preconditions(ctx, gate, cache)
    if reasons:
        return GateRun(wi, gate, "BLOCKED", reasons)
    files = cache.get(gate) or compute_manifest(project, wi, gate)
    mhash = hash_obj(files)
    checks, extra, evidence = EVALUATORS[gate](ctx, files, mhash)
    status = derive_status(checks)
    record: dict[str, Any] = {
        "type": "gate",
        "work_item": wi,
        "gate": gate,
        "status": status,
        "evaluated_at": runner.utc_now(),
        "validator": {"version": VERSION, "core_hash": ctx.integrity.core_hash, "mode": ctx.integrity.mode},
        "git": runner.git_info(project.root),
        "manifest": {"hash": mhash, "files": files},
        "checks": [c.as_dict() for c in checks],
        "review_required_by": sorted({str(c.data["review_required_by"]) for c in checks
                                      if c.status == "pending" and c.data.get("review_required_by")}),
        "evidence": evidence,
        "failure_signature": None,
        "blocked_reason": None,
        **extra,
    }
    if status == "FAILED":
        sig = failure_signature(checks)
        record["failure_signature"] = sig
        if consecutive_same_failures(ctx.entries, wi, gate, sig) >= 2:
            record["status"] = status = "BLOCKED"
            record["blocked_reason"] = "three_consecutive_identical_failures"
    elif status == "BLOCKED":
        reasons_b = [c.data.get("blocked_reason") for c in checks if c.status == "blocked"]
        record["blocked_reason"] = reasons_b[0] if reasons_b else "blocked"
    entry = ctx.ledger.append(record)
    out = GateRun(wi, gate, status, [], entry.record, True)
    if status == "BLOCKED" and record["blocked_reason"] == "three_consecutive_identical_failures":
        out.reasons.append("same failure 3 times in a row: automatic rework stops here; report to the user")
    return out


def hash_for_review(project: Project, wi: str, gate: str) -> dict:
    project.wi_dir(wi)
    files = compute_manifest(project, wi, gate)
    return {"work_item": wi, "gate": gate, "target_hash": hash_obj(files), "files": files}

"""Quality gate evaluation G1-G5 (SPEC section 3).

Only this module decides gate outcomes. Every evaluation is appended to the
signed ledger; preconditions that prevent an evaluation return BLOCKED
without a ledger record.
"""
from __future__ import annotations

import ast
import json
import os
import re
import tempfile
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

from . import VERSION, runner
from .hashing import hash_obj, sha256_file, short
from .integrity import IntegrityReport, check_against_lock, check_self
from .ledger import Entry, Ledger, LedgerError
from .project import ARTIFACTS, SCHEMA_FOR, Project
from .schema_lite import validate
from .textio import ArtifactError, display_decode, load_json
from .trace import TraceGraph, item_hashes, test_ids_in_text

DATA = Path(__file__).resolve().parent / "data"
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


# Gates whose records carry per-TEST results (G6/G7 join when implemented). Other gates' failures are N/A for tests.
TEST_EXECUTING_GATES = ("G5",)
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
    mapping = [ch for ch in rec.get("checks") or [] if isinstance(ch, dict) and ch.get("id") == "G5.TEST_MAPPING"]
    not_run = sorted({m.group(1) for ch in mapping for it in ch.get("items") or []
                      if isinstance(it, str) and (m := NOT_EXECUTED.match(it))})
    ex = rec.get("executed_tests")
    if not isinstance(ex, dict) or not ex:
        results = "unknown"  # no per-TEST results in the signed record (e.g. no JUnit produced)
    else:
        results = "partial" if not_run else "recorded"
    return {**c, "test_results": results, "failing_tests": failing_tests(rec), "unknown_tests": not_run,
            "recorded_tests": sorted(ex) if isinstance(ex, dict) else []}


def defect_trace(entries: list[Entry], wi: str, defects: list[dict],
                 evidence_check: Callable[[str, str | None], list[str]] | None = None,
                 ledger_error: str | None = None) -> list[dict]:
    """Defect view derived from the signed ledger (display only, never used for gate decisions).

    Per DEFECT: which cited records are valid failure evidence, the failing / UNKNOWN TEST ids they record, which
    failing TEST ids the DEFECT does not link, and the closure evidence `verified_by`: the first PASS, after the latest
    cited failure, of the most downstream gate that failed (a G5 PASS also implies G4 passed before it). Problems
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
                        verification_withheld=None, errors=errors, warnings=warnings)
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
        latest: dict[str, bool] = {}  # TEST id -> result unknown in the latest cited run that names it
        for c in runs:
            latest.update({t: False for t in c.get("recorded_tests") or []})
            latest.update({t: True for t in c["unknown_tests"]})
        unknown = sorted(t for t, u in latest.items() if u)
        no_results = bool(runs) and runs[-1]["test_results"] == "unknown" and not runs[-1]["unknown_tests"]
        unsure = [c for c in runs if c["test_results"] in ("unknown", "partial")]
        if unknown or no_results:
            recs = [c["record"] for c in unsure]
            w = _problem("unknown_test_result", recs[0] if len(recs) == 1 else None,
                         f"{did}: per-TEST results of {', '.join(recs)} are UNKNOWN (not executed or not recorded): "
                         + (", ".join(unknown) or "no per-TEST results recorded"), unknown)
            warnings.append({**w, "records": recs})
        closure_gate = verified_by = None
        if valid:
            # baseline = the latest cited failure; closure gate = the most downstream gate that failed, from the signed
            # records (not the agent-written `gate`), so a G4 re-pass cannot close a defect whose G5 still fails
            last = max(valid, key=lambda e: e.seq)
            closure_gate = max((str(e.record.get("gate")) for e in valid),
                               key=lambda g: GATE_ORDER.index(g) if g in GATE_ORDER else -1)
            for e in gate_entries(entries, wi, closure_gate):
                if e.seq > last.seq and e.record.get("type") == "gate" and e.record.get("status") == "PASSED":
                    verified_by = e.id
                    break
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
                    errors=errors, warnings=warnings)
        out.append(view)
    return out


# ---------------------------------------------------------------- state (shared with status)
def gate_state(ctx: Ctx, gate: str, current_manifests: dict[str, dict] | None = None) -> dict:
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
                "junitxml" in node.value or "PYTEST_ADDOPTS" in node.value):
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
    missing = [t for t in g.unit_tests() if t not in present]
    orphans = sorted(present - set(g.tests))
    status = "fail" if missing or multi else ("warn" if orphans else "pass")
    checks.append(Check("G4.TEST_CODE", "mechanical", status,
                        "unit test specs without a test function test_TEST_nnn_... / ambiguous test names"
                        if missing or multi else ("test code references TEST ids not in tests.json" if orphans
                                                  else f"{len(g.unit_tests())} unit test spec(s) implemented"),
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

    checks.append(check_review(ctx, "G4", mhash))
    return checks, {}, evidence


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

    passed_ids = {t for t, s in executed.items() if s == "passed"}
    probs = [rid for rid in g.active("functional") if not (set(g.tests_for_req(rid)) & passed_ids)]
    checks.append(Check("G5.REQ_COVERAGE", "mechanical", "fail" if probs else "pass",
                        "functional requirements without a passed test" if probs
                        else "every functional requirement has a passed test", probs))

    roots = test_roots(p)
    test_files = {k: v for k, v in files.items() if any(k.startswith(r) for r in roots if r)}
    checks.append(_no_weakening(ctx, test_files, executed))

    changed = diff_manifest(files, after)
    checks.append(Check("G5.INPUTS_UNCHANGED", "mechanical", "fail" if changed else "pass",
                        "verified files changed during the test run" if changed else "inputs unchanged during the run",
                        changed))
    extra = {"test_files": test_files, "executed_tests": dict(sorted(executed.items())),
             "junit": {k: v for k, v in (junit_summary or {}).items() if k != "cases"}, "failed_cases": failed_cases[:50]}
    return checks, extra, evidence


def _no_weakening(ctx: Ctx, test_files: dict[str, str], executed: dict[str, str]) -> Check:
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
    lost = sorted(t for t in old_exec if t not in executed and t not in removed_ok)
    probs += [f"{t} was executed in {prev.id} but not now" for t in lost]
    if probs:
        return Check("G5.NO_WEAKENING", "mechanical", "fail", "possible test weakening", probs)
    detail = f"{len(changed)} justified test file change(s) since {prev.id}" if changed else f"no test change since {prev.id}"
    return Check("G5.NO_WEAKENING", "mechanical", "pass", detail, changed)


EVALUATORS: dict[str, Callable[[Ctx, dict, str], tuple[list[Check], dict, list[dict]]]] = {
    "G1": eval_g1, "G2": eval_g2, "G3": eval_g3, "G4": eval_g4, "G5": eval_g5,
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


NEUTRAL_BLOCKS = {"tool_unavailable", "misconfigured", "blocked"}


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

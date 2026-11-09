"""Derived status, traceability views, impact analysis and Markdown reports."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .gates import (GATE_ORDER, REVIEWER, Ctx, _items, _str_list, build_ctx, defect_trace, g6_applicability,
                    gate_def, gate_state, gates_def, implemented_gates, integration_config_problems, integrity_for,
                    last_eval, last_with_status, project_test_levels)
from .hashing import short
from .integrity import IntegrityReport
from .ledger import Ledger, LedgerError
from .project import Project
from .runner import check_evidence
from .trace import item_hashes

MVP_NOTE = ("Implemented gates: G1-G6 (G6 integration verification is N/A only for a confirmed single-component work "
            "item without interfaces). G7 (system) is an extension gate, so a work item can reach PARTIALLY_VERIFIED at "
            "most. This is NOT a full V-Model completion.")


def _contexts(project: Project, wi: str | None) -> tuple[list[Ctx], dict]:
    integrity = integrity_for(project)
    ledger = Ledger(project)
    ledger_info: dict[str, Any] = {"ok": True, "error": None, "entries": 0}
    try:
        entries = ledger.entries()
        ledger_info["entries"] = len(entries)
    except LedgerError as exc:
        entries = []
        ledger_info.update(ok=False, error=str(exc))
        integrity = IntegrityReport(False, integrity.version, integrity.core_hash, integrity.mode,
                                    [*integrity.problems, f"ledger: {exc}"])
    wis = [wi] if wi else project.work_items()
    ctxs = []
    for w in wis:
        project.wi_dir(w)
        ctxs.append(build_ctx(project, w, ledger, entries, integrity))
    return ctxs, {"validator": integrity.as_dict(), "ledger": ledger_info}


def wi_status(gates: list[dict], profile: str) -> str:
    prof = gates_def()["profiles"].get(profile) if isinstance(profile, str) else None
    if prof is None:
        return "BLOCKED"  # unknown profile: nothing can be concluded
    impl = [g for g in gates if g["status"] != "NOT_IMPLEMENTED"]
    statuses = [g["status"] for g in impl]
    if any(s == "BLOCKED" for s in statuses):
        return "BLOCKED"
    if statuses and all(s == "PASSED" for s in statuses):
        required = prof.get("required_gates") or []
        if prof.get("implemented") and required and all(gate_def(r)["implemented"] for r in required):
            return "COMPLETED"
        return "PARTIALLY_VERIFIED"
    if all(s == "NOT_STARTED" for s in statuses):
        return "NOT_STARTED"
    return "IN_PROGRESS"


def _verified_prefix(gates: list[dict]) -> str:
    g6 = next((g for g in gates if g["gate"] == "G6"), {})
    if g6.get("status") == "PASSED" and g6.get("applicability") == "not_applicable":
        return (f"G1-G5 PASSED, G6 N/A (no integration scope: {g6.get('na_reason') or 'confirmed at G2/G3'}; no "
                "integration test executed)")
    if g6.get("status") == "PASSED":
        return "G1-G6 verified"
    return "G1-G5 verified"


def _g6_next(wi: str, g: dict, preview: dict | None) -> str | None:
    """G6-specific next steps: before the first evaluation (from the applicability preview) and per block reason."""
    s, reason = g["status"], g.get("blocked_reason")
    pv = preview or {}
    if g.get("not_evaluated"):
        if pv.get("applicability") == "required" and pv.get("config_problems"):
            reason = "misconfigured"
        elif pv.get("applicability") == "unconfirmed":
            reason = "applicability_unconfirmed"
        else:
            return f"run 'vmodel gate {wi} G6' (not evaluated yet: no integration verification has run)"
    elif s != "BLOCKED":
        return None
    if reason == "misconfigured":
        return (f"G6 needs the integration_test command: ask the user to add it to .vmodel/config.json (the agent "
                "cannot edit it; in a terminal: 'vmodel configure-tests --integration <path>'). The unit_test command "
                f"is never used instead. Then re-run G4 and G5 (config changed) and 'vmodel gate {wi} G6'")
    if reason == "applicability_unconfirmed":
        first = (pv.get("problems") or g.get("notes") or [""])[0]
        return (f"G6 N/A is not confirmed: {REVIEWER} records integration_applicability (decision not_required, "
                "reason, every external endpoint) in the G2 and G3 reviews, and removed interfaces need removed_ids in "
                f"a CR/DEFECT; or add the integration specs. ({str(first)[:200]}) Then re-run G2, G3 and "
                f"'vmodel gate {wi} G6'")
    if reason == "integration_evidence_insufficient":
        return ("G6 BLOCKED: a runtime integration path declared at G4 has no runtime proof (the provider did not run "
                "in a traced Python process during that test). Fix the test (keep PYTHONPATH when starting Python, no "
                f"-I/-E, or call the API directly), re-run G4-G5, then 'vmodel gate {wi} G6'; report to the user if "
                "unsure")
    return None


def next_action(wi: str, gates: list[dict], preview: dict | None = None) -> str:
    for g in gates:
        s = g["status"]
        gid = g["gate"]
        if s == "PASSED":
            continue
        if s == "NOT_IMPLEMENTED":
            return f"{_verified_prefix(gates)}. {gid}+ are extension gates (not implemented); report PARTIALLY_VERIFIED."
        if gid == "G6":
            g6 = _g6_next(wi, g, preview)
            if g6:
                return g6
        if s == "BLOCKED":
            return f"{gid} BLOCKED: stop and report to the user ({'; '.join(g.get('notes') or [g.get('blocked_reason', '')])[:300]})"
        if s == "FAILED":
            return f"{gid} FAILED: run /vmodel:rework (record a DEFECT for {g.get('record_id')}, fix, re-evaluate)"
        if s == "REVIEW_REQUIRED":
            who = ", ".join(g.get("review_required_by") or ["vmodel:verifier"])
            return f"{gid} REVIEW_REQUIRED by {who}; then re-run 'vmodel gate {wi} {gid}'"
        if s == "STALE":
            return f"{gid} STALE (inputs changed): re-review if needed and re-run 'vmodel gate {wi} {gid}'"
        return f"{gid} {s}: author its artifacts, then run 'vmodel gate {wi} {gid}'"
    return "all gates passed"


def defect_views(ctx: Ctx, ledger_error: str | None = None) -> list[dict]:
    """defect_trace() with the evidence-integrity check of the records each DEFECT relies on (display only)."""
    def check(path: str, sha: str | None) -> list[str]:
        try:
            return check_evidence(ctx.project, ctx.ledger, path, sha)
        except LedgerError as exc:
            return [f"{path}: {exc}"]

    return defect_trace(ctx.entries, ctx.wi, _items(ctx.arts.get("defects.json"), "defects"),
                        evidence_check=check, ledger_error=ledger_error)


def defect_check_counts(defects: list[dict]) -> dict:
    return {"errors": sum(len(d.get("errors") or []) for d in defects),
            "warnings": sum(len(d.get("warnings") or []) for d in defects)}


def ledger_unverifiable(d: dict) -> bool:
    return any(p["category"] == "evidence_integrity" and p.get("record") is None for p in d.get("errors") or [])


CLOSURE_STATES = ("OPEN", "FIX_APPLIED", "REVERIFY_REQUIRED", "VERIFICATION_FAILED", "CLOSED", "UNKNOWN",
                  "OUT_OF_SCOPE")


def closure_view(d: dict, gates: dict[str, dict]) -> dict:
    """Derived closure state (D32 option C, D37); defects.json keeps only the agent's claim `open` / `fixed`.

    Display only, from the signed ledger and the current gate state; first match wins:
    UNKNOWN              the ledger failed its integrity check: nothing is guessed.
    OUT_OF_SCOPE         (0.2.0, D42) the DEFECT's closure gate is G6 and G6 is now N/A for the current inputs: the
                         interfaces were removed with justification (CR/DEFECT removed_ids) and the G2/G3 reviews
                         confirmed it. Not verified and not CLOSED; past failures and the DEFECT stay as they are.
    VERIFICATION_FAILED  `last_verification` is a failure: for some gate the DEFECT cites a failure of, the latest
                         PASSED-or-failure evaluation since its first cited failure is FAILED or a 3-strike BLOCKED
                         (REVIEW_REQUIRED and environment BLOCKED are neutral, as in the 3-strike count).
    UNKNOWN              a PASS exists (`verification_withheld`) but its evidence or the cited failure's does not match
                         the signed ledger: neither "verified" nor "not verified" can be stated.
    CLOSED               verified (`verified_by`) and that gate is PASSED for the current inputs (gate_state already
                         requires the upstream gates to be PASSED).
    REVERIFY_REQUIRED    verified once, but that gate is not PASSED now (STALE, REVIEW_REQUIRED, BLOCKED ...).
    FIX_APPLIED / OPEN   no verification yet (claim `fixed` / `open`).
    `verified_by` and `verification_history` keep the past successes in every state. `closure_action` names the
    next step (reverify, rework, unblock, resolve_block, check_integrity) or is None. 'verified by' is worded only
    for CLOSED; past successes read 'previously passed in'.
    """
    vb, gate, claimed = d.get("verified_by"), d.get("closure_gate"), d.get("claimed_status")
    now: dict = gates.get(str(gate)) or {}
    attempt: dict = d.get("last_verification") or {}
    record = action = None
    if ledger_unverifiable(d):
        state, now_status, action = "UNKNOWN", None, "check_integrity"
    elif gate == "G6" and now.get("status") == "PASSED" and now.get("applicability") == "not_applicable":
        state, now_status, record = "OUT_OF_SCOPE", "N/A", now.get("record_id")
    elif attempt.get("failure"):
        state, now_status, record = "VERIFICATION_FAILED", now.get("status"), attempt.get("record")
        failed_now: dict = gates.get(str(attempt.get("gate"))) or {}
        if failed_now.get("status") != "BLOCKED":
            action = "rework"
        elif failed_now.get("blocked_reason") == "three_consecutive_identical_failures":
            action = "unblock"  # only `vmodel unblock` (user, TTY) lifts it
        else:
            action = "resolve_block"  # e.g. validator integrity; `vmodel unblock` does not apply
    elif d.get("verification_withheld"):
        state, now_status, action = "UNKNOWN", now.get("status"), "check_integrity"
    elif vb:
        state, now_status = ("CLOSED" if now.get("status") == "PASSED" else "REVERIFY_REQUIRED"), now.get("status")
        record = now.get("record_id")
        if state == "REVERIFY_REQUIRED":
            action = "resolve_block" if now_status == "BLOCKED" else "reverify"
    else:
        state, now_status = ("FIX_APPLIED" if claimed == "fixed" else "OPEN"), None
    note = None
    if vb and claimed == "open" and state == "CLOSED":
        note = f"defects.json says open, but the ledger shows the fix verified by {vb}"
    elif vb and claimed == "open" and state == "REVERIFY_REQUIRED":
        note = f"defects.json says open, but the ledger shows the fix passed {gate} in {vb} (no longer current)"
    return {"closure_state": state, "closure_gate_status": now_status, "closure_gate_record": record,
            "closure_action": action, "claim_note": note}


def scope_removal(ctx: Ctx, d: dict, g6: dict) -> dict:
    """OUT_OF_SCOPE detail: the interface / integration TEST ids of the cited G6 failures and who removed them."""
    by_id = {e.id: e for e in ctx.entries}
    ids: set[str] = set()
    for r in d.get("found_in_records") or []:
        e = by_id.get(r)
        if e is None or e.record.get("gate") != "G6":
            continue
        ids |= {i.get("id") for i in e.record.get("interfaces") or [] if isinstance(i, dict) and i.get("id")}
        ids |= set(_str_list(e.record.get("integration_specs")))
    removers: dict[str, list[str]] = {}
    reasons: dict[str, str] = {}
    for src, key in ((_items(ctx.arts.get("change-requests.json"), "change_requests"), "reason"),
                     (_items(ctx.arts.get("defects.json"), "defects"), "root_cause")):
        for x in src:
            if x.get("status") == "rejected":
                continue
            hit = [i for i in _str_list(x.get("removed_ids")) if i in ids]
            for i in hit:
                removers.setdefault(i, []).append(str(x.get("id")))
            if hit:
                reasons[str(x.get("id"))] = str(x.get(key) or "")[:200]
    return {"g6_record": g6.get("record_id"), "removed_ids": {i: removers.get(i, []) for i in sorted(ids)},
            "reasons": reasons, "failed_records": list(d.get("found_in_records") or [])}


SUMMARY_KEYS = ("passed_current", "na", "not_evaluated", "review_required", "in_progress", "not_started", "stale",
                "failed", "blocked", "not_implemented")


def gate_summary(gates: list[dict]) -> dict:
    """Gate results apart from the work item status (D41 decision 4)."""
    out: dict[str, list[str]] = {k: [] for k in SUMMARY_KEYS}
    for g in gates:
        st = g["status"]
        if st == "PASSED":
            out["na" if g.get("applicability") == "not_applicable" else "passed_current"].append(g["gate"])
        elif st == "NOT_IMPLEMENTED":
            out["not_implemented"].append(g["gate"])
        elif g.get("not_evaluated"):
            out["not_evaluated"].append(g["gate"])
        elif st.lower() in out:
            out[st.lower()].append(g["gate"])
    return out


def _span(ids: list[str]) -> str:
    nums = [GATE_ORDER.index(x) for x in ids]
    if len(ids) > 1 and nums == list(range(nums[0], nums[0] + len(ids))):
        return f"{ids[0]}-{ids[-1]}"
    return ", ".join(ids)


def summary_text(summary: dict) -> str:
    words = {"passed_current": "PASSED (current)", "na": "N/A", "not_evaluated": "not evaluated",
             "review_required": "REVIEW_REQUIRED", "in_progress": "IN_PROGRESS", "not_started": "NOT_STARTED",
             "stale": "STALE", "failed": "FAILED", "blocked": "BLOCKED", "not_implemented": "not implemented"}
    return ", ".join(f"{_span(summary[k])} {words[k]}" for k in SUMMARY_KEYS if summary.get(k))


def scope_warnings(ctx: Ctx) -> list[str]:
    """REQ-G6-06: without integration_test, integration tests run by the unit command are flagged (display only)."""
    try:
        cfg = ctx.project.config()
    except Exception:  # status must not fail on a broken config; integrity and gates report it
        return []
    if not isinstance(cfg, dict) or "integration_test" in cfg:
        return []
    last = last_eval(ctx.entries, ctx.wi, "G5")
    ex = (last.record.get("executed_tests") if last else None) or {}
    if not isinstance(ex, dict) or not ex:
        return []
    levels = project_test_levels(ctx)
    mixed = sorted(t for t in ex if levels.get(t) == "integration")
    if not mixed:
        return []
    return [f"G5 ({last.id}, unit_test command) executed integration test(s) {', '.join(mixed)}: these results are not "
            "integration verification (G6 runs the separate integration_test command). Ask the user to configure "
            "integration_test ('vmodel configure-tests') to separate them"]


def g6_preview(ctx: Ctx) -> dict:
    app = g6_applicability(ctx)
    try:
        cfg = ctx.project.config().get("integration_test")
    except Exception:
        cfg = None
    return {"applicability": app["applicability"], "problems": app["problems"][:5],
            "integration_test_configured": cfg is not None,
            "config_problems": integration_config_problems(cfg) if app["applicability"] == "required" else []}


def render_problem(p: dict) -> str:
    """'ERROR [invalid_citation] ...' / 'WARNING [unlinked_failing_test] ...': the same labels in status, lint, report."""
    return f"{p['severity'].upper()} [{p['category']}] {p['detail']}"


def project_status(project: Project, wi: str | None = None) -> dict:
    ctxs, meta = _contexts(project, wi)
    out: dict[str, Any] = {"project": str(project.root), **meta, "mvp_note": MVP_NOTE, "work_items": []}
    ledger_error = None if meta["ledger"]["ok"] else meta["ledger"]["error"]
    for ctx in ctxs:
        cache: dict[str, dict] = {}
        gates = [gate_state(ctx, g, cache) for g in GATE_ORDER]
        wi_doc = ctx.arts.get("workitem.json")
        wi_doc = wi_doc if isinstance(wi_doc, dict) else {}
        profile = wi_doc.get("profile", "STANDARD")
        defects = defect_views(ctx, ledger_error)
        by_gate = {g["gate"]: g for g in gates}
        for d in defects:
            d.update(closure_view(d, by_gate))
            if d.get("closure_state") == "OUT_OF_SCOPE":
                d["scope_removal"] = scope_removal(ctx, d, by_gate.get("G6") or {})
        preview = g6_preview(ctx) if ctx.integrity.ok else None
        item = {"id": ctx.wi, "title": wi_doc.get("title"), "profile": profile,
                "status": wi_status(gates, profile), "gates": gates,
                "next_action": next_action(ctx.wi, gates, preview),
                "gate_summary": gate_summary(gates), "scope_warnings": scope_warnings(ctx),
                "g6_applicability_preview": preview,
                "defects": defects, "defect_checks": defect_check_counts(defects)}
        if item["status"] == "BLOCKED" and not isinstance(gates_def()["profiles"].get(profile), dict):
            item["profile_note"] = f"unknown profile {profile!r} in workitem.json"
            item["next_action"] = f"fix the profile in {ctx.wi}/workitem.json (STANDARD)"
        elif not gates_def()["profiles"].get(profile, {}).get("implemented", False):
            item["profile_note"] = f"profile {profile} is not implemented in the MVP; gates follow STANDARD G1-G5"
        out["work_items"].append(item)
    return out


def tests_summary(d: dict) -> str:
    """Failing TEST ids from the valid failure records; N/A for gates that run no tests; UNKNOWN never reads as '-'."""
    if any(p["category"] == "evidence_integrity" and p.get("record") is None for p in d.get("errors") or []):
        return "failing tests (ledger): cannot be verified (ledger integrity failed)"
    valid = [c for c in d.get("citations") or [] if c.get("valid")]
    if not valid:
        return "failing tests (ledger): none (no valid failure record cited)"
    if all(c["test_results"] == "not_applicable" for c in valid):
        return f"failing tests (ledger): N/A ({'/'.join(sorted({str(c['gate']) for c in valid}))} does not run tests)"
    unsure = any(w["category"] == "unknown_test_result" for w in d.get("warnings") or [])
    text = f"failing tests (ledger): {', '.join(d['failing_tests']) or ('none confirmed' if unsure else 'none')}"
    if unsure:
        text += f"; UNKNOWN: {', '.join(d.get('unknown_tests') or []) or 'no per-TEST results recorded'}"
    return text


def _now_passed(d: dict) -> str:
    cur = d.get("closure_gate_record")
    return f"{d.get('closure_gate')} PASSED" + (f" ({cur})" if cur and cur != d["verified_by"] else "")


def _previously(d: dict) -> str:
    """Past successes, never worded as a current state ('verified by' is reserved for CLOSED):
    'previously passed in R1 (last PASS R5)'. A withheld PASS (evidence mismatch) is not a past success."""
    withheld = d.get("verification_withheld")
    hist = [r for r in d.get("verification_history") or [] if r != withheld]
    first = d.get("verified_by") or (hist[0] if hist else None)
    if not first:
        return ""
    return f"previously passed in {first}" + (f" (last PASS {hist[-1]})" if hist and hist[-1] != first else "")


def _withheld(d: dict) -> str:
    w = d.get("verification_withheld")
    return f"PASS {w} withheld (its evidence or the cited failure's does not match the signed ledger)" if w else ""


def _failed_attempt(d: dict) -> str:
    a = d.get("last_verification") or {}
    why = f" ({a['blocked_reason']})" if a.get("blocked_reason") else ""
    return f"{a.get('gate') or d.get('closure_gate')} re-verification {a.get('record')} {a.get('status')}{why}"


def _out_of_scope(d: dict) -> str:
    sr = d.get("scope_removal") or {}
    removed = sr.get("removed_ids") or {}
    by = sorted({x for v in removed.values() for x in v})
    return (f"not verified: scope removed, G6 is now N/A ({d.get('closure_gate_record')}); removed "
            f"{', '.join(sorted(removed)) or 'the interfaces'} by {', '.join(by) or 'CR/DEFECT removed_ids'}; "
            f"failure {', '.join(d.get('found_in_records') or [])} kept in the ledger")


def closure_text(d: dict) -> str:
    """Closure evidence for display. A past `verified_by` is shown as current only while its gate is PASSED."""
    state, gate, now = d.get("closure_state"), d.get("closure_gate"), d.get("closure_gate_status")
    if state == "OUT_OF_SCOPE":
        return _out_of_scope(d)
    if state == "UNKNOWN":
        if d.get("verification_withheld"):
            return (f"verification cannot be determined: {d['verification_withheld']} withheld (its evidence or the "
                    "cited failure's does not match the signed ledger)")
        return "verification cannot be determined: the ledger failed its integrity check"
    if state == "VERIFICATION_FAILED":
        extra = "".join(f", {x}" for x in (_previously(d), _withheld(d)) if x)
        failed_gate = (d.get("last_verification") or {}).get("gate") or gate
        what = {"unblock": "the user must unblock (three identical failures)",
                "resolve_block": f"{failed_gate} is now BLOCKED: resolve the block first"}.get(d.get("closure_action"),
                                                                                             "rework")
        return f"{_failed_attempt(d)}{extra}: {what}"
    if state == "REVERIFY_REQUIRED":
        return (f"{_previously(d)}, {gate} is now BLOCKED: resolve the block first" if now == "BLOCKED"
                else f"{_previously(d)}, {gate} is now {now}: re-verify")
    if state == "CLOSED":
        return f"verified by {d['verified_by']}, {_now_passed(d)}"
    return "not verified yet"


def render_defect(d: dict) -> list[str]:
    state = d.get("closure_state") or ("FIX_APPLIED" if d.get("claimed_status") == "fixed" else "OPEN")
    lines = [f"{d['id']} {state} [claimed {d['claimed_status']}; {closure_text(d)}] {d['gate']} root cause "
             f"{d['root_cause_phase']}; {tests_summary(d)}"]
    if d.get("claim_note"):
        lines.append(f"    note: {d['claim_note']}")
    lines += [f"    {render_problem(p)}" for p in [*(d.get("errors") or []), *(d.get("warnings") or [])]]
    return lines


def render_status(st: dict) -> str:
    lines = [f"Project: {st['project']}"]
    v = st["validator"]
    lines.append(f"Validator: {v['version']} ({v['mode']}) core {short(v['core_hash'])} integrity "
                 f"{'OK' if v['ok'] else 'FAILED'}")
    for p in v["problems"]:
        lines.append(f"  ! {p}")
    lg = st["ledger"]
    lines.append(f"Ledger: {'OK' if lg['ok'] else 'INVALID'} ({lg['entries']} entries)" +
                 (f" - {lg['error']}" if lg["error"] else ""))
    if not st["work_items"]:
        lines.append("No work items. Create one with 'vmodel new-wi --title ... --request ...'.")
    for w in st["work_items"]:
        lines.append("")
        dc = w.get("defect_checks") or defect_check_counts(w.get("defects") or [])
        lines.append(f"{w['id']} [{w['status']}] {w['title'] or ''} (profile {w['profile']}); "
                     f"defect checks: {dc['errors']} error(s), {dc['warnings']} warning(s)")
        if w.get("gate_summary"):
            lines.append(f"  gates: {summary_text(w['gate_summary'])}")
        for wn in w.get("scope_warnings") or []:
            lines.append(f"  ! scope: {wn}")
        for g in w["gates"]:
            extra = ""
            if g.get("record_id"):
                extra = f" {g['record_id']} @ {g.get('evaluated_at', '')}"
            lines.append(f"  {g['gate']} {g['name']:<32} {g.get('display_status') or g['status']:<16}{extra}")
            if g.get("display_status") == "N/A":
                eps = ", ".join(g.get("external_endpoints") or []) or "none"
                lines.append(f"      - N/A: recorded PASSED {g.get('record_id')}, no integration test executed "
                             f"({g.get('na_reason')}); external endpoints reviewed: {eps}")
            elif g.get("not_evaluated"):
                lines.append("      - not evaluated yet: no integration verification has run")
            elif g.get("coverage") and g["status"] == "PASSED":
                c = g["coverage"]
                lines.append(f"      - IF {c['covered']}/{c['interfaces']} covered (static call path or runtime trace, "
                             f"passed), {c['integration_tests_passed']} integration test(s) passed")
            for n in g.get("notes") or []:
                lines.append(f"      - {n}")
            for c in (g.get("changed_files") or [])[:10]:
                lines.append(f"      * {c}")
            if g.get("review_required_by") and g["status"] == "REVIEW_REQUIRED":
                lines.append(f"      review required by: {', '.join(g['review_required_by'])}")
            for c in g.get("failed_checks") or []:
                lines.append(f"      x {c['id']} {c['status']}: {c['detail'][:200]}")
                for it in c["items"][:5]:
                    lines.append(f"          {str(it).splitlines()[0][:200] if str(it) else ''}")
            if g.get("failing_tests"):
                lines.append(f"      failing tests: {', '.join(g['failing_tests'])}")
        for d in w.get("defects") or []:
            lines += [f"  {ln}" for ln in render_defect(d)]
        lines.append(f"  next: {w['next_action']}")
        if w.get("profile_note"):
            lines.append(f"  note: {w['profile_note']}")
    lines.append("")
    lines.append(st["mvp_note"])
    return "\n".join(lines)


# ---------------------------------------------------------------- trace
def trace_view(project: Project, wi: str) -> dict:
    ctxs, _ = _contexts(project, wi)
    ctx = ctxs[0]
    g = ctx.graph
    last_g5 = last_eval(ctx.entries, wi, "G5")
    executed = dict((last_g5.record.get("executed_tests") if last_g5 else None) or {})
    # integration results come from the last G6 run that executed tests (REQ rows and interface rows, 0.2.0)
    g6_runs = [e for e in reversed([x for x in ctx.entries if x.record.get("work_item") == wi
                                    and x.record.get("gate") == "G6" and x.record.get("type") == "gate"])
               if e.record.get("applicability") == "required" and e.record.get("executed_tests")]
    last_g6 = g6_runs[0] if g6_runs else None
    g6_exec = (last_g6.record.get("executed_tests") if last_g6 else None) or {}
    for tid, t in g.tests.items():
        if t.get("level") == "integration":
            executed.pop(tid, None)
            if tid in g6_exec:
                executed[tid] = g6_exec[tid]
    rows = []
    for rid in sorted(g.reqs):
        r = g.reqs[rid]
        tests = g.tests_for_req(rid)
        rows.append({
            "req": rid, "type": r.get("type"), "status": r.get("status"), "title": r.get("title"),
            "acceptance_criteria": [a.get("id") for a in r.get("acceptance_criteria") or []],
            "components": g.comps_for_req(rid), "design_units": g.units_for_req(rid),
            "symbols": [f"{g.units[u].get('module')}:{g.units[u].get('name')}" for u in g.units_for_req(rid)],
            "tests": {t: {"level": g.tests[t].get("level"), "result": executed.get(t, "not run")} for t in tests},
        })
    reverse = {tid: sorted(g.reqs_covered_by_test(tid)) for tid in sorted(g.tests)}
    recorded = {i.get("id"): i for i in (last_g6.record.get("interfaces") if last_g6 else None) or []
                if isinstance(i, dict)}
    last_any = last_eval(ctx.entries, wi, "G6")
    na = bool(last_any and last_any.record.get("applicability") == "not_applicable")
    ifaces = []
    for iid, i in sorted(g.ifaces.items()):
        rec = recorded.get(iid) or {}
        tests = {}
        for tid in sorted(t for t, x in g.tests.items() if iid in _str_list(x.get("verifies"))):
            tv = (rec.get("tests") or {}).get(tid) or {}
            tests[tid] = {"level": g.tests[tid].get("level"), "result": g6_exec.get(tid, "not run"),
                          "path": tv.get("path"), "function": tv.get("function")}
        ifaces.append({"id": iid, "name": i.get("name"), "provider": i.get("provider"),
                       "consumers": i.get("consumers") or [], "tests": tests, "covered": rec.get("covered"),
                       "g6_record": last_g6.id if last_g6 else None})
    return {"work_item": wi, "rows": rows, "reverse": reverse, "dangling": g.dangling(),
            "results_from": last_g5.id if last_g5 else None,
            "integration_results_from": last_g6.id if last_g6 else None, "interfaces": ifaces,
            "g6": "N/A (no interfaces)" if na else None}


def render_trace(tv: dict) -> str:
    lines = [f"Traceability {tv['work_item']} (results from {tv['results_from'] or 'no G5 run'})"]
    for r in tv["rows"]:
        lines.append(f"{r['req']} [{r['type']}/{r['status']}] {r['title']}")
        lines.append(f"   AC: {', '.join(r['acceptance_criteria']) or '-'}")
        lines.append(f"   ARCH: {', '.join(r['components']) or '-'}   DESIGN: {', '.join(r['design_units']) or '-'}")
        lines.append(f"   CODE: {', '.join(r['symbols']) or '-'}")
        tests = [f"{t}({v['level']}:{v['result']})" for t, v in r["tests"].items()]
        lines.append(f"   TEST: {', '.join(tests) or '-'}")
    if tv.get("interfaces") or tv.get("g6"):
        lines.append(f"Interfaces (integration results from {tv.get('integration_results_from') or tv.get('g6') or 'no G6 run'}):")
    for i in tv.get("interfaces") or []:
        lines.append(f"{i['id']} {i['name']}: {i['provider']} -> {', '.join(i['consumers']) or '-'} "
                     f"(covered: {'yes' if i['covered'] else 'no' if i['covered'] is False else 'not evaluated'})")
        tests = [f"{t}({v['result']}{', ' + v['path'] if v.get('path') else ''})" for t, v in i["tests"].items()]
        lines.append(f"   TEST: {', '.join(tests) or '-'}")
    lines.append("Reverse (TEST -> REQ):")
    for t, reqs in tv["reverse"].items():
        lines.append(f"   {t} -> {', '.join(reqs) or '(none)'}")
    lines.append("Dangling references: " + ("none" if not tv["dangling"] else ""))
    for d in tv["dangling"]:
        lines.append(f"   ! {d}")
    return "\n".join(lines)


# ---------------------------------------------------------------- impact
def impact_view(project: Project, wi: str) -> dict:
    ctxs, _ = _contexts(project, wi)
    ctx = ctxs[0]
    cur = item_hashes(ctx.arts, ["requirements.json", "architecture.json", "design.json", "tests.json"])
    changed: set[str] = set()
    baselines = {}
    for gate in ("G1", "G2", "G3"):
        lp = last_with_status(ctx.entries, wi, gate, "PASSED")
        if not lp:
            continue
        baselines[gate] = lp.id
        old = lp.record.get("item_hashes") or {}
        for k in set(old) | {k for k in cur if k.split("-")[0] in _prefixes(gate)}:
            if old.get(k) != cur.get(k):
                changed.add(k)
    impacted = sorted(ctx.graph.downstream(changed) - changed)
    cache: dict[str, dict] = {}
    gates = [gate_state(ctx, g, cache) for g in implemented_gates()]
    stale = [g["gate"] for g in gates if g["status"] == "STALE"]
    return {"work_item": wi, "baselines": baselines, "changed_items": sorted(changed), "impacted_items": impacted,
            "stale_gates": stale,
            "changed_files": {g["gate"]: g.get("changed_files", []) for g in gates if g.get("changed_files")}}


def _prefixes(gate: str) -> set[str]:
    return {"G1": {"REQ"}, "G2": {"ARCH", "IF"}, "G3": {"DESIGN", "TEST"}}[gate]


def render_impact(iv: dict) -> str:
    lines = [f"Impact {iv['work_item']} (baselines: {iv['baselines'] or 'none'})",
             f"Changed items: {', '.join(iv['changed_items']) or 'none'}",
             f"Impacted downstream items: {', '.join(iv['impacted_items']) or 'none'}",
             f"STALE gates: {', '.join(iv['stale_gates']) or 'none'}"]
    for gate, files in iv["changed_files"].items():
        lines.append(f"  {gate}: {'; '.join(files[:8])}")
    if iv["changed_items"]:
        lines.append("Requirement changes need a change request (change-requests.json) listing them in 'affected'.")
    return "\n".join(lines)


# ---------------------------------------------------------------- report
def report_closure(d: dict) -> str:
    state, gate = d.get("closure_state"), d.get("closure_gate")
    if state == "OUT_OF_SCOPE":
        return _out_of_scope(d)
    if state == "UNKNOWN":
        withheld = d.get("verification_withheld")
        return "verification cannot be determined" + (f": {withheld} withheld" if withheld else "")
    if state == "VERIFICATION_FAILED":
        return _failed_attempt(d)
    if state == "REVERIFY_REQUIRED":
        return f"{_previously(d)}, but {gate} is now {d.get('closure_gate_status')}"
    if state == "CLOSED":
        return f"verified by {d['verified_by']}"  # 0.1.3 wording
    return "not verified yet"


def report_closure_details(d: dict) -> list[str]:
    state, vb, gate, now = d.get("closure_state"), d["verified_by"], d.get("closure_gate"), d.get("closure_gate_status")
    prev = _previously(d)
    if state == "UNKNOWN" and d.get("verification_withheld"):
        why = (f"{gate} passed in {d['verification_withheld']}, but its evidence or the cited failure's does not match "
               "the signed ledger, so the verification cannot be determined (run `vmodel audit`)")
    elif state == "UNKNOWN":
        why = "the signed ledger failed its integrity check, so the verification cannot be determined"
    elif state == "CLOSED":
        why = f"verified by {vb} and {_now_passed(d)} for the current inputs"
    elif state == "VERIFICATION_FAILED":
        failed_gate = (d.get("last_verification") or {}).get("gate") or gate
        why = (f"{_failed_attempt(d)} after the cited failure, so the fix is not verified"
               + (f" ({prev}; that success no longer stands)" if prev else "")
               + {"unblock": f"; {failed_gate} is BLOCKED after three identical failures until the user unblocks it",
                  "resolve_block": f"; {failed_gate} is now BLOCKED (see the gate's reasons): resolve the block first"
                  }.get(d.get("closure_action"), "; record the failure in a DEFECT, fix and re-verify"))
    elif state == "REVERIFY_REQUIRED" and now == "BLOCKED":
        why = (f"{prev}, but {gate} is now BLOCKED; resolve the block (see the gate's reasons), then re-verify "
               "before treating the defect as closed")
    elif state == "REVERIFY_REQUIRED":
        why = f"{prev}, but {gate} is now {now}; re-verify (re-run {gate}) before treating the defect as closed"
    elif state == "OUT_OF_SCOPE":
        why = (_out_of_scope(d) + ". The removal was justified (CR/DEFECT removed_ids, G2/G3 reviews confirmed N/A); "
               "this is not a verification of the fix")
    elif state == "FIX_APPLIED":
        why = "fix claimed in defects.json (status fixed); no gate has verified it yet"
    else:
        why = "not fixed and not verified yet"
    if d.get("verification_withheld") and state != "UNKNOWN":
        why += f" ({_withheld(d)})"
    out = [f"closure: {state} — {why}"]
    if d.get("claim_note"):
        out.append(f"note: {d['claim_note']}")
    return out


def report_markdown(project: Project, wi: str) -> str:
    st = project_status(project, wi)
    w = st["work_items"][0]
    ctxs, _ = _contexts(project, wi)
    ctx = ctxs[0]
    tv = trace_view(project, wi)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    v = st["validator"]
    md = [f"# {w['id']} — {w['title'] or ''}", "",
          f"- Status: **{w['status']}** (profile {w['profile']})",
          f"- Generated: {now} by vmodel {v['version']} ({v['mode']}, core `{short(v['core_hash'])}`)",
          f"- Validator integrity: {'OK' if v['ok'] else 'FAILED'}; ledger: {'OK' if st['ledger']['ok'] else 'INVALID'}",
          "", f"> {st['mvp_note']}", "", "## Gates", "",
          "| Gate | Name | Status | Record | Evaluated | Manifest |", "|---|---|---|---|---|---|"]
    for g in w["gates"]:
        md.append(f"| {g['gate']} | {g['name']} | {g.get('display_status') or g['status']} | {g.get('record_id', '-')} | "
                  f"{g.get('evaluated_at', '-')} | `{short(g.get('manifest_hash_recorded'))}` |")
    md += ["", f"Gate results: {summary_text(w.get('gate_summary') or {})}"]
    g6 = next((g for g in w["gates"] if g["gate"] == "G6"), {})
    if g6.get("display_status") == "N/A":
        md += ["", f"G6 is N/A (recorded PASSED {g6.get('record_id')}): no integration test was executed; "
               f"reason: {g6.get('na_reason')}; external endpoints reviewed: "
               f"{', '.join(g6.get('external_endpoints') or []) or 'none'}. N/A never verifies a defect fix."]
    elif g6.get("not_evaluated"):
        md += ["", "G6 is not evaluated yet: no integration verification has run."]
    for wn in w.get("scope_warnings") or []:
        md += ["", f"Scope warning: {wn}"]
    md += ["", f"Next action: {w['next_action']}", "", "## Checks (latest evaluation per gate)", ""]
    for gate in implemented_gates():
        last = last_eval(ctx.entries, wi, gate)
        if not last:
            continue
        rec = last.record
        md.append(f"### {gate} — {rec['status']} ({last.id})")
        md.append("")
        md.append("Mechanical / execution checks (decided by the validator):")
        md.append("")
        for c in rec["checks"]:
            if c["kind"] == "ai_review":
                continue
            md.append(f"- `{c['id']}` **{c['status']}** — {c['detail']}")
            for it in (c.get("items") or [])[:10]:
                md.append(f"  - {it}")
        reviews = [c for c in rec["checks"] if c["kind"] == "ai_review"]
        if reviews:
            md += ["", "AI review (semantic, not machine-verified):", ""]
            for c in reviews:
                md.append(f"- `{c['id']}` **{c['status']}** — {c['detail']}")
        if rec.get("evidence"):
            md += ["", "Evidence:", ""]
            for e in rec["evidence"]:
                md.append(f"- `{e['path']}` (`{short(e['sha256'])}`)")
        md.append("")
    md += ["## Traceability", "", "| REQ | Type | ARCH | DESIGN | Tests (level:result) |", "|---|---|---|---|---|"]
    for r in tv["rows"]:
        tests = ", ".join(f"{t} ({x['level']}:{x['result']})" for t, x in r["tests"].items()) or "-"
        md.append(f"| {r['req']} {r['title']} | {r['type']} | {', '.join(r['components']) or '-'} | "
                  f"{', '.join(r['design_units']) or '-'} | {tests} |")
    if tv["dangling"]:
        md += ["", "Dangling references:", ""] + [f"- {d}" for d in tv["dangling"]]
    defects = _items(ctx.arts.get("defects.json"), "defects")
    crs = _items(ctx.arts.get("change-requests.json"), "change_requests")
    views = w["defects"]  # the same derivation as `vmodel status`
    md += ["", "## Defects", ""]
    if not defects:
        md.append("None recorded.")
    for d, dt in zip(defects, views):
        md.append(f"- {d.get('id')} [{d.get('status')} — {report_closure(dt)}] {d.get('gate')} "
                  f"{str(d.get('description', ''))[:200]} "
                  f"(root cause {d.get('root_cause_phase')}: {str(d.get('root_cause', ''))[:200]})")
        md += [f"  - {ln}" for ln in report_closure_details(dt)]
        for c in dt.get("citations") or []:
            if not c.get("valid"):
                continue
            if c["test_results"] == "not_applicable":
                tests = f"N/A ({c['gate']} does not run tests)"
            else:
                tests = ", ".join(c["failing_tests"]) or "none"
                if c["test_results"] in ("unknown", "partial"):
                    tests += (f"; UNKNOWN (not executed or not recorded): "
                              f"{', '.join(c['unknown_tests']) or 'no per-TEST results recorded'}")
            md.append(f"  - failing tests in {c['record']} (from the signed ledger): {tests}")
    md += ["", "## Defect trace check", "",
           "Evidence errors (ERROR) and traceability warnings (WARNING) derived from the signed ledger. "
           "`vmodel lint` exits 1 while any remain; gate decisions do not depend on them.", ""]
    problems = [p for dt in views for p in [*(dt.get("errors") or []), *(dt.get("warnings") or [])]]
    if not problems:
        md.append(f"None ({len(views)} defect(s) checked).")
    md += [f"- {render_problem(p)}" for p in problems]
    md += ["", "## Change requests", ""]
    if not crs:
        md.append("None recorded.")
    for c in crs:
        affected = [x for x in c.get("affected") or [] if isinstance(x, str)] if isinstance(c.get("affected"), list) else []
        md.append(f"- {c.get('id')} [{c.get('status')}] {str(c.get('description', ''))[:200]} — affects "
                  f"{', '.join(affected)}")
    md += ["", "## Limitations", "",
           "- AI review checks record that the vmodel:verifier approved the exact input hash; the semantic correctness "
           "of requirements and designs is not machine-verified.",
           "- Hooks and permission rules are best-effort protection, not OS-level isolation; the final trust boundary "
           "is a re-verification on CI or by a separate user (`vmodel audit`, `vmodel verify`).",
           "- G6 judges interface coverage from a static call analysis (Python, an approximation) or, for declared "
           "runtime paths, a runtime trace written inside the processes under test (same trust limit as the test "
           "runner); whether a test really exercises the interface's meaning is the G4 review's judgement.",
           "- G7, LITE and STRICT profiles are not implemented in this DevKit version."]
    return "\n".join(md) + "\n"

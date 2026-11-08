"""Derived status, traceability views, impact analysis and Markdown reports."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .gates import (GATE_ORDER, Ctx, _items, build_ctx, defect_trace, gate_def, gate_state, gates_def,
                    implemented_gates, integrity_for, last_eval, last_with_status)
from .hashing import short
from .integrity import IntegrityReport
from .ledger import Ledger, LedgerError
from .project import Project
from .runner import check_evidence
from .trace import item_hashes

MVP_NOTE = ("MVP scope: only G1-G5 are implemented. G6 (integration) and G7 (system) are extension gates, "
            "so a work item can reach PARTIALLY_VERIFIED at most. This is NOT a full V-Model completion.")


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


def next_action(wi: str, gates: list[dict]) -> str:
    for g in gates:
        s = g["status"]
        gid = g["gate"]
        if s == "PASSED":
            continue
        if s == "NOT_IMPLEMENTED":
            return f"G1-G5 verified. {gid}+ are extension gates (not implemented); report PARTIALLY_VERIFIED."
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
        item = {"id": ctx.wi, "title": wi_doc.get("title"), "profile": profile,
                "status": wi_status(gates, profile), "gates": gates, "next_action": next_action(ctx.wi, gates),
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
    unsure = [c for c in valid if c["test_results"] in ("unknown", "partial")]
    text = f"failing tests (ledger): {', '.join(d['failing_tests']) or ('none confirmed' if unsure else 'none')}"
    if unsure:
        unknown = sorted({t for c in unsure for t in c["unknown_tests"]})
        text += f"; UNKNOWN: {', '.join(unknown) or 'no per-TEST results recorded'}"
    return text


def closure_text(d: dict) -> str:
    if d["verified_by"]:
        return f"verified by {d['verified_by']}"
    if d.get("verification_withheld"):
        return f"not verified: {d['verification_withheld']} withheld (evidence integrity error)"
    return "not verified yet"


def render_defect(d: dict) -> list[str]:
    lines = [f"{d['id']} [{d['claimed_status']}; {closure_text(d)}] {d['gate']} root cause {d['root_cause_phase']}; "
             f"{tests_summary(d)}"]
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
        for g in w["gates"]:
            extra = ""
            if g.get("record_id"):
                extra = f" {g['record_id']} @ {g.get('evaluated_at', '')}"
            lines.append(f"  {g['gate']} {g['name']:<32} {g['status']:<16}{extra}")
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
    executed = (last_g5.record.get("executed_tests") if last_g5 else None) or {}
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
    return {"work_item": wi, "rows": rows, "reverse": reverse, "dangling": g.dangling(),
            "results_from": last_g5.id if last_g5 else None}


def render_trace(tv: dict) -> str:
    lines = [f"Traceability {tv['work_item']} (results from {tv['results_from'] or 'no G5 run'})"]
    for r in tv["rows"]:
        lines.append(f"{r['req']} [{r['type']}/{r['status']}] {r['title']}")
        lines.append(f"   AC: {', '.join(r['acceptance_criteria']) or '-'}")
        lines.append(f"   ARCH: {', '.join(r['components']) or '-'}   DESIGN: {', '.join(r['design_units']) or '-'}")
        lines.append(f"   CODE: {', '.join(r['symbols']) or '-'}")
        tests = [f"{t}({v['level']}:{v['result']})" for t, v in r["tests"].items()]
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
    return closure_text(d)


def report_closure_details(d: dict) -> list[str]:
    return []


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
        md.append(f"| {g['gate']} | {g['name']} | {g['status']} | {g.get('record_id', '-')} | "
                  f"{g.get('evaluated_at', '-')} | `{short(g.get('manifest_hash_recorded'))}` |")
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
           "- G6/G7, LITE and STRICT profiles are not implemented in this DevKit version."]
    return "\n".join(md) + "\n"

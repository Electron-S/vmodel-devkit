"""vmodel command line interface.

Exit codes: 0 OK/PASSED, 1 FAILED, 2 usage or internal error, 3 BLOCKED, 4 REVIEW_REQUIRED.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import VERSION
from .gates import (GATE_ORDER, ID_KINDS, hash_for_review, implemented_gates, open_context, run_gate)
from .hashing import sha256_file, short
from .integrity import check_self, plugin_root
from .ledger import Ledger, LedgerError
from .project import Project, ProjectError
from .runner import check_evidence, utc_now
from .schema_lite import validate
from .setup_project import (SetupError, env_summary, init_project, install_claude, new_work_item, next_id,
                            repin_lock, uninstall)
from .status import (impact_view, project_status, render_impact, render_problem, render_status, render_trace,
                     report_markdown, trace_view)
from .textio import ArtifactError, load_json, read_stdin_bytes, read_text, setup_stdio, write_text

EXIT = {"PASSED": 0, "FAILED": 1, "BLOCKED": 3, "REVIEW_REQUIRED": 4}
MARK = {"pass": "pass", "warn": "WARN", "pending": "PENDING", "fail": "FAIL", "blocked": "BLOCKED", "skip": "skip"}


def out(text: str = "") -> None:
    print(text)


def _project(args) -> Project:
    if getattr(args, "project", None):
        return Project.find(Path(args.project))
    return Project.find()


def _json(obj) -> None:
    out(json.dumps(obj, indent=2, ensure_ascii=False))


def render_gate(res: dict) -> str:
    lines = [f"{res['work_item']} {res['gate']} {res['status']}"
             + (f"  record {res['record_id']}  manifest {short(res.get('manifest_hash'))}" if res.get("recorded")
                else "  (not recorded: precondition)")]
    for r in res.get("reasons") or []:
        lines.append(f"  ! {r}")
    for c in res.get("checks") or []:
        lines.append(f"  [{MARK.get(c['status'], c['status']):<7}] {c['id']:<28} {c['detail']}")
        for it in (c.get("items") or [])[:15]:
            lines.append(f"            - {it}")
        if len(c.get("items") or []) > 15:
            lines.append(f"            ... {len(c['items']) - 15} more")
        if c["kind"] == "ai_review" and c["status"] == "pending" and c.get("data", {}).get("target_hash_expected"):
            lines.append(f"            target_hash for the reviewer: {c['data']['target_hash_expected']}")
    if res.get("review_required_by"):
        lines.append(f"  review required by: {', '.join(res['review_required_by'])}")
    if res.get("blocked_reason"):
        lines.append(f"  blocked reason: {res['blocked_reason']}")
    for e in res.get("evidence") or []:
        lines.append(f"  evidence: {e['path']} ({short(e['sha256'])})")
    return "\n".join(lines)


def _require_tty(action: str) -> bool:
    if not (sys.stdin is not None and sys.stdin.isatty() and sys.stdout.isatty()):
        out(f"'{action}' is a user-only action and needs an interactive terminal (TTY). "
            "Run it yourself in a terminal; an agent cannot perform it.")
        return False
    try:
        ans = input(f"Type 'yes' to {action}: ")
    except EOFError:
        return False
    return ans.strip() == "yes"


# ---------------------------------------------------------------- commands
def cmd_init(args) -> int:
    root = Path(args.project or ".")
    res = init_project(root, python=args.python, source=args.source, tests=args.tests, lint=args.lint,
                       allow_syntax_only=args.allow_syntax_only)
    cfg = res["config"]
    out(f"initialised {res['project']}")
    out(f"  python: {cfg['python']}")
    lint = cfg["static_analysis"]["lint"]
    out(f"  lint: {lint['name'] if lint else 'none'} (on_missing_lint={cfg['static_analysis']['on_missing_lint']})")
    out(f"  validator {res['lock']['validator_version']} core {short(res['lock']['core_hash'])} pinned")
    out(f"  signing key: {res['key']}")
    return 0


def cmd_install(args) -> int:
    root = Path(args.project or ".").resolve()
    if not (root / ".vmodel" / "config.json").exists():
        cmd_init(args)
    res = install_claude(root, claude_md_import=args.claude_md_import,
                         enable_plugin=Path(args.enable_plugin) if args.enable_plugin else None)
    out(f"installed into {root}")
    out(f"  deny rules added to .claude/settings.json: {len(res['added_deny'])}")
    out(f"  allow rules added for the validator CLI: {len(res['added_allow'])}")
    if res["settings_backup"]:
        out(f"  backup of previous settings: {res['settings_backup']}")
    out(f"  CLAUDE.md: {res['claude_md'] or 'untouched (instructions come from the SessionStart hook)'}")
    for c in res["conflicts"]:
        out(f"  CONFLICT: {c}")
    out("  register the plugin (touches ~/.claude/plugins, so it is up to you):")
    for c in res["register_commands"]:
        out(f"    {c}")
    return 0


def cmd_uninstall(args) -> int:
    if args.purge and not _require_tty("delete .vmodel/, its signing key and ledger anchor (all VModel history)"):
        return 3
    res = uninstall(Path(args.project or "."), purge=args.purge)
    for d in res["done"] or ["nothing to do"]:
        out(d)
    return 0


def cmd_new_wi(args) -> int:
    p = _project(args)
    request = args.request
    if args.request_file:
        request = read_text(Path(args.request_file))
    if not request:
        out("--request or --request-file is required")
        return 2
    doc = new_work_item(p, args.title, request, args.profile)
    if args.json:
        _json(doc)
    else:
        out(doc["id"])
    return 0


def cmd_next_id(args) -> int:
    p = _project(args)
    for i in next_id(p, args.kind, args.count):
        out(i)
    return 0


def cmd_lint(args) -> int:
    from .gates import TraceGraph, _items, defect_trace, load_artifacts, load_schema
    from .project import SCHEMA_FOR

    p = _project(args)
    p.wi_dir(args.wi)
    arts, errors = load_artifacts(p, args.wi)
    problems = []
    for name, err in errors.items():
        if err != "missing":
            problems.append(err)
    for name, data in arts.items():
        problems += [f"{name} {e}" for e in validate(data, load_schema(SCHEMA_FOR[name]))]
    rv_dir = p.wi_dir(args.wi) / "reviews"
    for rv in sorted(rv_dir.glob("G*.json")) if rv_dir.is_dir() else []:
        try:
            problems += [f"reviews/{rv.name} {e}" for e in validate(load_json(rv), load_schema("review"))]
        except ArtifactError as exc:
            problems.append(str(exc))
    problems += [f"trace: {d}" for d in TraceGraph.build(arts).dangling()]
    lines = [f"ERROR {pr}" for pr in problems]  # schema, encoding and trace problems are errors
    n_err, n_warn = len(problems), 0
    defects = _items(arts.get("defects.json"), "defects")
    if defects:  # rework records are checked against what the signed ledger says actually failed
        ledger = Ledger(p)
        ledger_error = None
        try:
            entries = ledger.entries()
        except (LedgerError, ArtifactError, ProjectError) as exc:
            ledger_error = str(exc)
            entries = []

        def check(path: str, sha: str | None) -> list[str]:
            try:
                return check_evidence(p, ledger, path, sha)
            except LedgerError as exc:
                return [f"{path}: {exc}"]

        for d in defect_trace(entries, args.wi, defects, evidence_check=check, ledger_error=ledger_error):
            n_err += len(d["errors"])
            n_warn += len(d["warnings"])
            lines += [render_problem(pr) for pr in [*d["errors"], *d["warnings"]]]
    present = sorted(arts)
    out(f"{args.wi}: {len(present)} artifact(s) present: {', '.join(present)}")
    for ln in lines:
        out(f"  - {ln}")
    # Exit code policy unchanged: any error or warning -> 1 (the labels tell them apart).
    out("lint OK (not a gate decision)" if not lines else
        f"{len(lines)} problem(s): {n_err} error(s), {n_warn} warning(s) (not a gate decision)")
    return 0 if not lines else 1


def cmd_hash(args) -> int:
    p = _project(args)
    res = hash_for_review(p, args.wi, args.gate)
    if args.json:
        _json(res)
    else:
        out(res["target_hash"])
    return 0


def cmd_gate(args) -> int:
    p = _project(args)
    r = run_gate(p, args.wi, args.gate)
    d = r.as_dict()
    if args.json:
        _json(d)
    else:
        out(render_gate(d))
    return EXIT.get(r.status, 2)


def cmd_verify(args) -> int:
    """Fresh full re-verification of all implemented gates (stored results are not reused)."""
    p = _project(args)
    gates = [args.gate] if args.gate else implemented_gates()
    results = []
    final = "PASSED"
    for g in gates:
        r = run_gate(p, args.wi, g)
        results.append(r.as_dict())
        if not args.json:
            out(render_gate(r.as_dict()))
            out("")
        if r.status != "PASSED":
            final = r.status
            break
    st = project_status(p, args.wi)["work_items"][0]
    if args.json:
        _json({"results": results, "work_item_status": st["status"], "next_action": st["next_action"]})
    else:
        out(f"{args.wi} work item status: {st['status']}")
        out(f"next: {st['next_action']}")
    return EXIT.get(final, 2)


def cmd_status(args) -> int:
    p = _project(args)
    st = project_status(p, args.wi)
    if args.json:
        _json(st)
    else:
        out(render_status(st))
    return 0 if st["validator"]["ok"] and st["ledger"]["ok"] else 3


def cmd_trace(args) -> int:
    p = _project(args)
    tv = trace_view(p, args.wi)
    _json(tv) if args.json else out(render_trace(tv))
    return 0 if not tv["dangling"] else 1


def cmd_impact(args) -> int:
    p = _project(args)
    iv = impact_view(p, args.wi)
    _json(iv) if args.json else out(render_impact(iv))
    return 0


def cmd_report(args) -> int:
    p = _project(args)
    md = report_markdown(p, args.wi)
    path = p.reports_dir / f"{args.wi}.md"
    write_text(path, md)
    if args.stdout:
        out(md)
    out(f"report written: {p.rel(path)}")
    return 0


def _check_evidence(p: Project, ledger: Ledger, rel: str, expected_sha: str | None) -> list[str]:
    return check_evidence(p, ledger, rel, expected_sha)


def cmd_audit(args) -> int:
    p = _project(args)
    problems = []
    integ = check_self()
    problems += [f"integrity: {x}" for x in integ.problems]
    try:
        lock = p.lock()
        if lock.get("core_hash") != integ.core_hash:
            problems.append("integrity: running core hash differs from devkit.lock.json")
    except ArtifactError as exc:
        problems.append(str(exc))
    ledger = Ledger(p)
    n_ev = 0
    try:
        entries = ledger.entries()
        for e in entries:
            for ev in e.record.get("evidence") or []:
                n_ev += 1
                problems += _check_evidence(p, ledger, ev["path"], ev.get("sha256"))
    except LedgerError as exc:
        problems.append(f"ledger: {exc}")
        entries = []
    referenced = {ev["path"] for e in entries for ev in e.record.get("evidence") or []}
    for rec in sorted(p.evidence_dir.rglob("record.json")) if p.evidence_dir.is_dir() else []:
        if p.rel(rec) not in referenced:
            problems.append(f"{p.rel(rec)}: evidence not referenced by the ledger (ignored for gate decisions)")
    out(f"audit: validator {integ.version} {integ.mode} core {short(integ.core_hash)}; "
        f"{len(entries)} ledger entries; {n_ev} evidence record(s) checked")
    for pr in problems:
        out(f"  ! {pr}")
    out("audit OK" if not problems else f"audit FAILED ({len(problems)} problem(s))")
    return 0 if not problems else 1


def cmd_verify_evidence(args) -> int:
    p = _project(args)
    ledger = Ledger(p)
    rel = p.rel(Path(args.path).resolve())
    problems = _check_evidence(p, ledger, rel, None)
    try:
        refs = {ev["path"]: ev["sha256"] for e in ledger.entries() for ev in e.record.get("evidence") or []}
    except LedgerError as exc:
        refs = {}
        problems.append(f"ledger: {exc}")
    if rel not in refs:
        problems.append(f"{rel}: not referenced by the signed ledger -> not evidence")
    elif refs[rel] != sha256_file(p.root / rel):
        problems.append(f"{rel}: differs from the hash recorded in the ledger")
    for pr in problems:
        out(f"  ! {pr}")
    out("evidence OK" if not problems else "evidence REJECTED")
    return 0 if not problems else 1


def cmd_review_submit(args) -> int:
    """Register a verifier review in the signed ledger. The guard hook allows this only for vmodel:verifier."""
    from .gates import REVIEWER, load_schema

    p = _project(args)
    path = p.wi_dir(args.wi) / "reviews" / f"{args.gate}.json"
    rv = load_json(path, f"reviews/{args.gate}.json")
    errs = validate(rv, load_schema("review"))
    if errs:
        out("review invalid: " + "; ".join(errs[:10]))
        return 1
    current = hash_for_review(p, args.wi, args.gate)["target_hash"]
    if rv["gate"] != args.gate or rv["work_item"] != args.wi or rv["reviewer"] != REVIEWER:
        out(f"review must be for {args.wi}/{args.gate} with reviewer {REVIEWER}")
        return 1
    if rv["target_hash"] != current:
        out(f"review targets {rv['target_hash']} but the current inputs hash to {current}; review again")
        return 1
    entry = Ledger(p).append({"type": "review", "work_item": args.wi, "gate": args.gate,
                              "review_sha256": sha256_file(path), "target_hash": rv["target_hash"],
                              "verdict": rv["verdict"], "submitted_at": utc_now(),
                              "attested_by": "guard hook: vmodel:verifier only"})
    out(f"review submitted: {args.wi} {args.gate} {rv['verdict']} ({entry.id})")
    return 0


def cmd_unblock(args) -> int:
    p = _project(args)
    if not _require_tty(f"unblock {args.wi} {args.gate}"):
        return 3
    Ledger(p).append({"type": "unblock", "work_item": args.wi, "gate": args.gate, "reason": args.reason,
                      "by": "user (tty)", "at": utc_now()})
    out(f"{args.wi} {args.gate} unblocked; a DEFECT referencing the blocked record is still required before re-evaluation")
    return 0


def cmd_lock(args) -> int:
    p = _project(args)
    if not args.accept_current:
        _json(p.lock())
        return 0
    if not _require_tty("re-pin the validator core hash (all previous PASS results become STALE)"):
        return 3
    lock = repin_lock(p, args.reason or "user re-pinned validator")
    out(f"re-pinned core {short(lock['core_hash'])} (validator {lock['validator_version']})")
    return 0


def cmd_hook(args) -> int:
    from .hook import run_hook

    code, text = run_hook(args.kind, read_stdin_bytes())
    if text:
        out(text)
    return code


GUIDES = {
    "artifacts": "skills/start/ARTIFACTS.md",
    "requirements": "agents/requirements-analyst.md",
    "architecture": "agents/architect.md",
    "design": "agents/detailed-designer.md",
    "tests": "agents/test-designer.md",
    "implementation": "agents/implementer.md",
    "review": "agents/verifier.md",
}


def cmd_guide(args) -> int:
    """Print plugin guidance through Bash, so no file outside the project has to be read with the Read tool."""
    rel = GUIDES[args.topic]
    text = read_text(plugin_root() / rel, rel)
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            text = text[end + 4:].lstrip("\n")
    out(text.replace("${CLAUDE_PLUGIN_ROOT}", str(plugin_root())))
    return 0


def cmd_version(args) -> int:
    integ = check_self()
    _json({"version": VERSION, "core_hash": integ.core_hash, "mode": integ.mode, "integrity_ok": integ.ok,
           "problems": integ.problems, **env_summary()})
    return 0 if integ.ok else 3


# ---------------------------------------------------------------- parser
def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="vmodel", description="VModel DevKit independent quality gate validator")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add(name, fn, help_):
        sp = sub.add_parser(name, help=help_)
        sp.add_argument("--project", help="project root (default: search upwards from cwd)")
        sp.set_defaults(fn=fn)
        return sp

    sp = add("init", cmd_init, "create .vmodel/ in a project (config, lock, signing key)")
    for s in (sp, add("install", cmd_install, "init (if needed) + merge Claude project settings")):
        s.add_argument("--python")
        s.add_argument("--source", nargs="+")
        s.add_argument("--tests", nargs="+")
        s.add_argument("--lint", choices=["auto", "ruff", "pyflakes", "none"], default="auto")
        s.add_argument("--allow-syntax-only", action="store_true",
                       help="user decision: if no linter is available, accept syntax-only static analysis")
    inst = sub.choices["install"]
    inst.add_argument("--claude-md-import", action="store_true")
    inst.add_argument("--enable-plugin", metavar="MARKETPLACE_DIR")
    sp = add("uninstall", cmd_uninstall, "remove what install added")
    sp.add_argument("--purge", action="store_true", help="also delete .vmodel/ and the signing key")
    sp = add("new-wi", cmd_new_wi, "create a work item")
    sp.add_argument("--title", required=True)
    sp.add_argument("--request")
    sp.add_argument("--request-file")
    sp.add_argument("--profile", default="STANDARD", choices=["LITE", "STANDARD", "STRICT"])
    sp.add_argument("--json", action="store_true")
    sp = add("next-id", cmd_next_id, "next free project-unique id")
    sp.add_argument("kind", choices=ID_KINDS)
    sp.add_argument("--count", type=int, default=1)
    sp = add("lint", cmd_lint, "schema/trace check of artifacts (not a gate decision, not recorded)")
    sp.add_argument("wi")
    sp = add("hash", cmd_hash, "input manifest hash a reviewer must put in target_hash")
    sp.add_argument("wi")
    sp.add_argument("gate", choices=GATE_ORDER)
    sp.add_argument("--json", action="store_true")
    for name, fn, h in (("gate", cmd_gate, "evaluate one gate and record the result"),):
        sp = add(name, fn, h)
        sp.add_argument("wi")
        sp.add_argument("gate", choices=GATE_ORDER)
        sp.add_argument("--json", action="store_true")
    sp = add("verify", cmd_verify, "fresh re-evaluation of G1..G5 in order (stops at the first non-PASS)")
    sp.add_argument("wi")
    sp.add_argument("gate", nargs="?", choices=GATE_ORDER)
    sp.add_argument("--json", action="store_true")
    sp = add("status", cmd_status, "derived gate/work item status")
    sp.add_argument("wi", nargs="?")
    sp.add_argument("--json", action="store_true")
    for name, fn, h in (("trace", cmd_trace, "traceability matrix"), ("impact", cmd_impact, "change impact")):
        sp = add(name, fn, h)
        sp.add_argument("wi")
        sp.add_argument("--json", action="store_true")
    sp = add("report", cmd_report, "write .vmodel/reports/<WI>.md")
    sp.add_argument("wi")
    sp.add_argument("--stdout", action="store_true")
    add("audit", cmd_audit, "verify validator integrity, ledger and all evidence")
    sp = add("verify-evidence", cmd_verify_evidence, "check one evidence record")
    sp.add_argument("path")
    sp = add("review-submit", cmd_review_submit, "VERIFIER ONLY: register reviews/<G>.json in the signed ledger")
    sp.add_argument("wi")
    sp.add_argument("gate", choices=["G1", "G2", "G3", "G4"])
    sp = add("unblock", cmd_unblock, "USER ONLY (TTY): resume a gate blocked after 3 identical failures")
    sp.add_argument("wi")
    sp.add_argument("gate", choices=GATE_ORDER)
    sp.add_argument("--reason", required=True)
    sp = add("lock", cmd_lock, "show the lock; --accept-current re-pins (USER ONLY, TTY)")
    sp.add_argument("--accept-current", action="store_true")
    sp.add_argument("--reason")
    sp = add("hook", cmd_hook, "Claude Code hook entry (reads JSON on stdin)")
    sp.add_argument("kind", choices=["guard", "session-start"])
    add("version", cmd_version, "validator version, core hash and integrity")
    sp = add("guide", cmd_guide, "print artifact formats or a role guide (artifacts, requirements, architecture, ...)")
    sp.add_argument("topic", choices=sorted(GUIDES))
    return ap


def main(argv: list[str] | None = None) -> int:
    setup_stdio()
    args = build_parser().parse_args(argv)
    try:
        return args.fn(args)
    except (ProjectError, SetupError, ArtifactError, LedgerError) as exc:
        out(f"vmodel: error: {exc}")
        return 3 if isinstance(exc, LedgerError) else 2
    except KeyboardInterrupt:
        return 2
    except Exception as exc:  # never let an internal error look like a gate FAILED (exit 1)
        import traceback

        out(f"vmodel: internal error (no gate result recorded): {exc.__class__.__name__}: {exc}")
        out(traceback.format_exc(limit=8))
        return 2

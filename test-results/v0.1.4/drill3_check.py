"""Validator/audit check of v0.1.4 on the real drill-3 ledger (signed by 0.1.3). No model calls.

    python3 -I drill3_check.py <drill-3 dir> <work dir> <old release dir> <new release dir> <out.json>

The drill-3 project and its VMODEL_HOME (signing key, anchor) are COPIED to <work dir>; the original is only read and
its digest is compared before/after. The anchor is copied under the copy's anchor name, so rollback detection stays on.
Steps: 0.1.3 baseline (status, audit) -> new core blocked until the user re-pins (pty, like a terminal) -> audit and
verify-evidence of every 0.1.3 evidence record -> status (old PASSes STALE, defect VERIFIED) -> re-verify G1-G5 with
the new core -> CLOSED -> P-F1 (status edited after the pass) -> P-F2 (failing tests unlinked) -> restore -> audit.
"""
from __future__ import annotations

import hashlib
import json
import os
import pty
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT = "한글 드릴 프로젝트"
drill, work, old_rel, new_rel, out_path = (Path(a).resolve() for a in sys.argv[1:6])


def digest(root: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        if p.is_file() and not p.is_symlink():
            h.update(p.relative_to(root).as_posix().encode("utf-8") + b"\0" + p.read_bytes() + b"\0")
    return h.hexdigest()


def anchor_name(root: Path) -> str:
    norm = os.path.normcase(os.path.realpath(str(root)))
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:32] + ".json"


src_proj, src_home = drill / PROJECT, drill / "vmodel-home"
before = {"project": digest(src_proj), "home": digest(src_home)}
if work.exists():
    shutil.rmtree(work)
work.mkdir(parents=True)
proj, home = work / PROJECT, work / "vmodel-home"
shutil.copytree(src_proj, proj, symlinks=True)
shutil.copytree(src_home, home, symlinks=True)
src_anchor = home / "anchors" / anchor_name(src_proj)
anchor_copied = src_anchor.is_file()
if anchor_copied:
    shutil.copy2(src_anchor, home / "anchors" / anchor_name(proj))
env = {**os.environ, "VMODEL_HOME": str(home)}
env.pop("CLAUDE_PROJECT_DIR", None)
defects_p = proj / ".vmodel/work-items/WI-001/defects.json"
ledger_p = proj / ".vmodel/state/ledger.jsonl"


def vm(rel: Path, *args: str) -> tuple[int, str]:
    r = subprocess.run([sys.executable, "-I", "-B", str(rel / "validator" / "vmodel.py"), *args], cwd=proj, env=env,
                       capture_output=True, stdin=subprocess.DEVNULL, timeout=900)
    return r.returncode, r.stdout.decode("utf-8", "replace") + r.stderr.decode("utf-8", "replace")


def tty(rel: Path, *args: str) -> str:
    pid, fd = pty.fork()
    if pid == 0:
        os.chdir(proj)
        os.execve(sys.executable, [sys.executable, "-I", "-B", str(rel / "validator" / "vmodel.py"), *args], env)
    os.write(fd, b"yes\n")
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
    return buf.decode("utf-8", "replace")


def snap(rel: Path) -> dict:
    st = json.loads(vm(rel, "status", "WI-001", "--json")[1])
    w = st["work_items"][0]
    keep = ("id", "claimed_status", "closure_state", "closure_gate", "closure_gate_status", "verified_by",
            "verification_withheld", "claim_note", "failing_tests", "unlinked_failing_tests", "errors", "warnings")
    return {"validator": {k: st["validator"][k] for k in ("version", "mode", "core_hash", "ok")},
            "wi": w["status"], "defect_checks": w.get("defect_checks"),
            "gates": {g["gate"]: g["status"] for g in w["gates"] if g["status"] != "NOT_IMPLEMENTED"},
            "stale_notes": sorted({n for g in w["gates"] for n in g.get("notes") or [] if "core" in n}),
            "defects": [{k: d.get(k) for k in keep if k in d} for d in w["defects"]]}


def defect_lines(rel: Path) -> list[str]:
    text = vm(rel, "status", "WI-001")[1]
    return [ln.strip() for ln in text.splitlines()
            if ln.strip().startswith(("WI-001 ", "DEFECT-", "ERROR", "WARNING", "note:"))]


res: dict = {"inputs": {"drill": str(drill), "work": str(work), "old_release": str(old_rel), "new_release": str(new_rel),
                        "anchor_copied": anchor_copied}}
ledger0 = ledger_p.read_bytes()
records0 = [json.loads(ln)["record"] for ln in ledger0.decode("utf-8").splitlines()]
evidence = sorted({e["path"] for r in records0 for e in r.get("evidence") or []})
res["old_baseline"] = {"status": snap(old_rel), "lines": defect_lines(old_rel), "audit_exit": vm(old_rel, "audit")[0],
                       "ledger_entries": len(records0), "evidence_records": len(evidence)}
res["new_before_repin"] = {"validator_ok": snap(new_rel)["validator"]["ok"],
                           "gates": snap(new_rel)["gates"]}
res["repin"] = [ln for ln in tty(new_rel, "lock", "--accept-current", "--reason", "upgrade to 0.1.4 (drill-3 copy)")
                .splitlines() if "re-pinned" in ln]
code, text = vm(new_rel, "audit")
res["audit_after_repin"] = {"exit": code, "summary": [ln for ln in text.splitlines() if ln.startswith(("audit", "  !"))]}
res["verify_evidence"] = {p: vm(new_rel, "verify-evidence", str(proj / p))[0] for p in evidence}
res["new_after_repin"] = {"status": snap(new_rel), "lines": defect_lines(new_rel)}
code, text = vm(new_rel, "lint", "WI-001")
res["new_after_repin"]["lint"] = {"exit": code, "last": text.strip().splitlines()[-1]}

res["reverify"] = {}
for g in ("G1", "G2", "G3", "G4", "G5"):
    code, text = vm(new_rel, "gate", "WI-001", g, "--json")
    r = json.loads(text)
    res["reverify"][g] = {"status": r["status"], "record": r.get("record_id"), "reasons": r.get("reasons")}
res["after_reverify"] = {"status": snap(new_rel), "lines": defect_lines(new_rel)}
code, text = vm(new_rel, "report", "WI-001")
report = (proj / ".vmodel/reports/WI-001.md").read_text(encoding="utf-8")
res["after_reverify"]["report_defects"] = report[report.index("## Defects"):report.index("## Change requests")]

original = defects_p.read_bytes()
try:
    doc = json.loads(original.decode("utf-8"))
    doc["defects"][0]["status"] = "open"
    defects_p.write_text(json.dumps(doc, ensure_ascii=False, indent=1), "utf-8")
    res["P-F1_status_edited_after_pass"] = {"status": snap(new_rel), "lines": defect_lines(new_rel)}
    defects_p.write_bytes(original)
    doc = json.loads(original.decode("utf-8"))
    doc["defects"][0]["related"] = [r for r in doc["defects"][0]["related"] if r not in ("TEST-011", "TEST-012")]
    defects_p.write_text(json.dumps(doc, ensure_ascii=False, indent=1), "utf-8")
    code, text = vm(new_rel, "lint", "WI-001")
    res["P-F2_unlinked"] = {"status": snap(new_rel), "lines": defect_lines(new_rel), "lint_exit": code,
                            "lint": [ln.strip() for ln in text.splitlines() if "[" in ln or "problem" in ln]}
finally:
    defects_p.write_bytes(original)
res["restored"] = {"status": snap(new_rel), "lines": defect_lines(new_rel)}
code, text = vm(new_rel, "audit")
res["final_audit"] = {"exit": code, "summary": [ln for ln in text.splitlines() if ln.startswith(("audit", "  !"))]}
ledger1 = ledger_p.read_bytes()
added = [json.loads(ln)["record"] for ln in ledger1[len(ledger0):].decode("utf-8").splitlines()]
res["ledger"] = {"old_prefix_unchanged": ledger1.startswith(ledger0), "entries_before": len(records0),
                 "added": [(r.get("type"), r.get("gate"), r.get("status"), (r.get("validator") or {}).get("version"))
                           for r in added],
                 "old_gate_versions": sorted({(r["validator"]["version"], r["validator"]["core_hash"])
                                              for r in records0 if r.get("type") == "gate"})}
after = {"project": digest(src_proj), "home": digest(src_home)}
res["original_untouched"] = before == after
out_path.write_text(json.dumps(res, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
print(json.dumps(res, indent=2, ensure_ascii=False))

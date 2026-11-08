"""Validator-only probes on the finished drill-3 sandbox (no model calls, every change restored byte-for-byte).

    python3 -I probe_f1_f2.py <repo> <drill dir> <release dir>

P-F2: drop TEST-011/TEST-012 from DEFECT-001 `related` -> does the validator (status/lint/report) name exactly those
      two from the signed failure record, and what does it cost (G4/G5 freshness)?
P-F1: flip DEFECT-001 `status` fixed -> open after the pass -> are G4/G5 STALE, does `verified_by` stay ledger-derived?
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

repo, work, release = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
sys.dont_write_bytecode = True
sys.path.insert(0, str(repo / "scripts" / "e2e"))
from rework_drill import PROJECT_DIR, env_for, tree_digest  # noqa: E402

proj = work / PROJECT_DIR
defects_p = proj / ".vmodel" / "work-items" / "WI-001" / "defects.json"
ledger_p = proj / ".vmodel" / "state" / "ledger.jsonl"
env = {**os.environ, **env_for(work)}


def vm(*a: str) -> tuple[int, str]:
    r = subprocess.run(["sh", str(release / "bin" / "vmodel"), *a], cwd=proj, env=env, capture_output=True)
    return r.returncode, r.stdout.decode("utf-8", "replace") + r.stderr.decode("utf-8", "replace")


def snapshot() -> dict:
    st = json.loads(vm("status", "WI-001", "--json")[1])["work_items"][0]
    return {"wi": st["status"], "gates": {g["gate"]: g["status"] for g in st["gates"] if g["gate"] in ("G4", "G5")},
            "defects": st["defects"]}


original = defects_p.read_bytes()
before = {"digest": tree_digest(proj), "ledger_lines": len(ledger_p.read_text("utf-8").splitlines())}
results = []
try:
    doc = json.loads(original.decode("utf-8"))
    doc["defects"][0]["related"] = [r for r in doc["defects"][0]["related"] if r not in ("TEST-011", "TEST-012")]
    defects_p.write_text(json.dumps(doc, ensure_ascii=False, indent=1), "utf-8")
    lint_code, lint_out = vm("lint", "WI-001")
    st_txt = vm("status", "WI-001")[1]
    results.append({"probe": "P-F2 unlinked failing tests", "snapshot": snapshot(), "lint_exit": lint_code,
                    "lint": [ln for ln in lint_out.splitlines() if "rework" in ln or "lint" in ln],
                    "status_defect_line": [ln.strip() for ln in st_txt.splitlines() if "DEFECT-001" in ln]})
    defects_p.write_bytes(original)

    doc = json.loads(original.decode("utf-8"))
    doc["defects"][0]["status"] = "open"
    defects_p.write_text(json.dumps(doc, ensure_ascii=False, indent=1), "utf-8")
    st_txt = vm("status", "WI-001")[1]
    results.append({"probe": "P-F1 status edited after the pass", "snapshot": snapshot(),
                    "status_lines": [ln.strip() for ln in st_txt.splitlines()
                                     if any(k in ln for k in ("G4 ", "G5 ", "changed", "DEFECT-001", "next:"))]})
finally:
    defects_p.write_bytes(original)

after = {"digest": tree_digest(proj), "ledger_lines": len(ledger_p.read_text("utf-8").splitlines())}
out = {"before": before, "after": after, "restored": before == after, "final": snapshot(), "results": results}
(work / "probe-f1-f2.json").write_text(json.dumps(out, indent=2, ensure_ascii=False), "utf-8")
sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
print(json.dumps(out, indent=2, ensure_ascii=False))

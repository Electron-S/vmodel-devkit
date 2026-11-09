"""v0.1.5 release confirmation: which reviews survive an upgrade (no model calls).

    python3 -I test-results/v0.1.5/upgrade_review_cost_probe.py <old release> <new release> <out.json>

A project installed by the old release passes G1-G5, is re-pinned to the new release by the user (pty), and every
gate is re-evaluated WITHOUT writing any new review. Records which gates pass again on the validator alone and
which need a new verifier review, and whether .claude/settings.json (part of the G4/G5 code manifest) changed.
Also checks that the ledger written by the old release is kept byte for byte and `vmodel audit` passes.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tests"))
from helpers import Sandbox  # noqa: E402


def main() -> int:
    old, new, out = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve(), Path(sys.argv[3])
    sb = Sandbox(plugin=old)
    try:
        code, text = sb.vm("install", "--project", str(sb.root), "--lint", "none", "--allow-syntax-only")
        assert code == 0, text
        sb.new_wi()
        sb.advance("G5")
        settings_before = (sb.root / ".claude" / "settings.json").read_bytes()
        ledger_before = (sb.root / ".vmodel" / "state" / "ledger.jsonl").read_bytes()
        sb.plugin, sb.entry = new, new / "validator" / "vmodel.py"
        tty = sb.run_tty("lock", "--accept-current", "--reason", "upgrade", answer=b"yes\n").decode("utf-8", "replace")
        settings_changed = (sb.root / ".claude" / "settings.json").read_bytes() != settings_before
        after_upgrade = {g["gate"]: g["status"] for g in sb.status()["work_items"][0]["gates"]}
        reeval = {}
        for g in ("G1", "G2", "G3", "G4", "G5"):
            code, rec = sb.gate(g)
            checks = {c["id"]: c["status"] for c in rec.get("checks", [])} if isinstance(rec, dict) else {}
            reeval[g] = {"status": rec.get("status") if isinstance(rec, dict) else None,
                         "review_check": checks.get(f"{g}.REVIEW")}
            if reeval[g]["status"] != "PASSED":
                break
        audit_code, audit_out = sb.vm("audit")
        ledger_after = (sb.root / ".vmodel" / "state" / "ledger.jsonl").read_bytes()
        result = {"old": old.name, "new": new.name, "repinned": "re-pinned" in tty,
                  "old_ledger_entries": len(ledger_before.splitlines()),
                  "old_ledger_prefix_kept": ledger_after.startswith(ledger_before),
                  "audit_exit_code_after": audit_code,
                  "settings_changed_by_upgrade": settings_changed, "status_after_upgrade": after_upgrade,
                  "reevaluate_without_new_reviews": reeval}
    finally:
        sb.cleanup()
    out.write_text(json.dumps(result, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

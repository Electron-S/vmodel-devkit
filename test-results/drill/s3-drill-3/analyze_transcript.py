"""Timeline of a rework-drill transcript: tool calls in order, by main session or subagent (no model calls).

    python3 -I analyze_s3.py <drill dir> <phase>

Prints JSON to stdout (UTF-8) so it also works on a cp949 console when redirected.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

work, phase = Path(sys.argv[1]), sys.argv[2]
lines = (work / f"transcript-{phase}.jsonl").read_text("utf-8", errors="replace").splitlines()

calls: list[dict] = []
results: dict[str, dict] = {}
agent_names: dict[str, str] = {}
for line in lines:
    try:
        ev = json.loads(line)
    except json.JSONDecodeError:
        continue
    if ev.get("type") == "assistant":
        for b in (ev.get("message") or {}).get("content") or []:
            if b.get("type") == "tool_use":
                inp = b.get("input") or {}
                if b.get("name") in ("Agent", "Task"):
                    agent_names[b.get("id")] = inp.get("subagent_type", "?")
                calls.append({"id": b.get("id"), "tool": b.get("name"), "parent": ev.get("parent_tool_use_id"),
                              "input": inp})
    elif ev.get("type") == "user":
        for b in (ev.get("message") or {}).get("content") or []:
            if isinstance(b, dict) and b.get("type") == "tool_result":
                c = b.get("content")
                if isinstance(c, list):
                    c = " ".join(x.get("text", "") for x in c if isinstance(x, dict))
                results[b.get("tool_use_id")] = {"is_error": bool(b.get("is_error")), "content": str(c)}


def who(c: dict) -> str:
    return "main" if not c["parent"] else agent_names.get(c["parent"], "sub")


def brief(c: dict) -> str:
    i = c["input"]
    if c["tool"] == "Bash":
        return i.get("command", "")[:260]
    if c["tool"] in ("Read", "Write", "Edit", "MultiEdit"):
        s = i.get("file_path", "")
        if c["tool"] == "Edit":
            s += f" | old={i.get('old_string', '')[:120]!r} new={i.get('new_string', '')[:160]!r}"
        return s
    if c["tool"] in ("Agent", "Task"):
        return f"{i.get('subagent_type')}: {i.get('prompt', '')[:400]}"
    if c["tool"] == "Skill":
        return f"{i.get('skill')} {i.get('args', '')}"
    return json.dumps(i, ensure_ascii=False)[:200]


timeline = []
for n, c in enumerate(calls, 1):
    r = results.get(c["id"]) or {}
    timeline.append({"n": n, "by": who(c), "tool": c["tool"], "what": brief(c), "error": r.get("is_error"),
                     "result": (r.get("content") or "")[:300]})

ledger_reads = [t for t in timeline if "ledger.jsonl" in t["what"] or "head.json" in t["what"]]
evidence_reads = [t for t in timeline if "/evidence/" in t["what"] or ".vmodel/evidence" in t["what"]]
defect_writes = [t for t in timeline if t["tool"] in ("Write", "Edit", "MultiEdit") and "defects.json" in t["what"]]
defect_bash_writes = [t for t in timeline if t["tool"] == "Bash" and "defects.json" in t["what"]
                      and any(k in t["what"] for k in (">", "sed -i", "tee", "python"))]
status_calls = [t for t in timeline if t["tool"] == "Bash" and " status" in t["what"]]
lint_calls = [t for t in timeline if t["tool"] == "Bash" and " lint" in t["what"]]
gate_calls = [t for t in timeline if t["tool"] == "Bash" and " gate " in t["what"]]
review_submits = [t for t in timeline if t["tool"] == "Bash" and "review-submit" in t["what"]]
agents = [t for t in timeline if t["tool"] in ("Agent", "Task")]
pytest_calls = [t for t in timeline if t["tool"] == "Bash" and "pytest" in t["what"]]
denied = [t for t in timeline if t["error"] and ("denied" in t["result"].lower() or "blocked" in t["result"].lower()
                                                  or "guard" in t["result"].lower())]
src_edits = [t for t in timeline if t["tool"] in ("Write", "Edit", "MultiEdit") and "/src/" in t["what"]]
test_edits = [t for t in timeline if t["tool"] in ("Write", "Edit", "MultiEdit") and "/tests/" in t["what"]]

out = {"tool_calls": len(timeline), "timeline": timeline, "ledger_reads": ledger_reads,
       "evidence_reads": evidence_reads, "defect_writes": defect_writes, "defect_bash_writes": defect_bash_writes,
       "status_calls": [t["n"] for t in status_calls], "lint_calls": lint_calls, "gate_calls": gate_calls,
       "review_submits": review_submits, "agents": agents, "pytest_calls": pytest_calls, "denied": denied,
       "src_edits": src_edits, "test_edits": test_edits}
sys.stdout.reconfigure(encoding="utf-8")
print(json.dumps(out, indent=1, ensure_ascii=False))

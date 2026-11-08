"""Run a headless Claude Code session and summarise its stream-json transcript.

Used by the hook probes and the M4 E2E runs. Every run is capped with --max-budget-usd and isolated from the user's
global settings with --setting-sources project,local (DECISIONS D10).
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path


def run_claude(prompt: str, cwd: Path, *, plugin_dirs: list[Path], model: str, budget_usd: float, env: dict,
               transcript: Path, permission_args: list[str] | None = None, timeout_s: int = 3600,
               extra_args: list[str] | None = None) -> dict:
    cmd = ["claude", "-p", prompt, "--model", model, "--max-budget-usd", str(budget_usd),
           "--setting-sources", "project,local", "--output-format", "stream-json", "--verbose",
           "--no-session-persistence"]
    for d in plugin_dirs:
        cmd += ["--plugin-dir", str(d)]
    # Safe default: file edits inside the working directories are accepted, anything that would prompt is denied.
    cmd += permission_args or ["--permission-mode", "acceptEdits", "--permission-prompts", "none"]
    cmd += extra_args or []
    t0 = time.monotonic()
    proc = subprocess.run(cmd, cwd=str(cwd), env={**os.environ, **env}, capture_output=True, timeout=timeout_s,
                          stdin=subprocess.DEVNULL)
    transcript.parent.mkdir(parents=True, exist_ok=True)
    transcript.write_bytes(proc.stdout)
    (transcript.with_suffix(".stderr.txt")).write_bytes(proc.stderr)
    summary = summarise(proc.stdout.decode("utf-8", errors="replace"))
    summary.update({"exit_code": proc.returncode, "wall_s": round(time.monotonic() - t0, 1),
                    "command": [c if c != prompt else "<prompt>" for c in cmd], "transcript": str(transcript)})
    return summary


def summarise(stream: str) -> dict:
    init: dict = {}
    tool_uses: list[dict] = []
    results: dict[str, dict] = {}
    final: dict = {}
    for line in stream.splitlines():
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("type") == "system" and ev.get("subtype") == "init":
            init = {k: ev.get(k) for k in ("model", "slash_commands", "agents", "plugins", "skills", "tools",
                                           "permissionMode")}
        elif ev.get("type") == "assistant":
            for block in (ev.get("message") or {}).get("content") or []:
                if block.get("type") == "tool_use":
                    tool_uses.append({"id": block.get("id"), "name": block.get("name"), "input": block.get("input"),
                                      "parent": ev.get("parent_tool_use_id")})
        elif ev.get("type") == "user":
            for block in (ev.get("message") or {}).get("content") or []:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    content = block.get("content")
                    if isinstance(content, list):
                        content = " ".join(c.get("text", "") for c in content if isinstance(c, dict))
                    results[block.get("tool_use_id")] = {"is_error": bool(block.get("is_error")),
                                                         "content": str(content)[:1500]}
        elif ev.get("type") == "result":
            final = {k: ev.get(k) for k in ("subtype", "is_error", "result", "total_cost_usd", "num_turns",
                                            "duration_ms", "usage")}
    for tu in tool_uses:
        tu["result"] = results.get(tu["id"])
    return {"init": init, "tool_uses": tool_uses, "final": final}

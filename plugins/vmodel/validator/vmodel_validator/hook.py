"""Claude Code hook handlers (PreToolUse guard, SessionStart context).

The guard is registered with "onFailure": "block" so a crash blocks the tool
call instead of letting it through (DECISIONS D05). It is best-effort
protection, not OS isolation (SPEC section 5.7).
"""
from __future__ import annotations

import json
import os
import re
import shlex
from pathlib import Path
from typing import Any

from .integrity import CORE_DIRS, plugin_root
from .project import VMODEL_DIR, vmodel_home

WRITE_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
READ_TOOLS = {"Read"}
SHELL_TOOLS = {"Bash", "PowerShell"}
SHELL_META = re.compile(r"[;&|`<>]|\$\(")
# Commands that write, move or delete (POSIX shell, Git, PowerShell/cmd). fd duplication ("2>&1", ">&2", "2>&-") is
# not a write; "&>file", "&>>file", ">&file", "1>&file" and "x2>&file" (digits ending an ordinary word) are, as bash
# creates the file ("2>&file" is an error).
WRITE_VERBS = re.compile(
    r"(?<![0-9&])>(?!&)|[0-9]>(?!&)|&>|(?<![02-9])>&(?![ \t]*(?:[0-9]+|-)(?=$|[ \t\n;&|)<>]))|"
    r"(?<=[^\s;&|()<>0-9])[0-9]+>&(?![ \t]*(?:[0-9]+|-)(?=$|[ \t\n;&|)<>]))|"
    r"\b(rm|rmdir|mv|cp|touch|tee|truncate|chmod|chown|ln|mkdir|dd|install|patch|"
    r"unlink|shred|rsync|tar|unzip)\b|sed\s+(-[a-zA-Z]*i|--in-place)|python[0-9.]*(\.exe)?\s+-c|\bperl\b|"
    r"\bfind\b[^|;&]*-(delete|exec)|git\s+(clean|checkout|restore|stash|reset|rm|mv|apply|am|switch)\b|"
    r"Remove-Item|Set-Content|Out-File|Add-Content|New-Item|Move-Item|Copy-Item|Clear-Content|Rename-Item|"
    r"(^|[\s;&|(@])(del|erase|rd|ren|move|copy|xcopy|robocopy)(?=[\s,;=/+(]|$)", re.IGNORECASE)
# (D48: cmd.exe also ends a builtin's name at , ; = / + ( - e.g. "del,file" deletes file)
REPO_WIDE_DESTRUCTIVE = re.compile(
    r"git\s+clean\b|\bfind\b[^|;&]*-delete|\brm\s+(-[a-zA-Z]+\s+)*(\.|\./|\*|\./\*|\.\*)(\s|$)", re.IGNORECASE)
USER_ONLY = re.compile(r"vmodel(\.cmd)?[\"']?\s+(init|install|uninstall|unblock|configure-tests)\b|accept-current",
                       re.IGNORECASE)
VERIFIER_WRITE_VERBS = WRITE_VERBS
# Bash redirections that cannot write a file (D36): output to exactly /dev/null, fd duplication or closing, and plain
# input redirection. They are removed before the write checks, so they neither count as writes nor hide a write verb
# from its flag (e.g. "sed >/dev/null 2>&1 -i ..."). A target must end at a bash word break (space, tab, newline,
# ;&|) or the end): '/dev/null"x"', '/dev/null`..`', '/dev/null$X', '/dev/null#c', '/dev/null/..' and '/dev/null\r'
# name other paths, and a quoted "/dev/null" is not recognised, so those stay writes.
NON_WRITING_REDIRECT = re.compile(
    r"(?:&>>?|>&|[0-9]*>>?)[ \t]*/dev/null(?=$|[ \t\n;&|)])"
    r"|[0-9]*[<>]&[ \t]*(?:[0-9]+|-)(?=$|[ \t\n;&|)<>])"
    r"|[0-9]*<(?![<>&(])[ \t]*[^\s;&|()<>'\"`$]+(?=$|[ \t\n;&|)<>])")


def normalize_redirections(cmd: str, tool: str = "Bash") -> str:
    """The command without non-writing redirections (Bash only: PowerShell resolves /dev/null to a real path)."""
    return NON_WRITING_REDIRECT.sub(" ", cmd) if tool == "Bash" else cmd


def shell_writes(cmd: str, tool: str = "Bash") -> bool:
    """True if the command may write, move or delete files."""
    return bool(WRITE_VERBS.search(normalize_redirections(cmd, tool)))


def _norm(p: str | os.PathLike) -> str:
    return os.path.normcase(os.path.realpath(os.fspath(p)))


def _under(path: str, base: str | os.PathLike) -> bool:
    b = _norm(base)
    p = _norm(path)
    return p == b or p.startswith(b.rstrip(os.sep) + os.sep)


def _find_project(start: str) -> Path | None:
    try:
        d = Path(start).resolve()
    except OSError:
        return None
    for c in (d, *d.parents):
        if (c / VMODEL_DIR / "config.json").is_file():
            return c
    return None


def _deny(reason: str) -> dict:
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                   "permissionDecisionReason": f"[vmodel guard] {reason}"}}


def _is_verifier(agent_type: Any) -> bool:
    return isinstance(agent_type, str) and agent_type.split(":")[-1] == "verifier"


def protected_paths(project: Path) -> list[tuple[str, str]]:
    v = project / VMODEL_DIR
    root = plugin_root()
    out = [
        (str(v / "state"), "validator ledger (only the validator writes it)"),
        (str(v / "evidence"), "validator evidence (only the validator writes it)"),
        (str(v / "config.json"), "project config (user-owned; change it outside the agent)"),
        (str(v / "devkit.lock.json"), "validator lock (user-owned)"),
        (str(v / "install-record.json"), "install record (user-owned)"),
        (str(vmodel_home()), "VModel home with signing keys"),
    ]
    out += [(str(root / d), "Validator Core (pinned, hashed)") for d in CORE_DIRS]
    return out


def _home_markers() -> list[str]:
    home = vmodel_home()
    return sorted({".vmodel-devkit", str(home).lower(), str(home).replace("\\", "/").lower()})


def _core_markers() -> list[str]:
    root = plugin_root()
    return sorted({str(root).lower(), str(root).replace("\\", "/").lower()})


SAFE_TAIL = re.compile(r"(\s+2>&1)?(\s*\|\s*(head|tail|grep|less|cat|wc)(\s+[^;&|`<>$]*)?)*\s*$")


# --- D46 (drill S1 2026-11-10, reviews 16-19) ---------------------------------------------------------------------
# A validator call may carry quoted text (a request with < > ; | & ( ) #) only when the whole call is in this narrow
# grammar: plain words outside quotes, single-quoted text without quote-like characters, double-quoted text without
# command substitution, backticks, ${ $[ or quote-like characters (bash: a backslash escapes any character but a newline;
# a quoted Windows path keeps its backslashes). Masking quoted text
# by hand kept disagreeing with bash, PowerShell and cmd.exe (ANSI-C $'', comments, typographic quotes, .cmd
# re-parsing), so anything outside the grammar is judged as before, with an unquoted newline and, in PowerShell, a
# parenthesised argument also counting as shell syntax.
_PLAIN_WORD = r"[A-Za-z0-9_./:=+\-]"  # one character per repetition: no nested quantifier (no ReDoS)
_PLAIN_SQ = "'[^'\u2018-\u201f]*'"
_PLAIN_DQ = {"Bash": '"(?:[^"$`\\\\\u2018-\u201f]|\\$(?![({\\[])|\\\\[^\\n\\r\u2018-\u201f])*"',
             "PowerShell": '"(?:[^"$`\u2018-\u201f]|\\$(?![({\\[]))*"'}
_PLAIN_SEP = {"Bash": r"(?:[ \t]+\\\n[ \t]*|[ \t]+)", "PowerShell": r"[ \t]+"}
PLAIN_CALL = {k: re.compile(rf"(?:{_PLAIN_WORD}|{_PLAIN_SQ}|{dq})+(?:{_PLAIN_SEP[k]}(?:{_PLAIN_WORD}|{_PLAIN_SQ}|{dq})+)*")
              for k, dq in _PLAIN_DQ.items()}
PS_META = re.compile(r"[;&|`<>(]|\$\(")


def _call_tokens(head: str, tool: str) -> list[str] | None:
    try:  # bash removes backslash-newline (line continuation) before splitting words
        return shlex.split(head.replace("\\\n", "") if tool == "Bash" else head, posix=True)
    except ValueError:
        return None


def _plain_call(text: str, tool: str) -> bool:
    if tool != "Bash" and any(ch in text for ch in "&|<>^%"):  # PowerShell runs bin/vmodel as vmodel.cmd (PATHEXT),
        return False                                           # and cmd.exe parses the arguments again (review 20)
    if not PLAIN_CALL.get(tool, PLAIN_CALL["PowerShell"]).fullmatch(text):
        return False
    toks = _call_tokens(text, tool)
    return bool(toks) and not toks[0].lower().endswith((".cmd", ".bat"))  # cmd.exe parses its arguments again
# --- end D46 -------------------------------------------------------------------------------------------------------


def _is_validator_call(cmd: str, tool: str = "Bash") -> bool:
    """A single plain vmodel invocation, optionally followed by 2>&1 and read-only filters.

    Quoted executable paths may contain spaces (e.g. "C:\\Users\\x\\vmodel 한글\\bin\\vmodel"). Quoted arguments may
    contain shell metacharacters only within the D46 grammar.
    """
    c = cmd.strip()
    if _plain_call(c, tool):
        head = c
    else:
        m = SAFE_TAIL.search(c) if "|" in c or "2>&1" in c else None  # no tail to find: skip the (quadratic) search
        head = c[: m.start()] if m else c
        if "\n" in c or "\r" in c or (SHELL_META if tool == "Bash" else PS_META).search(head):
            if not _plain_call(head, tool) or "\n" in c[len(head):] or "\r" in c[len(head):]:
                return False
    toks = _call_tokens(head, tool)
    if not toks:
        return False
    first = toks[0]
    if first in ("vmodel", "vmodel.cmd"):
        return True  # the plugin's bin/ is on the Bash PATH
    root = plugin_root()
    if _same_file(first, root / "bin" / "vmodel") or _same_file(first, root / "bin" / "vmodel.cmd"):
        return True
    return len(toks) >= 2 and re.match(r"^(python[0-9.]*|py)(\.exe)?$", first.replace("\\", "/").rsplit("/", 1)[-1]) \
        is not None and _same_file(toks[1], root / "validator" / "vmodel.py")


def _same_file(candidate: str, real: Path) -> bool:
    """True only for the real validator launcher, not for any script that happens to be named bin/vmodel."""
    try:
        return _norm(candidate) == _norm(real)
    except (OSError, ValueError):
        return False


def guard(payload: dict) -> dict | None:
    """Return a PreToolUse deny decision, or None to allow."""
    tool = payload.get("tool_name") or ""
    ti = payload.get("tool_input") or {}
    cwd = payload.get("cwd") or os.getcwd()
    agent_type = payload.get("agent_type")
    project = _find_project(os.environ.get("CLAUDE_PROJECT_DIR") or cwd) or _find_project(cwd)
    if project is None:
        return None
    verifier = _is_verifier(agent_type)

    if tool in WRITE_TOOLS or tool in READ_TOOLS:
        raw = ti.get("file_path") or ti.get("notebook_path") or ti.get("path") or ""
        if not raw:
            return None
        path = raw if os.path.isabs(raw) else os.path.join(cwd, raw)
        if tool in READ_TOOLS:
            if _under(path, vmodel_home() / "keys"):
                return _deny("reading VModel signing keys is not allowed")
            return None
        for base, why in protected_paths(project):
            if _under(path, base):
                return _deny(f"{raw} is protected: {why}. Use the vmodel CLI instead.")
        reviews_dir = project / VMODEL_DIR / "work-items"
        in_reviews = _under(path, reviews_dir) and Path(_norm(path)).parent.name == "reviews"
        if in_reviews and not verifier:
            return _deny("gate reviews must be written by the vmodel:verifier subagent (independent context), "
                         f"not by '{agent_type or 'main session'}'")
        if verifier and not in_reviews:
            return _deny("the verifier is read-only except for .vmodel/work-items/<WI>/reviews/*.json")
        return None

    if tool in SHELL_TOOLS:
        cmd = str(ti.get("command") or "")
        low = cmd.lower().replace("\\", "/")
        validator_call = _is_validator_call(cmd, tool)
        writes = shell_writes(cmd, tool)
        if USER_ONLY.search(cmd):
            return _deny("init/install/uninstall/unblock/configure-tests and 'lock --accept-current' are user-only actions; "
                         "ask the user to run them in a terminal")
        if "review-submit" in low and not verifier:
            return _deny("only the vmodel:verifier subagent may submit gate reviews")
        if validator_call:
            return None
        if verifier and writes:
            return _deny("the verifier may only run read-only commands and the vmodel CLI")
        if REPO_WIDE_DESTRUCTIVE.search(cmd) or REPO_WIDE_DESTRUCTIVE.search(normalize_redirections(cmd, tool)):
            return _deny("repository-wide deletion (git clean, find -delete, rm of '.' or '*') would also destroy "
                         "VModel records; delete explicit paths instead")
        if any(m in low for m in _home_markers()):
            return _deny("VModel home (signing keys, anchors) is off limits to the agent")
        if ".vmodel" in low and writes:
            return _deny("this command would modify .vmodel/ through the shell; use the Write/Edit tools for work "
                         "item artifacts and the vmodel CLI for everything validator-owned")
        if any(m in low for m in _core_markers()) and writes:
            return _deny("this command would modify the Validator Core (pinned and hashed)")
        return None
    return None


def session_context(cwd: str) -> str | None:
    project = _find_project(os.environ.get("CLAUDE_PROJECT_DIR") or cwd) or _find_project(cwd)
    if project is None:
        return None
    from .project import Project
    from .status import project_status, render_status

    root = plugin_root()
    lines = [
        "[VModel DevKit active in this project]",
        f"Validator CLI: \"{root / 'bin' / 'vmodel'}\" (run it with Bash; it finds Python 3.11+). Artifact formats "
        "and role guides: 'vmodel guide <topic>' (plugin files are outside the project).",
        "Policy: feature development, substantive behaviour changes, bug fixes, architecture changes and large "
        "refactors follow the V-Model workflow -> use /vmodel:start <request> (or continue the open work item). "
        "Explanations, Q&A, searches, unrelated docs and read-only analysis do NOT use the workflow. "
        "If unsure, tell the user and suggest /vmodel:start.",
        "Only the validator decides gates. Never claim PASS without 'vmodel gate'/'vmodel status' output. "
        "Never edit .vmodel/state, .vmodel/evidence, config or lock files. Reviews are written only by vmodel:verifier.",
    ]
    try:
        st = project_status(Project(project))
        brief = render_status(st)
        lines += ["", "Current status (from the signed ledger):", brief[:6000]]
    except Exception as exc:  # status must never break session start
        lines.append(f"(status unavailable: {exc.__class__.__name__}: {exc})")
    return "\n".join(lines)


def run_hook(kind: str, stdin_bytes: bytes) -> tuple[int, str]:
    try:
        payload = json.loads(stdin_bytes.decode("utf-8", errors="replace") or "{}")
    except json.JSONDecodeError:
        payload = None
    if kind == "guard":
        if not isinstance(payload, dict):
            return 0, json.dumps(_deny("hook input was not valid JSON; blocking to stay safe"))
        decision = guard(payload)
        log = os.environ.get("VMODEL_GUARD_LOG")
        if log:  # diagnostics for hook behaviour tests; set by the user/test runner, not reachable by the agent
            entry = {"tool_name": payload.get("tool_name"), "agent_type": payload.get("agent_type"),
                     "agent_id": payload.get("agent_id"), "tool_input": payload.get("tool_input"),
                     "decision": "deny" if decision else "allow",
                     "reason": decision["hookSpecificOutput"]["permissionDecisionReason"] if decision else None}
            with open(log, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return 0, json.dumps(decision, ensure_ascii=False) if decision else ""
    if kind == "session-start":
        cwd = (payload or {}).get("cwd") if isinstance(payload, dict) else None
        text = session_context(cwd or os.getcwd())
        return 0, text or ""
    return 2, f"unknown hook {kind}"

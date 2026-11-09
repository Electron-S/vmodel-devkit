"""Check regression tests against a plugin copy: RED on the old core, GREEN on the fix (v0.1.4 procedure).

    python3 scripts/red_green.py --mode red   --plugin dist/vmodel-0.1.3 --log <file> <test module> ...
    python3 scripts/red_green.py --mode green --log <file> <test module> ...

Expectations come from the test class name, so they are fixed before any code changes:
  ...Red        RED mode: every method must FAIL by assertion (an ERROR is not a clean RED). GREEN mode: pass.
  ...Char       characterisation of current behaviour: must pass in both modes.
  ...Invariant  invariant that the fix must not change: must pass in both modes.
  ...Accept     acceptance test that only makes sense on the new core: GREEN mode only (not run in RED mode).
Other TestCase classes in the module are not evaluated. Exit code 0 only if every expectation holds.

--marker TEXT (0.2.0): in RED mode a Red FAIL counts only if TEXT appears in its assertion traceback, so a failure in a
helper or in setUp (which carries no marker) is reported as a violation instead of a clean RED.
"""
from __future__ import annotations

import argparse
import importlib
import io
import json
import os
import subprocess
import sys
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TESTS = REPO / "tests"
KINDS = ("Red", "Char", "Invariant", "Accept")


def kind_of(cls: type) -> str | None:
    for k in KINDS:
        if cls.__name__.endswith(k):
            return k
    return None


class Collect(unittest.TextTestResult):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.outcomes: dict[str, tuple[str, str]] = {}
        self.tracebacks: dict[str, str] = {}

    def addSuccess(self, test):
        super().addSuccess(test)
        self.outcomes[test.id()] = ("ok", "")

    def addFailure(self, test, err):
        super().addFailure(test, err)
        tb = self._exc_info_to_string(err, test)
        self.tracebacks[test.id()] = tb
        self.outcomes[test.id()] = ("FAIL", _first_line(tb))

    def addError(self, test, err):
        super().addError(test, err)
        self.outcomes[test.id()] = ("ERROR", _first_line(self._exc_info_to_string(err, test)))

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self.outcomes[test.id()] = ("skipped", reason)


def _first_line(tb: str) -> str:
    lines = [ln for ln in tb.strip().splitlines() if ln.strip()]
    for ln in reversed(lines):
        if ln.startswith(("AssertionError", "KeyError", "TypeError", "ValueError", "AttributeError")):
            return ln[:400]
    return (lines[-1] if lines else "")[:400]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=("red", "green"), required=True)
    ap.add_argument("--plugin", help="plugin directory under test (default: the source plugins/vmodel)")
    ap.add_argument("--log", required=True)
    ap.add_argument("--marker", help="RED mode: a Red FAIL must carry this text in its assertion traceback")
    ap.add_argument("modules", nargs="+")
    args = ap.parse_args()
    log = Path(args.log).resolve()  # before the chdir below
    if args.plugin:
        os.environ["VMODEL_TEST_PLUGIN"] = str(Path(args.plugin).resolve())
    else:
        os.environ.pop("VMODEL_TEST_PLUGIN", None)
    sys.path.insert(0, str(TESTS))
    os.chdir(TESTS)
    import helpers  # noqa: E402  (reads VMODEL_TEST_PLUGIN at import)

    plugin = helpers.PLUGIN
    rm = plugin / "RELEASE_MANIFEST.json"
    plugin_desc = {"path": str(plugin), "release_manifest": None}
    if rm.is_file():
        m = json.loads(rm.read_text(encoding="utf-8"))
        plugin_desc["release_manifest"] = {"version": m.get("version"), "core_hash": m.get("core_hash")}
    head = subprocess.run(["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"], capture_output=True, text=True)
    dirty = subprocess.run(["git", "-C", str(REPO), "status", "--porcelain"], capture_output=True, text=True)

    suite = unittest.TestSuite()
    expected: dict[str, str] = {}
    loader = unittest.TestLoader()
    for name in args.modules:
        mod = importlib.import_module(name)
        for attr in sorted(dir(mod)):
            cls = getattr(mod, attr)
            if not (isinstance(cls, type) and issubclass(cls, unittest.TestCase) and cls.__module__ == mod.__name__):
                continue
            k = kind_of(cls)
            if k is None or (k == "Accept" and args.mode == "red"):
                continue
            tests = loader.loadTestsFromTestCase(cls)
            for t in tests:
                expected[t.id()] = "FAIL" if (k == "Red" and args.mode == "red") else "ok"
            suite.addTests(tests)

    stream = io.StringIO()
    t0 = time.time()
    runner = unittest.TextTestRunner(stream=stream, verbosity=0, resultclass=Collect)
    result: Collect = runner.run(suite)  # type: ignore[assignment]
    took = time.time() - t0

    rows, bad = [], 0
    for tid, want in expected.items():
        got, msg = result.outcomes.get(tid, ("missing", ""))
        ok = got == want
        if ok and got == "FAIL" and args.marker and args.marker not in result.tracebacks.get(tid, ""):
            ok = False
            msg = f"(no {args.marker} marker: not the targeted assertion) {msg}"
        bad += not ok
        rows.append(f"{'OK ' if ok else 'BAD'} expect={want:<4} got={got:<7} {tid}" + (f"\n      {msg}" if msg else ""))
    summary = {"mode": args.mode, "plugin": plugin_desc, "git_head": head.stdout.strip(),
               "worktree_dirty": bool(dirty.stdout.strip()), "python": sys.version.split()[0], "marker": args.marker,
               "tests": len(expected), "expectations_met": len(expected) - bad, "violations": bad,
               "seconds": round(took, 1)}
    text = "\n".join([json.dumps(summary, indent=2), "", *rows, ""])
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(text, encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    print(text)
    return 0 if bad == 0 and expected else 1


if __name__ == "__main__":
    sys.exit(main())

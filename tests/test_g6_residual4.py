"""Independent review 25 of the instance-shadowing check (c399b1a): false patches and lost tracing.

RED target: git archive c399b1a plugins/vmodel (the reviewer's standalone tracer runs, re-run).
- The check reported any provider method name found in a module-level instance's __dict__, so the provider's own code
  was a "patch": a functools.cached_property value, a per-instance cache (`self.compute = lru_cache(...)(self.compute)`)
  and a per-instance strategy (`self.run = self._fast`). Now an instance value counts only when it is a mock, test-tree
  code or code from a string (the weak rule).
- An object whose __dict__ access raised made the check raise; the monitoring callback then disabled tracing of that
  provider function, so a later test's call was not recorded. The check must never stop tracing.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from g6_base import RED
from helpers import PLUGIN

TRACER = PLUGIN / "validator" / "vmodel_validator" / "tracer"
PROV = '''import functools


class _Fmt:
    @functools.cached_property
    def table(self):
        return {"x": 1}

    def top(self, records):
        return max(records)


class _Cache:
    def __init__(self):
        self.compute = functools.lru_cache(maxsize=None)(self.compute)

    def compute(self, x):
        return x * 2


class _Strategy:
    def __init__(self, fast):
        if fast:
            self.run = self._fast

    def run(self, x):
        return x

    def _fast(self, x):
        return x


class _Weird:
    def __getattribute__(self, name):
        if name == "__dict__":
            raise RuntimeError("no dict here")
        return object.__getattribute__(self, name)

    def ping(self):
        return 1


_fmt = _Fmt()
_cache = _Cache()
_strategy = _Strategy(fast=True)
_weird = _Weird() if __import__("os").environ.get("WEIRD") else None


def work(x):
    _fmt.table
    _cache.compute(x)
    _strategy.run(x)
    return x
'''
DEFS = {"strict": ["_Fmt.top", "_Cache.__init__", "_Cache.compute", "_Strategy.__init__", "_Strategy.run",
                   "_Strategy._fast", "_Weird.__getattribute__", "_Weird.ping", "work", "_Fmt", "_Cache", "_Strategy",
                   "_Weird"],
        "weak": ["_Fmt.table"]}
TEST = '''import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import prov


def test_TEST_010_x():
    prov.work(1)


def test_TEST_011_y():
    if os.environ.get("FAKE"):
        prov._fmt.top = lambda records: 0
    prov.work(2)


for name in ("test_TEST_010_x", "test_TEST_011_y"):
    os.environ["PYTEST_CURRENT_TEST"] = f"t.py::{name} (call)"
    globals()[name]()
'''


class TracerBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="vmodel-inst-"))
        (self.tmp / "prov.py").write_text(PROV, encoding="utf-8")
        (self.tmp / "t.py").write_text(TEST, encoding="utf-8")
        (self.tmp / "out").mkdir()
        self.spec = self.tmp / "spec.json"
        self.spec.write_text(json.dumps({
            "out": str(self.tmp / "out"),
            "watch": {str((self.tmp / "prov.py").resolve()): "src/prov.py", str((self.tmp / "t.py").resolve()): "tests/t.py"},
            "providers": {"src/prov.py": []}, "tests": ["tests/t.py"], "provider_defs": {"src/prov.py": DEFS},
            "test_files": [str((self.tmp / "t.py").resolve())]}), encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_traced(self, **extra) -> list[dict]:
        env = {k: v for k, v in os.environ.items() if not k.startswith(("PYTHON", "PYTEST", "VMODEL"))}
        env.update({"PYTHONPATH": str(TRACER), "VMODEL_TRACE_SPEC": str(self.spec), **extra})
        r = subprocess.run([sys.executable, str(self.tmp / "t.py")], cwd=str(self.tmp), env=env, capture_output=True,
                           text=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stderr[-800:])
        return [json.loads(x) for f in (self.tmp / "out").glob("*.jsonl")
                for x in f.read_text(encoding="utf-8").splitlines()[1:]]


class InstanceOwnCodeRed(TracerBase):
    def test_the_providers_own_instance_rebinding_is_no_patch(self):
        patched = sorted({n for r in self.run_traced() if "x" in r for n in r["n"]})
        self.assertEqual(patched, [], f"{RED} {patched}")

    def test_a_raising_dict_never_stops_tracing(self):
        ran = {r["t"] for r in self.run_traced(WEIRD="1") if r.get("m") == "src/prov.py" and r.get("f") == "work"}
        self.assertEqual(ran, {"t.py::test_TEST_010_x", "t.py::test_TEST_011_y"}, f"{RED} {ran}")


class InstancePatchChar(TracerBase):
    def test_a_test_lambda_on_the_instance_is_a_patch(self):
        patched = {(r["t"], n) for r in self.run_traced(FAKE="1") if "x" in r for n in r["n"]}
        self.assertIn(("t.py::test_TEST_011_y", "_fmt.top"), patched)


if __name__ == "__main__":
    unittest.main()

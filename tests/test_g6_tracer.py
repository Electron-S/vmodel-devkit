"""The validator's runtime tracer on its own (REQ-G6-31): what it records, attribution to the pytest test id, child
processes, the setprofile fallback, and that a tracer problem never breaks the traced program."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import PLUGIN

TRACER = PLUGIN / "validator" / "vmodel_validator" / "tracer"


class TracerAccept(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="vmodel-tracer-")) / "추적 테스트"
        self.tmp.mkdir()
        (self.tmp / "mod.py").write_text("def f():\n    return 1\n\n\nclass K:\n    def m(self):\n        return 2\n",
                                         encoding="utf-8")
        (self.tmp / "other.py").write_text("def g():\n    return 3\n", encoding="utf-8")
        self.out = self.tmp / "trace"
        self.out.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp.parent, ignore_errors=True)

    def spec(self, **extra) -> Path:
        p = self.tmp / "spec.json"
        p.write_text(json.dumps({"out": str(self.out), "watch": {str(self.tmp / "mod.py"): "mod"}, **extra}),
                     encoding="utf-8")
        return p

    def run_py(self, code: str, spec: Path | None, test_id: str | None = "t.py::test_TEST_001_x (call)") -> int:
        env = {k: v for k, v in os.environ.items() if not k.startswith(("PYTHON", "PYTEST", "VMODEL"))}
        env["PYTHONPATH"] = str(TRACER)
        if spec is not None:
            env["VMODEL_TRACE_SPEC"] = str(spec)
        if test_id:
            env["PYTEST_CURRENT_TEST"] = test_id
        return subprocess.run([sys.executable, "-c", code], cwd=str(self.tmp), env=env, capture_output=True,
                              timeout=120).returncode

    def records(self) -> list[dict]:
        out = []
        for f in sorted(self.out.glob("*.jsonl")):
            lines = f.read_text(encoding="utf-8").splitlines()
            out += [json.loads(x) for x in lines[1:]]
        for r in out:
            r.pop("ts", None)
            r.pop("tc", None)  # 0.2.0 review 4: lines carry a wall-clock time; compared without it
        return [r for r in out if "b" not in r]  # and test boundary lines (the pytest process only)

    def test_function_calls_are_attributed_to_the_test_and_children_are_traced(self):
        code = ("import subprocess, sys, mod, other\nmod.f(); other.g(); mod.K().m()\n"
                "subprocess.run([sys.executable, '-c', 'import mod; mod.f()'], check=True)\n")
        self.assertEqual(self.run_py(code, self.spec()), 0)
        recs = self.records()
        # records carry the pytest phase since the review fix F6 (proof must come from the test call phase)
        self.assertIn({"t": "t.py::test_TEST_001_x", "p": "call", "m": "mod", "f": "f"}, recs)
        self.assertIn({"t": "t.py::test_TEST_001_x", "p": "call", "m": "mod", "f": "K.m"}, recs)
        self.assertFalse([r for r in recs if r["m"] != "mod"])  # other.py is not watched
        headers = [json.loads(f.read_text(encoding="utf-8").splitlines()[0]) for f in self.out.glob("*.jsonl")]
        self.assertEqual(len(headers), 2)  # parent and child
        self.assertEqual(len([r for r in recs if r["f"] == "f"]), 2)

    def test_import_alone_is_not_execution(self):
        self.assertEqual(self.run_py("import mod\n", self.spec()), 0)
        self.assertEqual(self.records(), [])

    def test_setprofile_fallback_records_the_same(self):
        self.assertEqual(self.run_py("import mod\nmod.f()\n", self.spec(force_setprofile=True)), 0)
        self.assertEqual(self.records(), [{"t": "t.py::test_TEST_001_x", "p": "call", "m": "mod", "f": "f"}])
        header = json.loads(next(self.out.glob("*.jsonl")).read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(header["method"], "setprofile")

    def test_bad_spec_never_breaks_the_program(self):
        bad = self.tmp / "bad.json"
        bad.write_text("{not json", encoding="utf-8")
        self.assertEqual(self.run_py("import mod\nassert mod.f() == 1\n", bad), 0)
        self.assertEqual(self.run_py("import mod\nassert mod.f() == 1\n", self.tmp / "missing.json"), 0)
        self.assertEqual(self.run_py("import mod\nassert mod.f() == 1\n", None), 0)

    def test_project_sitecustomize_still_runs(self):
        (self.tmp / "site_dir").mkdir()
        (self.tmp / "site_dir" / "sitecustomize.py").write_text(
            "import os\nopen(os.path.join(os.path.dirname(__file__), 'ran.txt'), 'w').write('x')\n", encoding="utf-8")
        env = {k: v for k, v in os.environ.items() if not k.startswith(("PYTHON", "PYTEST", "VMODEL"))}
        env["PYTHONPATH"] = os.pathsep.join([str(TRACER), str(self.tmp / "site_dir")])
        env["VMODEL_TRACE_SPEC"] = str(self.spec())
        subprocess.run([sys.executable, "-c", "pass"], cwd=str(self.tmp), env=env, check=True, timeout=120)
        self.assertTrue((self.tmp / "site_dir" / "ran.txt").exists())


if __name__ == "__main__":
    unittest.main()

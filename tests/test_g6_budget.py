"""The tracer's stack-scan budget belongs to a thread, not to a reused thread id (review 14 C5, kept at tracer level).

test_g6_review14's sandbox case can no longer show this through a G6 verdict: since D48 R2 an autouse fixture's thread
makes the test count only main-thread evidence. Here the tracer runs directly: a thread started by another test-file
function calls a consumer function 3000 times and exits, then a thread the test function starts (the OS usually
reuses the id) calls it once; the consumer line with the test function's anchor must still be written. On 9497d14
(budget keyed by threading.get_ident) it was not.
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

from helpers import PLUGIN

TRACER = PLUGIN / "validator" / "vmodel_validator" / "tracer"
TEST = '''import os
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cons


def warm():
    t = threading.Thread(target=lambda: [cons.use(1) for _ in range(3000)])
    t.start()
    t.join()


def test_TEST_010_x():
    out = {}
    t = threading.Thread(target=lambda: out.setdefault("r", cons.use(2)))
    t.start()
    t.join()


os.environ["PYTEST_CURRENT_TEST"] = "t.py::test_TEST_010_x (call)"
warm()
test_TEST_010_x()
'''


class BudgetAccept(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="vmodel-budget-"))
        (self.tmp / "prov.py").write_text("def p(x):\n    return x\n", encoding="utf-8")
        (self.tmp / "cons.py").write_text("import prov\n\n\ndef use(x):\n    return prov.p(x)\n", encoding="utf-8")
        (self.tmp / "t.py").write_text(TEST, encoding="utf-8")
        (self.tmp / "out").mkdir()
        self.spec = self.tmp / "spec.json"
        self.spec.write_text(json.dumps({
            "out": str(self.tmp / "out"),
            "watch": {str((self.tmp / n).resolve()): lab for n, lab in
                      (("prov.py", "src/prov.py"), ("cons.py", "src/cons.py"), ("t.py", "tests/t.py"))},
            "providers": {"src/prov.py": ["src/cons.py"]}, "tests": ["tests/t.py"]}), encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_a_reused_thread_id_does_not_inherit_an_exhausted_budget(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith(("PYTHON", "PYTEST", "VMODEL"))}
        env.update({"PYTHONPATH": str(TRACER), "VMODEL_TRACE_SPEC": str(self.spec)})
        r = subprocess.run([sys.executable, str(self.tmp / "t.py")], cwd=str(self.tmp), env=env, capture_output=True,
                           text=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stderr[-800:])
        lines = [json.loads(x) for f in (self.tmp / "out").glob("*.jsonl")
                 for x in f.read_text(encoding="utf-8").splitlines()[1:]]
        own = [ln for ln in lines if ln.get("k") == "src/cons.py" and "test_TEST_010_x" in (ln.get("a") or [])]
        self.assertTrue(own, [ln for ln in lines if ln.get("k")][:5])


if __name__ == "__main__":
    unittest.main()

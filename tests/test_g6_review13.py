"""Independent review 13 of c451a13 (D45 round 2): regressions the round-12 fix caused.

RED target: git archive c451a13 plugins/vmodel. Reproduced from the reviewer's probes.
- SF1: a runtime path where the provider and the consumer are one module (the E2E-A design) was BLOCKED: consumer-run
  lines are written only for consumer files that are not also the provider's file, and path B now needed one.
- C5: an autouse thread calling a consumer function in a loop used up the per (test, phase, consumer) scan budget, so
  the test's own consumer run was never recorded and the miss was read as "only from an autouse fixture".
- os.system held a lock for the whole command: two os.system calls that wait for each other deadlocked, and a worker
  forked while another thread was inside os.system inherited the held lock.
Documented, not fixed (DECISIONS D45): fixtures the static patch detection does not reach (imported from another
module, base classes, pytest_plugins, the root conftest.py, MonkeyPatch.context()), and a conditional autouse patch
counted as a patch (conservative).
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

from g6_base import RED, file_sha256, justify_test_change, ledger_record, replace_function
from helpers import PLUGIN
from test_g6_e2e_findings import E2ESameFileRed
from test_g6_policy import CHILD_ENV, PolicyBase, iface, level

INTEGRATION = "tests/integration/test_pipeline.py"
TRACER = PLUGIN / "validator" / "vmodel_validator" / "tracer"


def g6_with_runtime(tc, kind: str, iid: str, tests: tuple) -> tuple[dict, dict]:
    sb = tc.sb
    for tid in tests:
        justify_test_change(sb, INTEGRATION, affected=tid, reqs=("REQ-002",))
    entries = sb.interface_review_entries()
    for e in entries:
        if e["id"] == iid:
            e["runtime_paths"] = [{"test": t, "kind": kind, "test_file_sha256": file_sha256(sb.root / INTEGRATION)}
                                  for t in tests]
            e["provider_symbols"] = ["main", "summarize"] if iid == "IF-002" else ["parse"]
    sb.review("G4", interfaces=entries)
    for g in ("G4", "G5"):
        res = sb.gate(g)[1]
        assert res["status"] == "PASSED", json.dumps(res, indent=1, ensure_ascii=False)[:3000]
    r6 = sb.gate("G6")[1]
    return r6, (ledger_record(sb, r6["record_id"]) if r6.get("record_id") else {})


class R13SameFileRed(E2ESameFileRed):
    """Provider (parse) and consumer (summarize) in one module, both IF-001 tests on a declared subprocess path."""
    test_E2E_A_provider_and_consumer_in_one_module = None

    def test_SF1_same_module_runtime_path(self):
        it = self.sb.root / INTEGRATION
        t = it.read_text(encoding="utf-8")
        it.write_text(t.replace("import json\n", "import json\nimport os\nimport subprocess\nimport sys\n", 1),
                      encoding="utf-8")
        body = (CHILD_ENV +
                "    res = subprocess.run([sys.executable, '-c', 'import json; from pipeline.report import summarize; '\n"
                "                          'print(json.dumps(summarize(\"a,1\")))'], env=env, capture_output=True,\n"
                "                         text=True, check=True)\n"
                "    assert json.loads(res.stdout)['count'] == 1\n")
        replace_function(it, "test_TEST_010_report_uses_real_parser", "def test_TEST_010_report_uses_real_parser():\n" + body)
        replace_function(it, "test_TEST_011_parser_error_reaches_report",
                         "def test_TEST_011_parser_error_reaches_report():\n" + body)
        r6, rec = g6_with_runtime(self, "subprocess", "IF-001", ("TEST-010", "TEST-011"))
        self.assertEqual((r6.get("status"), level(rec, "IF-001", "TEST-010")), ("PASSED", "test_level"),
                         f"{RED} {iface(rec, 'IF-001')}")


class R13ScanCapRed(PolicyBase):
    def test_C5_consumer_noise_from_an_autouse_thread_before_the_tests_own_run(self):
        rp = self.sb.root / "src/pipeline/report.py"
        rp.write_text(rp.read_text(encoding="utf-8").replace(
            "\n\ndef main(", "\n\ndef label(x) -> str:\n    return str(x)\n\n\ndef main(", 1), encoding="utf-8")
        replace_function(self.itest, "test_TEST_010_report_uses_real_parser",
                         "@pytest.fixture(autouse=True)\ndef heartbeat():\n"
                         "    import threading\n    from pipeline import report\n    stop = threading.Event()\n\n"
                         "    def beat():\n        while not stop.is_set():\n            report.label(1)\n\n"
                         "    t = threading.Thread(target=beat, daemon=True)\n    t.start()\n    yield\n"
                         "    stop.set()\n    t.join()\n\n\n"
                         "def test_TEST_010_report_uses_real_parser():\n"
                         "    import importlib\n    import time\n    time.sleep(0.5)\n"
                         "    assert importlib.import_module('pipeline.report').summarize('a,1')['count'] == 1\n")
        r6, rec = g6_with_runtime(self, "dynamic_import", "IF-001", ("TEST-010",))
        self.assertEqual(level(rec, "IF-001", "TEST-010"), "test_level", f"{RED} {iface(rec, 'IF-001')}")


@unittest.skipUnless(hasattr(os, "mkfifo") and hasattr(os, "fork"), "POSIX fifo and fork")
class R13SystemRed(unittest.TestCase):
    """The tracer's os.system wrapper must not change what the traced program can do."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="vmodel-sys-"))
        (self.tmp / "trace").mkdir()
        (self.tmp / "mod.py").write_text("def f():\n    return 1\n", encoding="utf-8")
        self.spec = self.tmp / "spec.json"
        self.spec.write_text(json.dumps({"out": str(self.tmp / "trace"), "watch": {str(self.tmp / "mod.py"): "mod"}}),
                             encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_py(self, code: str) -> str:
        env = {k: v for k, v in os.environ.items() if not k.startswith(("PYTHON", "PYTEST", "VMODEL"))}
        env.update({"PYTHONPATH": str(TRACER), "VMODEL_TRACE_SPEC": str(self.spec),
                    "PYTEST_CURRENT_TEST": "t.py::test_TEST_001_x (call)"})
        (self.tmp / "prog.py").write_text(code, encoding="utf-8")
        r = subprocess.run([sys.executable, str(self.tmp / "prog.py")], cwd=str(self.tmp), env=env,
                           capture_output=True, text=True, timeout=60)
        return r.stdout + r.stderr

    def test_two_os_system_calls_that_wait_for_each_other(self):
        out = self.run_py(
            "import os, threading, time\n"
            "fifo = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'f')\nos.mkfifo(fifo)\nres = {}\n"
            "a = threading.Thread(target=lambda: res.__setitem__('r', os.system(f'cat {fifo} > /dev/null')), daemon=True)\n"
            "def w():\n    time.sleep(0.3)\n    res['w'] = os.system(f'echo hi > {fifo}')\n"
            "b = threading.Thread(target=w, daemon=True)\na.start(); b.start(); a.join(8); b.join(1)\n"
            "print('DONE' if not a.is_alive() and not b.is_alive() else 'HUNG')\n"
            "if a.is_alive():\n    open(fifo, 'w').write('x')\n")
        self.assertIn("DONE", out, f"{RED} {out[-800:]}")

    def test_worker_forked_while_another_thread_is_in_os_system(self):
        out = self.run_py(
            "import multiprocessing as mp, os, threading, time, warnings\n"
            "warnings.simplefilter('ignore', DeprecationWarning)\n"
            "def job(_):\n    return os.system('true')\n"
            "if __name__ == '__main__':\n"
            "    threading.Thread(target=lambda: os.system('sleep 2'), daemon=True).start()\n    time.sleep(0.3)\n"
            "    with mp.get_context('fork').Pool(1) as pool:\n"
            "        r = pool.map_async(job, [0])\n"
            "        try:\n            print('RESULT', r.get(timeout=8))\n"
            "        except mp.TimeoutError:\n            print('HUNG')\n"
            "        pool.terminate()\n")
        self.assertIn("RESULT [0]", out, f"{RED} {out[-800:]}")


if __name__ == "__main__":
    unittest.main()

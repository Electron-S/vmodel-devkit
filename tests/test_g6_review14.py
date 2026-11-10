"""Independent review 14 of 9497d14 (D45 round 3).

RED target: git archive 9497d14 plugins/vmodel. Reproduced from the reviewer's probes.
- SF2 (false PASS made by the round-13 SF1 fix): "provider and consumer share a module" was decided per interface, so
  when only some provider modules are also consumer modules, a provider run in a provider-only module counted as the
  consumer evidence.
- C5 (not fully fixed): the per-thread scan budget was keyed by threading.get_ident(), which the OS reuses after a
  thread exits, so a finished autouse thread's budget was charged to the test's own thread; and the provider side still
  had one budget per (test, phase, file, function) for every thread.
- The "not certain" note used the capped node ids the trace summary keeps (the first 20).
"""
from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from g6_base import RED, SandboxClass, replace_function
from helpers import PLUGIN
from test_g6_policy import CHILD_ENV, PolicyBase, iface, level
from test_g6_review13 import g6_with_runtime

INTEGRATION = "tests/integration/test_pipeline.py"


def add_label(sb) -> None:
    rp = sb.root / "src/pipeline/report.py"
    rp.write_text(rp.read_text(encoding="utf-8").replace(
        "\n\ndef main(", "\n\ndef label(x) -> str:\n    return str(x)\n\n\ndef main(", 1), encoding="utf-8")


class R14PartialOverlapRed(SandboxClass):
    """IF-001's provider component ARCH-001 has units in parser.py (parse) and report.py (main); the consumer ARCH-002
    is report.py (summarize): provider modules {parser.py, report.py}, consumer modules {report.py}."""
    upto = "G1"

    @classmethod
    def build(cls, sb):
        super().build(sb)
        sb.prepare("G2")
        arch = sb.load("architecture.json")
        for c in arch["components"]:
            if c["id"] == "ARCH-001":
                c["requirements"] = sorted(set(c["requirements"]) | {"REQ-002"})
        sb.save("architecture.json", arch)
        sb.review("G2")
        res = sb.gate("G2")[1]
        assert res["status"] == "PASSED", json.dumps(res, ensure_ascii=False)[:3000]
        sb.prepare("G3")
        design = sb.load("design.json")
        for u in design["units"]:
            if u["id"] == "DESIGN-003":
                u["component"] = "ARCH-001"
        sb.save("design.json", design)
        sb.review("G3")
        res = sb.gate("G3")[1]
        assert res["status"] == "PASSED", json.dumps(res, ensure_ascii=False)[:3000]
        sb.prepare("G4")
        sb.review("G4")
        for g in ("G4", "G5"):
            res = sb.gate(g)[1]
            assert res["status"] == "PASSED", json.dumps(res, ensure_ascii=False)[:3000]

    def test_SF2_provider_only_module_run_is_no_consumer_evidence(self):
        it = self.sb.root / INTEGRATION
        it.write_text(it.read_text(encoding="utf-8").replace(
            "import json\n", "import json\nimport os\nimport subprocess\nimport sys\n", 1), encoding="utf-8")
        body = (CHILD_ENV +
                "    res = subprocess.run([sys.executable, '-c', 'from pipeline.parser import parse; '\n"
                "                          'print(len(parse(\"a,1\")))'], env=env, capture_output=True, text=True,\n"
                "                         check=True)\n"
                "    assert res.stdout.strip() == '1'\n")
        replace_function(it, "test_TEST_010_report_uses_real_parser", "def test_TEST_010_report_uses_real_parser():\n" + body)
        replace_function(it, "test_TEST_011_parser_error_reaches_report",
                         "def test_TEST_011_parser_error_reaches_report():\n" + body)
        r6, rec = g6_with_runtime(self, "subprocess", "IF-001", ("TEST-010", "TEST-011"))
        self.assertNotEqual(level(rec, "IF-001", "TEST-010"), "test_level",
                            f"{RED} no consumer function ran anywhere: {iface(rec, 'IF-001')}")
        self.assertEqual(r6.get("status"), "BLOCKED", f"{RED} {r6}")


class R14ScanBudgetRed(PolicyBase):
    def test_C5_reused_thread_id_after_an_autouse_thread_exits(self):
        add_label(self.sb)
        replace_function(self.itest, "test_TEST_010_report_uses_real_parser",
                         "@pytest.fixture(autouse=True)\ndef warm():\n"
                         "    import threading\n    import time\n    from pipeline import report\n\n"
                         "    def go():\n        time.sleep(0.2)\n        for _ in range(3000):\n            report.label(1)\n\n"
                         "    t = threading.Thread(target=go)\n    t.start()\n    yield\n    t.join()\n\n\n"
                         "def test_TEST_010_report_uses_real_parser():\n"
                         "    import importlib\n    import threading\n    import time\n"
                         "    time.sleep(1.0)\n"
                         "    mod = importlib.import_module('pipeline.report')\n    out = {}\n"
                         "    t = threading.Thread(target=lambda: out.__setitem__('r', mod.summarize('a,1')))\n"
                         "    t.start()\n    t.join()\n"
                         "    assert out['r']['count'] == 1\n")
        r6, rec = g6_with_runtime(self, "dynamic_import", "IF-001", ("TEST-010",))
        self.assertEqual(level(rec, "IF-001", "TEST-010"), "test_level", f"{RED} {iface(rec, 'IF-001')}")

    def test_C5_provider_noise_from_an_autouse_thread(self):
        replace_function(self.itest, "test_TEST_010_report_uses_real_parser",
                         "@pytest.fixture(autouse=True)\ndef heartbeat():\n"
                         "    import threading\n    from pipeline import parser\n    stop = threading.Event()\n\n"
                         "    def beat():\n        while not stop.is_set():\n            parser.parse('a,1')\n\n"
                         "    t = threading.Thread(target=beat, daemon=True)\n    t.start()\n    yield\n"
                         "    stop.set()\n    t.join()\n\n\n"
                         "def test_TEST_010_report_uses_real_parser():\n"
                         "    import importlib\n    import time\n    time.sleep(0.5)\n"
                         "    assert importlib.import_module('pipeline.report').summarize('a,1')['count'] == 1\n")
        r6, rec = g6_with_runtime(self, "dynamic_import", "IF-001", ("TEST-010",))
        self.assertEqual(level(rec, "IF-001", "TEST-010"), "test_level", f"{RED} {iface(rec, 'IF-001')}")


class R14CappedRed(unittest.TestCase):
    def test_every_capped_test_is_known_to_the_judgement(self):
        import importlib
        import sys
        sys.path.insert(0, str(PLUGIN / "validator"))
        try:
            for m in [m for m in sys.modules if m == "vmodel_validator" or m.startswith("vmodel_validator.")]:
                del sys.modules[m]
            gates = importlib.import_module("vmodel_validator.gates")
        finally:
            sys.path.remove(str(PLUGIN / "validator"))
        d = Path(tempfile.mkdtemp(prefix="vmodel-cap-"))
        try:
            lines = [{"v": 2, "spawned_in": None}]
            lines += [{"edge_scan_capped": True, "t": f"tests/integration/test_x.py::test_TEST_{i:03d}_a", "p": "call",
                       "k": "src/c.py"} for i in range(100, 130)]
            (d / "1-a.jsonl").write_text("\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8")
            rt = gates.read_runtime_trace(d)
            self.assertEqual(len(rt.get("_capped") or []), 30, f"{RED} only the summary's first 20 were kept")
        finally:
            shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()

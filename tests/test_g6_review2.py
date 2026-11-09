"""Second independent review (c216910, docs/g6/WORKITEM.md section 7.2): every accepted finding as a test first.

RED target: the re-reviewed build (git archive c216910 plugins/vmodel). Finding numbers N1..N11 and P1/P2 (pre-existing
since 0.1.x) follow the review report.
"""
from __future__ import annotations

import json
import os
import sys
import unittest

from g6_base import RED, SandboxClass, file_sha256, justify_test_change, replace_function

INTEGRATION = "tests/integration/test_pipeline.py"
MOCKED_IF001 = (
    ("test_TEST_010_report_uses_real_parser",
     "def test_TEST_010_report_uses_real_parser(monkeypatch):\n"
     "    monkeypatch.setattr('pipeline.report.parse', lambda text: [{'name': 'x', 'score': 1}])\n"
     "    assert summarize('ignored')['top'] == 'x'\n"),
    ("test_TEST_011_parser_error_reaches_report",
     "def test_TEST_011_parser_error_reaches_report(monkeypatch):\n"
     "    def boom(text):\n        raise ValueError('x')\n"
     "    monkeypatch.setattr('pipeline.report.parse', boom)\n"
     "    with pytest.raises(ValueError):\n        summarize('kim,ninety')\n"),
)
TRACE_OUT = ("[v for k, v in os.environ.items() if k.startswith('VMODEL') and k.endswith('_SPEC')]")


class R2WiringBase(SandboxClass):
    """pipeline, split commands, G1-G3 PASSED, code in place (G4 not evaluated)."""
    upto = "G3"

    @classmethod
    def build(cls, sb):
        super().build(sb)
        sb.put_code()

    @property
    def itest(self):
        return self.sb.root / INTEGRATION

    def path(self, iid: str, tid: str) -> str:
        code, out = self.sb.vm("wiring", "WI-001", "--json")
        self.assertEqual(code, 0, out)
        return json.loads(out)["interfaces"][iid]["tests"][tid]["path"]

    def wiring_test(self, iid: str, tid: str) -> dict:
        code, out = self.sb.vm("wiring", "WI-001", "--json")
        self.assertEqual(code, 0, out)
        return json.loads(out)["interfaces"][iid]["tests"][tid]


class R2WiringRed(R2WiringBase):
    # N5: references that are never called
    def test_N5a_module_level_def_shadowing_the_import(self):
        text = self.itest.read_text(encoding="utf-8")
        self.itest.write_text(text.replace("from pipeline.report import main, summarize\n",
                                           "from pipeline.report import main, summarize\n\n\n"
                                           "def summarize(text):  # noqa: F811\n    return {'count': 3, 'total': 255, "
                                           "'top': 'lee'}\n"), encoding="utf-8")
        self.assertNotEqual(self.path("IF-001", "TEST-010"), "static", f"{RED} the later def shadows the import")

    def test_N5b_local_reassignment_after_a_local_import(self):
        replace_function(self.itest, "test_TEST_012_cli_main_reads_file",
                         "def test_TEST_012_cli_main_reads_file():\n"
                         "    import functools\n    from pipeline.report import main\n"
                         "    main = functools.partial(len)\n    assert main(['x']) == 1\n")
        self.assertNotEqual(self.path("IF-002", "TEST-012"), "static", f"{RED} main is reassigned")

    def test_N5c_setup_local_alias_resolves_in_setup_scope(self):
        replace_function(self.itest, "test_TEST_012_cli_main_reads_file", None)
        self.itest.write_text(self.itest.read_text(encoding="utf-8") + (
            "\n\nclass TestCli:\n"
            "    def setup_method(self):\n        main = lambda argv: 0  # noqa: E731\n        self.run_cli = main\n\n"
            "    def test_TEST_012_cli_alias(self):\n        assert self.run_cli(['x']) == 0\n"), encoding="utf-8")
        self.assertNotEqual(self.path("IF-002", "TEST-012"), "static", f"{RED} setUp's local main is a lambda")

    def test_N5d_lambda_argument_that_is_never_called(self):
        replace_function(self.itest, "test_TEST_012_cli_main_reads_file",
                         "def test_TEST_012_cli_main_reads_file():\n"
                         "    assert sorted([], key=lambda a: main([a])) == []\n")
        self.assertNotEqual(self.path("IF-002", "TEST-012"), "static", f"{RED} sorted([]) never calls the key")

    def test_N5e_injection_into_a_non_consumer_call(self):
        replace_function(self.itest, "test_TEST_012_cli_main_reads_file",
                         "def test_TEST_012_cli_main_reads_file():\n"
                         "    from pipeline.parser import parse\n"
                         "    with pytest.raises(TypeError):\n        parse(main)\n")
        self.assertNotEqual(self.path("IF-002", "TEST-012"), "static", f"{RED} main handed to the provider of IF-001")

    # N6: project files must not take over stdlib names
    def test_N6_project_http_module_does_not_hide_http_client(self):
        (self.sb.root / "src/pipeline/http.py").write_text("X = 1\n", encoding="utf-8")
        replace_function(self.itest, "test_TEST_012_cli_main_reads_file",
                         "def test_TEST_012_cli_main_reads_file():\n"
                         "    import http.client\n"
                         "    conn = http.client.HTTPConnection('127.0.0.1', 9)\n"
                         "    assert conn is not None\n")
        t = self.wiring_test("IF-002", "TEST-012")
        self.assertEqual((t["path"], t["best"]["mechanisms"]), ("runtime_candidate", ["api"]),
                         f"{RED} http.client is the stdlib: {t}")

    def test_N6_project_json_module_does_not_take_over_stdlib_json(self):
        (self.sb.root / "src/pipeline/json.py").write_text(
            "import pipeline.report  # noqa: F401\n\n\ndef loads(s):\n    return {}\n", encoding="utf-8")
        replace_function(self.itest, "test_TEST_012_cli_main_reads_file",
                         "def test_TEST_012_cli_main_reads_file():\n"
                         "    assert json.loads('{\"count\": 2}') == {'count': 2}\n")
        self.assertNotEqual(self.path("IF-002", "TEST-012"), "static", f"{RED} json is the stdlib json")

    # N10: module-level instances and star re-exports
    def test_N10_module_level_instance_method_is_a_call(self):
        rp = self.sb.root / "src/pipeline/report.py"
        rp.write_text(rp.read_text(encoding="utf-8").replace(
            'if __name__ == "__main__":',
            "class _Cli:\n    def run(self, argv):\n        return main(argv)\n\n\ncli = _Cli()\n\n\n"
            'if __name__ == "__main__":'), encoding="utf-8")
        replace_function(self.itest, "test_TEST_012_cli_main_reads_file",
                         "def test_TEST_012_cli_main_reads_file(tmp_path, capsys):\n"
                         "    from pipeline.report import cli\n"
                         "    f = tmp_path / 'scores.csv'\n    f.write_text('a,1\\n', encoding='utf-8')\n"
                         "    assert cli.run([str(f)]) == 0\n")
        self.assertEqual(self.path("IF-002", "TEST-012"), "static", f"{RED} cli.run is _Cli.run")

    def test_N10_star_reexport_in_package_init(self):
        (self.sb.root / "src/pipeline/__init__.py").write_text("from .report import *  # noqa: F403\n",
                                                               encoding="utf-8")
        replace_function(self.itest, "test_TEST_010_report_uses_real_parser",
                         "def test_TEST_010_report_uses_real_parser():\n"
                         "    from pipeline import summarize as s\n"
                         "    assert s('kim,90\\n')['count'] == 1\n")
        self.assertEqual(self.path("IF-001", "TEST-010"), "static", f"{RED} pipeline.summarize via star re-export")

    # N11: relative import in a namespace package
    def test_N11_relative_import_in_a_namespace_package(self):
        (self.sb.root / "src/pipeline/__init__.py").unlink()
        rp = self.sb.root / "src/pipeline/report.py"
        rp.write_text(rp.read_text(encoding="utf-8").replace("from pipeline.parser import parse\n",
                                                             "from . import parser\n").replace(
            "records = parse(text)", "records = parser.parse(text)"), encoding="utf-8")
        self.assertEqual(self.path("IF-001", "TEST-010"), "static", f"{RED} report imports parser relatively")


class R2G6Red(SandboxClass):
    """pipeline, split commands, G1-G5 PASSED."""

    @property
    def itest(self):
        return self.sb.root / INTEGRATION

    def to_g6(self, interfaces: list | None = None, rel: str = INTEGRATION) -> tuple[dict, dict, int | None, dict]:
        justify_test_change(self.sb, rel)
        self.sb.review("G4", interfaces=interfaces)
        r4 = self.sb.gate("G4")[1]
        r5 = self.sb.gate("G5")[1] if r4["status"] == "PASSED" else {}
        if r5.get("status") != "PASSED":
            return r4, r5, None, {}
        code, out = self.sb.vm("gate", "WI-001", "G6", "--json")
        try:
            return r4, r5, code, json.loads(out)
        except json.JSONDecodeError:
            return r4, r5, code, {"raw": out[-800:]}

    def mock_if001(self) -> None:
        for name, src in MOCKED_IF001:
            replace_function(self.itest, name, src)

    def test_N1_background_thread_running_the_provider_is_not_the_tests_evidence(self):
        for name, src in MOCKED_IF001:  # mocked tests that last long enough for the thread to run meanwhile
            replace_function(self.itest, name, src.replace("(monkeypatch):\n", "(monkeypatch):\n    import time\n"
                                                                                "    time.sleep(0.3)\n", 1))
        (self.sb.root / "tests/integration/conftest.py").write_text(
            "import threading\nimport time\n\nfrom pipeline import parser\n\n\n"
            "def _spin():\n    while True:\n        try:\n            parser.parse('a,1')\n"
            "        except Exception:\n            pass\n        time.sleep(0.005)\n\n\n"
            "threading.Thread(target=_spin, daemon=True).start()\n", encoding="utf-8")
        r4, r5, code, r6 = self.to_g6()
        self.assertEqual((r4["status"], r5.get("status")), ("PASSED", "PASSED"), r4)
        self.assertNotEqual(r6.get("status"), "PASSED", f"{RED} a conftest thread ran the provider, not the tests")

    @unittest.skipUnless(sys.platform.startswith("linux"), "fork start method (Linux)")
    def test_N2_forked_ipc_child_is_another_process(self):
        replace_function(self.itest, "test_TEST_012_cli_main_reads_file",
                         "def test_TEST_012_cli_main_reads_file(tmp_path):\n"
                         "    import multiprocessing\n    from pipeline import report\n"
                         "    f = tmp_path / 's.csv'\n    f.write_text('a,1\\n', encoding='utf-8')\n"
                         "    with multiprocessing.get_context('fork').Pool(1) as pool:\n"
                         "        assert pool.apply(report.main, ([str(f)],)) == 0\n")
        entries = self.sb.interface_review_entries()
        for e in entries:
            if e["id"] == "IF-002":
                e["runtime_paths"] = [{"test": "TEST-012", "kind": "ipc", "test_file_sha256": file_sha256(self.itest)}]
        r4, r5, code, r6 = self.to_g6(entries)
        self.assertEqual((r4["status"], r5.get("status")), ("PASSED", "PASSED"), r4)
        self.assertEqual(r6.get("status"), "PASSED", f"{RED} report.main ran in the forked pool worker: {r6}")

    def test_N3_deeply_nested_trace_line_is_not_a_crash(self):
        replace_function(self.itest, "test_TEST_012_cli_main_reads_file",
                         "def test_TEST_012_cli_main_reads_file(tmp_path, capsys):\n"
                         "    import json as j\n    import os\n"
                         f"    out = j.load(open({TRACE_OUT}[0], encoding='utf-8'))['out']\n"
                         "    with open(os.path.join(out, 'zz.jsonl'), 'w', encoding='utf-8') as fh:\n"
                         "        fh.write('{\"v\": 1}\\n' + '[' * 200000 + '\\n')\n"
                         "    f = tmp_path / 'scores.csv'\n    f.write_text('a,1\\nb,2\\n', encoding='utf-8')\n"
                         "    assert main([str(f)]) == 0\n")
        r4, r5, code, r6 = self.to_g6()
        self.assertNotEqual(code, 2, f"{RED} internal error instead of a gate result: {r6}")
        self.assertTrue(r6.get("recorded"), r6)

    def test_N4_deleted_trace_is_not_junit_only_credit(self):
        self.mock_if001()
        (self.sb.root / "tests/integration/conftest.py").write_text(
            "import glob\nimport json\nimport os\n\n"
            f"_spec = {TRACE_OUT}\n"
            "if _spec:\n"
            "    for p in glob.glob(os.path.join(json.load(open(_spec[0], encoding='utf-8'))['out'], '*.jsonl')):\n"
            "        os.remove(p)\n", encoding="utf-8")
        r4, r5, code, r6 = self.to_g6()
        self.assertEqual((r4["status"], r5.get("status")), ("PASSED", "PASSED"), r4)
        self.assertNotEqual(r6.get("status"), "PASSED", f"{RED} no runtime trace: nothing proves the provider ran")

    def test_N8_fixture_computing_the_result_in_setup_is_credited(self):
        replace_function(self.itest, "test_TEST_012_cli_main_reads_file",
                         "@pytest.fixture\ndef cli_output(tmp_path, capsys):\n"
                         "    f = tmp_path / 'scores.csv'\n    f.write_text('a,1\\nb,2\\n', encoding='utf-8')\n"
                         "    assert main([str(f)]) == 0\n    return json.loads(capsys.readouterr().out)\n\n\n"
                         "def test_TEST_012_cli_main_reads_file(cli_output):\n"
                         "    assert cli_output == {'count': 2, 'total': 3, 'top': 'b'}\n")
        r4, r5, code, r6 = self.to_g6()
        self.assertEqual((r4["status"], r5.get("status")), ("PASSED", "PASSED"), r4)
        self.assertEqual(r6.get("status"), "PASSED", f"{RED} the provider ran in the requested fixture: {r6}")

    def test_N9_many_parametrised_cases_do_not_truncate_the_evidence(self):
        replace_function(self.itest, "test_TEST_010_report_uses_real_parser",
                         "@pytest.mark.parametrize('i', range(4500))\n"
                         "def test_TEST_010_report_uses_real_parser(i):\n"
                         "    assert summarize(f'kim,{i}\\n')['total'] == i\n")
        r4, r5, code, r6 = self.to_g6()
        self.assertEqual((r4["status"], r5.get("status")), ("PASSED", "PASSED"), r4)
        self.assertEqual(r6.get("status"), "PASSED", f"{RED} {[c for c in r6.get('checks') or [] if c['status'] != 'pass']}")

    @unittest.skipUnless(os.name == "posix", "symlinks need privileges on Windows")
    def test_N7_symlinked_junit_stays_hashed_as_in_015(self):
        unit = self.sb.root / "tests/unit/test_report.py"
        replace_function(unit, "test_TEST_007_main_empty_file",
                         "def test_TEST_007_main_empty_file(tmp_path, capsys):\n"
                         "    import os\n    import sys\n"
                         "    junit = [a.split('=', 1)[1] for a in sys.argv if a.startswith('--junit' + 'xml=')][0]\n"
                         "    os.symlink(str(tmp_path / 'x.xml'), junit)\n"
                         "    f = tmp_path / 'empty.csv'\n    f.write_text('', encoding='utf-8')\n"
                         "    assert main([str(f)]) == 0\n")
        justify_test_change(self.sb, "tests/unit/test_report.py", affected="TEST-007")
        self.sb.review("G4")
        self.assertEqual(self.sb.gate("G4")[1]["status"], "PASSED")
        res = self.sb.gate("G5")[1]
        self.assertEqual(res["status"], "PASSED", res)
        rec = self.sb.root / res["evidence"][0]["path"]
        target = os.path.realpath(rec.parent / "junit.xml")
        with open(target, "a", encoding="utf-8") as fh:
            fh.write("<!-- changed after the run -->")
        code, out = self.sb.vm("verify-evidence", str(rec))
        self.assertEqual(code, 1, f"{RED} junit.xml content changed after the run but evidence verifies: {out}")


class R2PreexistingRed(R2WiringBase):
    def test_P1_huge_integer_in_a_review_is_not_a_crash(self):
        self.sb.review("G4", extra={"note": "BIGNUM"}, submit=False)
        path = self.sb.wi_dir / "reviews/G4.json"
        path.write_text(path.read_text(encoding="utf-8").replace('"BIGNUM"', "1" + "0" * 5000), encoding="utf-8")
        code, out = self.sb.vm("gate", "WI-001", "G4", "--json")
        self.assertNotEqual(code, 2, f"{RED} {out[-400:]}")

    def test_P2_non_string_interface_provider_is_not_a_crash(self):
        arch = self.sb.load("architecture.json")
        arch["interfaces"][0]["provider"] = ["ARCH-001"]
        self.sb.save("architecture.json", arch)
        for cmd in (("trace", "WI-001"), ("report", "WI-001"), ("status",)):
            code, out = self.sb.vm(*cmd)
            self.assertNotEqual(code, 2, f"{RED} {cmd}: {out[-400:]}")


if __name__ == "__main__":
    unittest.main()

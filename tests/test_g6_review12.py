"""Independent review 12 of the D45 change (092a0fe): policies A/B on both paths, and the regressions it caused.

RED target: git archive 092a0fe plugins/vmodel. Reproduced from the reviewer's probes (scratch reviewer-work) by
re-running them against that build.
- H1 (policy A, both paths; also on 5275b5d): a provider patch made by an autouse fixture or by a fixture applied
  with @pytest.mark.usefixtures was never seen (only fixtures named as test parameters were analysed).
- H2 (policy B, path B; also on 5275b5d): the consumer evidence of a runtime path was any consumer run in the call
  phase, including one an autouse fixture's thread made.
- M1/M2/M3 (regressions of 092a0fe, Test-level on 5275b5d): a process started through multiprocessing spawn or
  forkserver or os.system had no origin; a fixture applied with usefixtures was not a requested fixture; a fork pool
  created in a thread lost the thread's inherited anchors in the forked child.
Not fixed, documented (DECISIONS D45): who sent a request to a server (H3: the request crosses a socket), a patch
written inside a child's command string (H4: not visible to the static analysis).
"""
from __future__ import annotations

import json
import multiprocessing
import unittest

from g6_base import RED, file_sha256, justify_test_change, ledger_record, replace_function
from test_g6_policy import CHILD_ENV, EXPECTED, REQUEST, PolicyBase, iface, level, server_fixture

INTEGRATION = "tests/integration/test_pipeline.py"
POSIX_FORK = "fork" in multiprocessing.get_all_start_methods()
FORKSERVER = "forkserver" in multiprocessing.get_all_start_methods()
SERVER_PROC = (
    "import json\nfrom http.server import BaseHTTPRequestHandler, HTTPServer\nfrom pipeline import report\n"
    "class H(BaseHTTPRequestHandler):\n"
    "    def do_POST(self):\n"
    "        body = self.rfile.read(int(self.headers['Content-Length'])).decode('utf-8')\n"
    "        out = json.dumps(report.summarize(body)).encode('utf-8')\n"
    "        self.send_response(200)\n        self.send_header('Content-Length', str(len(out)))\n"
    "        self.end_headers()\n        self.wfile.write(out)\n"
    "    def log_message(self, *a):\n        pass\n"
    "srv = HTTPServer(('127.0.0.1', 0), H)\nprint(srv.server_address[1], flush=True)\nsrv.serve_forever()\n")
SERVER_PROC_FIXTURE = (
    "PORT = {}\n\n\n@pytest.fixture\ndef server_port():\n" + CHILD_ENV +
    f"    proc = subprocess.Popen([sys.executable, '-c', {SERVER_PROC!r}], stdout=subprocess.PIPE, text=True, env=env)\n"
    "    PORT['p'] = int(proc.stdout.readline())\n    yield PORT['p']\n    proc.terminate()\n    proc.wait(timeout=30)\n\n\n")
REAL_TOP = "lambda records: max(records, key=lambda r: (r['score'], r['name']))"


def pool_test(method: str, from_thread: bool = False) -> str:
    if not from_thread:
        return ("def test_TEST_012_cli_main_reads_file():\n"
                "    import multiprocessing\n    from pipeline import report\n"
                f"    ctx = multiprocessing.get_context('{method}')\n"
                "    with ctx.Pool(1) as pool:\n"
                f"        assert pool.apply(report.summarize, ('a,1\\nb,2\\n',)) == {EXPECTED}\n")
    return ("def test_TEST_012_cli_main_reads_file():\n"
            "    import multiprocessing\n    import threading\n    from pipeline import report\n"
            f"    out = {{}}\n    ctx = multiprocessing.get_context('{method}')\n\n"
            "    def go():\n"
            "        with ctx.Pool(1) as pool:\n"
            "            out['r'] = pool.apply(report.summarize, ('a,1\\nb,2\\n',))\n\n"
            "    t = threading.Thread(target=go)\n    t.start()\n    t.join()\n"
            f"    assert out['r'] == {EXPECTED}\n")


class R12Base(PolicyBase):
    def go(self, kind: str | None, iid: str = "IF-002", tests: tuple = ("TEST-012",)) -> tuple[dict, dict]:
        """G4 re-review (runtime path declared when kind is given), G4/G5 must pass (helper), then G6."""
        for tid in tests:
            justify_test_change(self.sb, INTEGRATION, affected=tid, reqs=("REQ-002",))
        entries = self.sb.interface_review_entries()
        if kind:
            for e in entries:
                if e["id"] == iid:
                    e["runtime_paths"] = [{"test": t, "kind": kind, "test_file_sha256": file_sha256(self.itest)}
                                          for t in tests]
                    e["provider_symbols"] = ["main", "summarize"] if iid == "IF-002" else ["parse"]
        self.sb.review("G4", interfaces=entries)
        r4 = self.sb.gate("G4")[1]
        assert r4["status"] == "PASSED", json.dumps(r4, indent=1, ensure_ascii=False)[:3000]
        r5 = self.sb.gate("G5")[1]
        assert r5["status"] == "PASSED", json.dumps(r5, indent=1, ensure_ascii=False)[:3000]
        r6 = self.sb.gate("G6")[1]
        return r6, (ledger_record(self.sb, r6["record_id"]) if r6.get("record_id") else {})

    def assert_level(self, rec: dict, r6: dict, want: str, iid: str = "IF-002", tid: str = "TEST-012") -> None:
        got = level(rec, iid, tid)
        if want == "test_level":
            self.assertEqual((r6.get("status"), got), ("PASSED", "test_level"), f"{RED} {iface(rec, iid)}")
        else:
            self.assertNotEqual(got, "test_level", f"{RED} {iface(rec, iid)}")
            self.assertEqual(r6.get("status"), "BLOCKED", f"{RED} {r6}")


class R12PatchRed(R12Base):
    """H1: policy A also for patches made by autouse fixtures and by fixtures applied with usefixtures."""

    def test_H1a_autouse_fixture_patches_the_provider_static_path(self):
        self.add_top_helper()
        t = self.itest.read_text(encoding="utf-8")
        self.itest.write_text(t.replace(
            "\n\ndef test_TEST_010", "\n\n@pytest.fixture(autouse=True)\ndef fake_top(monkeypatch):\n"
            f"    monkeypatch.setattr('pipeline.report._top', {REAL_TOP})\n\n\ndef test_TEST_010", 1),
            encoding="utf-8")
        r6, rec = self.go(None, tests=("TEST-010",))
        self.assert_level(rec, r6, "insufficient")

    def test_H1b_usefixtures_fixture_patches_the_provider_static_path(self):
        self.add_top_helper()
        replace_function(self.itest, "test_TEST_012_cli_main_reads_file",
                         "@pytest.fixture\ndef fake_top(monkeypatch):\n"
                         "    monkeypatch.setattr('pipeline.report._top', lambda records: {'name': 'b'})\n\n\n"
                         "@pytest.mark.usefixtures('fake_top')\n"
                         "def test_TEST_012_cli_main_reads_file(tmp_path, capsys):\n"
                         "    f = tmp_path / 'scores.csv'\n    f.write_text('a,1\\nb,2\\n', encoding='utf-8')\n"
                         "    assert main([str(f)]) == 0\n"
                         f"    assert json.loads(capsys.readouterr().out) == {EXPECTED}\n")
        r6, rec = self.go(None)
        self.assert_level(rec, r6, "insufficient")

    def test_H1c_autouse_fixture_patches_the_provider_runtime_path(self):
        self.add_top_helper()
        replace_function(self.itest, "test_TEST_012_cli_main_reads_file",
                         "@pytest.fixture(autouse=True)\ndef fake_top(monkeypatch):\n"
                         f"    monkeypatch.setattr('pipeline.report._top', {REAL_TOP})\n\n\n" +
                         server_fixture(False) + "def test_TEST_012_cli_main_reads_file(server):\n" + REQUEST)
        r6, rec = self.go("api")
        self.assert_level(rec, r6, "insufficient")


class R12ConsumerRed(R12Base):
    def test_H2_consumer_ran_only_in_an_autouse_fixtures_thread(self):
        """IF-001: both tests run the provider alone in a child; the consumer ran only in an autouse thread."""
        self.module_imports()
        body = (CHILD_ENV + "    import time\n"
                "    res = subprocess.run([sys.executable, '-c', 'from pipeline.parser import parse; '\n"
                "                          'print(len(parse(\"a,1\")))'], env=env, capture_output=True, text=True,\n"
                "                         check=True)\n"
                "    assert res.stdout.strip() == '1'\n    time.sleep(1.0)\n")
        replace_function(self.itest, "test_TEST_010_report_uses_real_parser",
                         "@pytest.fixture(autouse=True)\ndef background():\n"
                         "    import threading\n    import time\n    from pipeline import report\n\n"
                         "    def work():\n        time.sleep(0.3)\n        report.summarize('')\n\n"
                         "    threading.Thread(target=work, daemon=True).start()\n    yield\n\n\n"
                         "def test_TEST_010_report_uses_real_parser():\n" + body)
        replace_function(self.itest, "test_TEST_011_parser_error_reaches_report",
                         "def test_TEST_011_parser_error_reaches_report():\n" + body)
        r6, rec = self.go("subprocess", iid="IF-001", tests=("TEST-010", "TEST-011"))
        self.assertEqual([level(rec, "IF-001", t) == "test_level" for t in ("TEST-010", "TEST-011")], [False, False],
                         f"{RED} {iface(rec, 'IF-001')}")
        self.assertEqual(r6.get("status"), "BLOCKED", f"{RED} {r6}")


class R12RegressionRed(R12Base):
    """Legitimate runtime-path tests that 092a0fe BLOCKED (Test-level on 5275b5d): the test body or a fixture it
    requested started the work."""

    def test_M1a_spawn_pool_in_the_test_body(self):
        replace_function(self.itest, "test_TEST_012_cli_main_reads_file", pool_test("spawn"))
        r6, rec = self.go("ipc")
        self.assert_level(rec, r6, "test_level")

    @unittest.skipUnless(FORKSERVER, "forkserver start method (POSIX)")
    def test_M1b_forkserver_pool_in_the_test_body(self):
        replace_function(self.itest, "test_TEST_012_cli_main_reads_file", pool_test("forkserver"))
        r6, rec = self.go("ipc")
        self.assert_level(rec, r6, "test_level")

    def test_M1c_os_system_in_the_test_body(self):
        replace_function(self.itest, "test_TEST_012_cli_main_reads_file",
                         "def test_TEST_012_cli_main_reads_file(tmp_path, monkeypatch):\n"
                         "    import os\n    import sys\n    from pathlib import Path\n"
                         "    src = str(Path(__file__).resolve().parents[2] / 'src')\n"
                         "    monkeypatch.setenv('PYTHONPATH', os.pathsep.join(p for p in (src, os.environ.get('PYTHONPATH'))"
                         " if p))\n"
                         "    f = tmp_path / 'scores.csv'\n    f.write_text('a,1\\nb,2\\n', encoding='utf-8')\n"
                         "    out = tmp_path / 'out.json'\n"
                         "    cmd = f'\"{sys.executable}\" -m pipeline.report \"{f}\" > \"{out}\"'\n"
                         "    assert os.system(f'\"{cmd}\"' if os.name == 'nt' else cmd) == 0\n"
                         f"    assert json.loads(out.read_text(encoding='utf-8')) == {EXPECTED}\n")
        r6, rec = self.go("subprocess")
        self.assert_level(rec, r6, "test_level")

    def test_M2_server_fixture_applied_with_usefixtures(self):
        replace_function(self.itest, "test_TEST_012_cli_main_reads_file",
                         server_fixture(False) + "@pytest.mark.usefixtures('server')\n"
                         "def test_TEST_012_cli_main_reads_file():\n" + REQUEST)
        r6, rec = self.go("api")
        self.assert_level(rec, r6, "test_level")

    @unittest.skipUnless(POSIX_FORK, "fork start method (POSIX)")
    def test_M3_fork_pool_created_in_a_thread_the_test_started(self):
        replace_function(self.itest, "test_TEST_012_cli_main_reads_file", pool_test("fork", from_thread=True))
        r6, rec = self.go("ipc")
        self.assert_level(rec, r6, "test_level")


class R12ControlChar(R12Base):
    """Stay Test-level on 092a0fe and after the fix."""

    @unittest.skipUnless(POSIX_FORK, "fork start method (POSIX)")
    def test_fork_pool_in_the_test_body(self):
        replace_function(self.itest, "test_TEST_012_cli_main_reads_file", pool_test("fork"))
        r6, rec = self.go("ipc")
        self.assertEqual((r6.get("status"), level(rec, "IF-002", "TEST-012")), ("PASSED", "test_level"), r6)

    def test_asyncio_subprocess_in_the_test_body(self):
        self.module_imports()
        replace_function(self.itest, "test_TEST_012_cli_main_reads_file",
                         "def test_TEST_012_cli_main_reads_file(tmp_path):\n" + CHILD_ENV +
                         "    import asyncio\n"
                         "    f = tmp_path / 'scores.csv'\n    f.write_text('a,1\\nb,2\\n', encoding='utf-8')\n\n"
                         "    async def run():\n"
                         "        p = await asyncio.create_subprocess_exec(sys.executable, '-m', 'pipeline.report',\n"
                         "                                                 str(f), stdout=asyncio.subprocess.PIPE, env=env)\n"
                         "        out, _ = await p.communicate()\n        return out\n\n"
                         f"    assert json.loads(asyncio.run(run())) == {EXPECTED}\n")
        r6, rec = self.go("subprocess")
        self.assertEqual((r6.get("status"), level(rec, "IF-002", "TEST-012")), ("PASSED", "test_level"), r6)

    def test_requested_fixture_starting_a_server_process(self):
        self.module_imports()
        replace_function(self.itest, "test_TEST_012_cli_main_reads_file", SERVER_PROC_FIXTURE +
                         "def test_TEST_012_cli_main_reads_file(server_port):\n"
                         "    import urllib.request\n"
                         "    url = f'http://127.0.0.1:{server_port}/'\n"
                         "    with urllib.request.urlopen(url, data=b'a,1\\nb,2\\n', timeout=30) as resp:\n"
                         f"        assert json.loads(resp.read()) == {EXPECTED}\n")
        r6, rec = self.go("api")
        self.assertEqual((r6.get("status"), level(rec, "IF-002", "TEST-012")), ("PASSED", "test_level"), r6)


if __name__ == "__main__":
    unittest.main()

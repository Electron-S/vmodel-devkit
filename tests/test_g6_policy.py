"""Conservative evidence policy A/B on the runtime path (path B), confirmed by the owner on 2026-11-10 (decision D45).

A. Provider patch: running a patched provider is not, by itself, a verified real connection; other independent valid
   evidence may still cover the interface; without enough basis the interface is BLOCKED.
B. Autouse fixture: a connection made by the fixture itself is never credited to an individual test; a test that runs
   the provider/consumer connection itself and proves it is credited; using fixtures is not forbidden.

D44 applied both to path A (static call path: the anchor must be the test function or a fixture it requested; a test
that patches the provider is not test-level). On path B (a runtime path declared at G4: subprocess, ipc, api,
dynamic import) 5275b5d credited any provider run during the test's call phase, so:
- a test that patched a provider function and drove the real provider over HTTP was Test-level (policy A),
- a thread or child process started by an autouse fixture that ran the provider on its own during the call made the
  test Test-level although the test's own request never reached the provider (policy B, false PASS).
RED target: git archive 5275b5d plugins/vmodel (= release 0.2.0 candidate core 9cc0997a).
"""
from __future__ import annotations

import json
import unittest

from g6_base import RED, SandboxClass, file_sha256, justify_test_change, ledger_record, replace_function

INTEGRATION = "tests/integration/test_pipeline.py"
CHILD_ENV = (
    "    import os\n    import subprocess\n    import sys\n    from pathlib import Path\n"
    "    env = dict(os.environ)\n"
    "    src = str(Path(__file__).resolve().parents[2] / 'src')\n"
    "    env['PYTHONPATH'] = os.pathsep.join(p for p in (src, env.get('PYTHONPATH')) if p)\n")
HANDLER = (
    "    import threading\n    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer\n"
    "    from pipeline import report\n\n"
    "    class Handler(BaseHTTPRequestHandler):\n"
    "        def do_POST(self):\n"
    "            body = self.rfile.read(int(self.headers['Content-Length'])).decode('utf-8')\n"
    "            out = json.dumps(report.summarize(body)).encode('utf-8')\n"
    "            self.send_response(200)\n            self.send_header('Content-Length', str(len(out)))\n"
    "            self.end_headers()\n            self.wfile.write(out)\n\n"
    "        def log_message(self, *args):\n            pass\n\n"
    "    srv = ThreadingHTTPServer(('127.0.0.1', 0), Handler)\n"
    "    threading.Thread(target=srv.serve_forever, daemon=True).start()\n")
REQUEST = (
    "    import urllib.request\n"
    "    url = f\"http://127.0.0.1:{SRV['s'].server_address[1]}/\"\n"
    "    with urllib.request.urlopen(url, data=b'a,1\\nb,2\\n', timeout=30) as resp:\n"
    "        assert json.loads(resp.read()) == {'count': 2, 'total': 3, 'top': 'b'}\n")
EXPECTED = "{'count': 2, 'total': 3, 'top': 'b'}"
TOP_HELPER = "\n\ndef _top(records):\n    return max(records, key=lambda r: (r['score'], r['name']))\n"


def server_fixture(autouse: bool) -> str:
    return ("SRV = {}\n\n\n" + ("@pytest.fixture(autouse=True)\n" if autouse else "@pytest.fixture\n") +
            "def server():\n" + HANDLER + "    SRV['s'] = srv\n    yield srv\n    srv.shutdown()\n\n\n")


def iface(rec: dict, iid: str) -> dict:
    return ([i for i in rec.get("interfaces") or [] if i.get("id") == iid] or [{}])[0]


def level(rec: dict, iid: str, tid: str) -> str | None:
    return ((iface(rec, iid).get("tests") or {}).get(tid) or {}).get("evidence_level")


class PolicyBase(SandboxClass):
    """pipeline fixture (IF-001 parse: ARCH-001 -> ARCH-002, IF-002 report: ARCH-002 -> EXTERNAL), G1-G5 PASSED."""

    @property
    def itest(self):
        return self.sb.root / INTEGRATION

    def module_imports(self) -> None:
        t = self.itest.read_text(encoding="utf-8")
        if "\nimport subprocess\n" not in t:
            self.itest.write_text(t.replace("import json\n", "import json\nimport os\nimport subprocess\nimport sys\n",
                                            1), encoding="utf-8")

    def declare(self, kind: str, symbols: list | None = None) -> list[dict]:
        entries = self.sb.interface_review_entries()
        for e in entries:
            if e["id"] == "IF-002":
                e["runtime_paths"] = [{"test": "TEST-012", "kind": kind, "test_file_sha256": file_sha256(self.itest)}]
                e["provider_symbols"] = symbols or ["main", "summarize"]
        return entries

    def to_g6(self, kind: str) -> tuple[dict, dict]:
        """G4 re-review with TEST-012's runtime path declared, G4/G5 must pass (helper), then G6: (result, record)."""
        justify_test_change(self.sb, INTEGRATION)
        self.sb.review("G4", interfaces=self.declare(kind))
        r4 = self.sb.gate("G4")[1]
        assert r4["status"] == "PASSED", json.dumps(r4, indent=1, ensure_ascii=False)[:3000]
        r5 = self.sb.gate("G5")[1]
        assert r5["status"] == "PASSED", json.dumps(r5, indent=1, ensure_ascii=False)[:3000]
        r6 = self.sb.gate("G6")[1]
        return r6, (ledger_record(self.sb, r6["record_id"]) if r6.get("record_id") else {})

    def add_top_helper(self) -> None:
        rp = self.sb.root / "src/pipeline/report.py"
        t = rp.read_text(encoding="utf-8").replace(
            '    top = max(records, key=lambda r: (r["score"], r["name"]))\n', "    top = _top(records)\n", 1)
        assert "_top(records)" in t
        rp.write_text(t.replace("\n\ndef main(", TOP_HELPER + "\n\ndef main(", 1), encoding="utf-8")


class PolicyPatchRed(PolicyBase):
    """Policy A on path B: a test function that patches the provider is not test-level evidence by itself."""

    def test_A1_api_test_that_patches_a_provider_function(self):
        self.add_top_helper()
        replace_function(self.itest, "test_TEST_012_cli_main_reads_file",
                         server_fixture(False) +
                         "def test_TEST_012_cli_main_reads_file(server, monkeypatch):\n"
                         "    monkeypatch.setattr('pipeline.report._top', lambda records: {'name': 'b'})\n" + REQUEST)
        r6, rec = self.to_g6("api")
        self.assertEqual(level(rec, "IF-002", "TEST-012"), "insufficient",
                         f"{RED} the provider ran with its _top patched by the test: {iface(rec, 'IF-002')}")
        self.assertEqual(iface(rec, "IF-002").get("covered_by"), [], RED)
        self.assertEqual(r6.get("status"), "BLOCKED", f"{RED} {r6}")

    def test_A2_subprocess_test_that_patches_the_interface_symbol(self):
        """The child runs the real CLI, but the test function itself replaced the interface symbol: the same rule as
        path A (review 7 R4, policy A), whatever the runtime path (a forked ipc child would inherit the patch)."""
        self.module_imports()
        replace_function(self.itest, "test_TEST_012_cli_main_reads_file",
                         "def test_TEST_012_cli_main_reads_file(tmp_path, monkeypatch):\n"
                         f"    monkeypatch.setattr('pipeline.report.summarize', lambda text: {EXPECTED})\n" + CHILD_ENV +
                         "    f = tmp_path / 'scores.csv'\n    f.write_text('a,1\\nb,2\\n', encoding='utf-8')\n"
                         "    res = subprocess.run([sys.executable, '-m', 'pipeline.report', str(f)], capture_output=True,\n"
                         "                         env=env, check=True)\n"
                         f"    assert json.loads(res.stdout) == {EXPECTED}\n")
        r6, rec = self.to_g6("subprocess")
        self.assertEqual(level(rec, "IF-002", "TEST-012"), "insufficient", f"{RED} {iface(rec, 'IF-002')}")
        self.assertEqual(r6.get("status"), "BLOCKED", f"{RED} {r6}")


class PolicyFixtureRed(PolicyBase):
    """Policy B on path B: what an autouse fixture started (thread or process) is not the test's own connection."""

    def test_B1_autouse_fixture_thread_runs_the_provider_itself(self):
        """The test's request goes to a canned server; the autouse fixture's own thread runs summarize meanwhile."""
        replace_function(self.itest, "test_TEST_012_cli_main_reads_file",
                         "@pytest.fixture(autouse=True)\ndef background():\n"
                         "    import threading\n    import time\n    from pipeline import report\n\n"
                         "    def work():\n        time.sleep(0.3)\n        report.summarize('a,1')\n\n"
                         "    threading.Thread(target=work, daemon=True).start()\n    yield\n\n\n"
                         "def test_TEST_012_cli_main_reads_file():\n"
                         "    import threading\n    import time\n    import urllib.request\n"
                         "    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer\n\n"
                         "    class Canned(BaseHTTPRequestHandler):\n"
                         "        def do_POST(self):\n"
                         "            self.rfile.read(int(self.headers['Content-Length']))\n"
                         "            out = b'{\"count\": 2, \"total\": 3, \"top\": \"b\"}'\n"
                         "            self.send_response(200)\n"
                         "            self.send_header('Content-Length', str(len(out)))\n"
                         "            self.end_headers()\n            self.wfile.write(out)\n\n"
                         "        def log_message(self, *args):\n            pass\n\n"
                         "    srv = ThreadingHTTPServer(('127.0.0.1', 0), Canned)\n"
                         "    threading.Thread(target=srv.serve_forever, daemon=True).start()\n"
                         "    try:\n"
                         "        url = f'http://127.0.0.1:{srv.server_address[1]}/'\n"
                         "        with urllib.request.urlopen(url, data=b'a,1\\nb,2\\n', timeout=30) as resp:\n"
                         f"            assert json.loads(resp.read()) == {EXPECTED}\n"
                         "        time.sleep(0.8)\n"
                         "    finally:\n        srv.shutdown()\n")
        r6, rec = self.to_g6("api")
        self.assertNotEqual(level(rec, "IF-002", "TEST-012"), "test_level",
                            f"{RED} an autouse fixture's thread ran the provider: {iface(rec, 'IF-002')}")
        self.assertEqual(r6.get("status"), "BLOCKED", f"{RED} {r6}")

    def test_B2_autouse_fixture_child_process_runs_the_provider_itself(self):
        """The test's subprocess prints canned JSON; a child the autouse fixture started runs summarize meanwhile."""
        self.module_imports()
        replace_function(self.itest, "test_TEST_012_cli_main_reads_file",
                         "@pytest.fixture(autouse=True)\ndef background():\n" + CHILD_ENV +
                         "    proc = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(0.5); "
                         "from pipeline.report import summarize; summarize(\"a,1\")'], env=env)\n"
                         "    yield\n    proc.wait(timeout=30)\n\n\n"
                         "def test_TEST_012_cli_main_reads_file():\n"
                         "    import time\n"
                         "    res = subprocess.run([sys.executable, '-c', 'import json; "
                         "print(json.dumps({\"count\": 2, \"total\": 3, \"top\": \"b\"}))'],\n"
                         "                         capture_output=True, text=True, check=True)\n"
                         f"    assert json.loads(res.stdout) == {EXPECTED}\n"
                         "    time.sleep(1.5)\n")
        r6, rec = self.to_g6("subprocess")
        self.assertNotEqual(level(rec, "IF-002", "TEST-012"), "test_level",
                            f"{RED} a child process an autouse fixture started ran the provider: {iface(rec, 'IF-002')}")
        self.assertEqual(r6.get("status"), "BLOCKED", f"{RED} {r6}")

    def test_B3_autouse_server_fixture_cannot_prove_the_tests_request(self):
        """Conservative (policy B, 'not proven -> BLOCKED'): the test does send the request, but the provider ran in a
        server thread an autouse fixture started; nothing ties that run to the test rather than to the fixture.
        Requesting the fixture by name (PolicyControlChar) is credited."""
        replace_function(self.itest, "test_TEST_012_cli_main_reads_file",
                         server_fixture(True) + "def test_TEST_012_cli_main_reads_file():\n" + REQUEST)
        r6, rec = self.to_g6("api")
        self.assertNotEqual(level(rec, "IF-002", "TEST-012"), "test_level",
                            f"{RED} credited through an autouse fixture's server: {iface(rec, 'IF-002')}")
        self.assertEqual(r6.get("status"), "BLOCKED", f"{RED} {r6}")


class PolicyControlChar(PolicyBase):
    """Legitimate runtime-path tests that must stay Test-level Verified (fixtures are not forbidden)."""

    def test_C1_requested_server_fixture_with_the_tests_request(self):
        replace_function(self.itest, "test_TEST_012_cli_main_reads_file",
                         server_fixture(False) + "def test_TEST_012_cli_main_reads_file(server):\n" + REQUEST)
        r6, rec = self.to_g6("api")
        self.assertEqual((r6.get("status"), level(rec, "IF-002", "TEST-012")), ("PASSED", "test_level"),
                         iface(rec, "IF-002"))

    def test_C2_grandchild_process_started_through_the_tests_child(self):
        """The test starts a Python child that starts the CLI (the provider) as its own child."""
        self.module_imports()
        replace_function(self.itest, "test_TEST_012_cli_main_reads_file",
                         "def test_TEST_012_cli_main_reads_file(tmp_path):\n" + CHILD_ENV +
                         "    f = tmp_path / 'scores.csv'\n    f.write_text('a,1\\nb,2\\n', encoding='utf-8')\n"
                         "    inner = ('import subprocess, sys; r = subprocess.run([sys.executable, \"-m\", '\n"
                         "             '\"pipeline.report\", sys.argv[1]], capture_output=True, text=True, check=True); '\n"
                         "             'print(r.stdout, end=\"\")')\n"
                         "    res = subprocess.run([sys.executable, '-c', inner, str(f)], capture_output=True, text=True,\n"
                         "                         env=env, check=True)\n"
                         f"    assert json.loads(res.stdout) == {EXPECTED}\n")
        r6, rec = self.to_g6("subprocess")
        self.assertEqual((r6.get("status"), level(rec, "IF-002", "TEST-012")), ("PASSED", "test_level"),
                         iface(rec, "IF-002"))

    def test_C3_unrelated_autouse_fixture_and_the_tests_own_subprocess(self):
        """An autouse fixture that only prepares the environment does not stop the test's own connection counting."""
        self.module_imports()
        replace_function(self.itest, "test_TEST_012_cli_main_reads_file",
                         "@pytest.fixture(autouse=True)\ndef _locale(monkeypatch):\n"
                         "    monkeypatch.setenv('LC_ALL', 'C.UTF-8')\n    yield\n\n\n"
                         "def test_TEST_012_cli_main_reads_file(tmp_path):\n" + CHILD_ENV +
                         "    f = tmp_path / 'scores.csv'\n    f.write_text('a,1\\nb,2\\n', encoding='utf-8')\n"
                         "    res = subprocess.run([sys.executable, '-m', 'pipeline.report', str(f)], capture_output=True,\n"
                         "                         env=env, check=True)\n"
                         f"    assert json.loads(res.stdout) == {EXPECTED}\n")
        r6, rec = self.to_g6("subprocess")
        self.assertEqual((r6.get("status"), level(rec, "IF-002", "TEST-012")), ("PASSED", "test_level"),
                         iface(rec, "IF-002"))


if __name__ == "__main__":
    unittest.main()

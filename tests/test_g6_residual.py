"""Residual G6 false PASS shapes from reviews 12-13 (D45 section 8), closed by run-time facts (decision D48).

Policy A/B (D45) say a patched provider or a fixture's own connection is not test-level evidence. The static patch
detection does not reach every way a fixture applies (imported fixtures, base classes, pytest_plugins, the root
conftest.py, MonkeyPatch.context, code inside a child's command string), and who sent a request over a socket is not on
any call stack. RED target: git archive 20d2139 plugins/vmodel (the reviewer's probes, re-run): each shape below is
Test-level Verified and G6 PASSED there.
D48 adds two minimal run-time protections instead of more static analysis:
- R1: when a provider function starts, the tracer checks the names the provider module defines; a name bound to a
  mock, to code from the test tree or from a string, or (for a plain def/class) to anything not from the provider
  file, is a patch observed in that test (policy A, any path).
- R2: a thread, pool work item or process started in the test by code the test did not request (an autouse or
  unrequested fixture) makes the thread/process evidence uncertain: then only the test's main-thread evidence counts.
"""
from __future__ import annotations

import unittest

from g6_base import RED, replace_function
from test_g6_policy import CHILD_ENV, EXPECTED, REQUEST, iface, level, server_fixture
from test_g6_review12 import SERVER_PROC_FIXTURE, R12Base

REAL_TOP = "lambda records: max(records, key=lambda r: (r['score'], r['name']))"
STATIC_012 = ("    f = tmp_path / 'scores.csv'\n    f.write_text('a,1\\nb,2\\n', encoding='utf-8')\n"
              "    assert main([str(f)]) == 0\n"
              f"    assert json.loads(capsys.readouterr().out) == {EXPECTED}\n")


class ResidualBase(R12Base):
    def blocked(self, r6: dict, rec: dict, tid: str = "TEST-012", iid: str = "IF-002") -> None:
        self.assertNotEqual(level(rec, iid, tid), "test_level", f"{RED} {iface(rec, iid)}")
        self.assertEqual(r6.get("status"), "BLOCKED", f"{RED} {r6}")

    def assert_test_level(self, r6: dict, rec: dict, tid: str = "TEST-012", iid: str = "IF-002") -> None:
        self.assertEqual((r6.get("status"), level(rec, iid, tid)), ("PASSED", "test_level"), iface(rec, iid))


class ResidualPatchRed(ResidualBase):
    """R1: a provider patch the static analysis cannot see, observed when the provider runs."""

    def test_A1_autouse_patch_fixture_imported_from_another_module(self):
        self.add_top_helper()
        (self.sb.root / "tests/integration/shared_fx.py").write_text(
            "import pytest\n\n\n@pytest.fixture(autouse=True)\ndef fake_top(monkeypatch):\n"
            f"    monkeypatch.setattr('pipeline.report._top', {REAL_TOP})\n", encoding="utf-8")
        t = self.itest.read_text(encoding="utf-8")
        self.itest.write_text(t.replace("import pytest\n", "import pytest\nfrom shared_fx import fake_top  # noqa: F401\n",
                                        1), encoding="utf-8")
        self.blocked(*self.go(None))

    def test_A2_autouse_patch_fixture_in_a_base_class(self):
        self.add_top_helper()
        replace_function(self.itest, "test_TEST_012_cli_main_reads_file",
                         "class _FakeBase:\n    @pytest.fixture(autouse=True)\n    def fake_top(self, monkeypatch):\n"
                         f"        monkeypatch.setattr('pipeline.report._top', {REAL_TOP})\n\n\n"
                         "class TestCli(_FakeBase):\n"
                         "    def test_TEST_012_cli_main_reads_file(self, tmp_path, capsys):\n"
                         + "".join("    " + ln + "\n" for ln in STATIC_012.splitlines()))
        self.blocked(*self.go(None))

    def test_A3_autouse_patch_fixture_from_pytest_plugins(self):
        self.add_top_helper()
        (self.sb.root / "tests/integration/plug_fx.py").write_text(
            "import pytest\n\n\n@pytest.fixture(autouse=True)\ndef fake_top(monkeypatch):\n"
            f"    monkeypatch.setattr('pipeline.report._top', {REAL_TOP})\n", encoding="utf-8")
        (self.sb.root / "conftest.py").write_text("pytest_plugins = ['tests.integration.plug_fx']\n", encoding="utf-8")
        self.blocked(*self.go(None))

    def test_A4_autouse_patch_fixture_in_the_root_conftest(self):
        self.add_top_helper()
        (self.sb.root / "conftest.py").write_text(
            "import pytest\n\n\n@pytest.fixture(autouse=True)\ndef fake_top(monkeypatch):\n"
            f"    monkeypatch.setattr('pipeline.report._top', {REAL_TOP})\n", encoding="utf-8")
        self.blocked(*self.go(None))

    def test_A5_module_scoped_autouse_monkeypatch_context(self):
        self.add_top_helper()
        t = self.itest.read_text(encoding="utf-8")
        self.itest.write_text(t.replace(
            "\n\ndef test_TEST_010", "\n\n@pytest.fixture(autouse=True, scope='module')\ndef fake_top():\n"
            "    with pytest.MonkeyPatch.context() as mp:\n"
            f"        mp.setattr('pipeline.report._top', {REAL_TOP})\n        yield\n\n\ndef test_TEST_010", 1),
            encoding="utf-8")
        self.blocked(*self.go(None))

    def test_H4_patch_written_inside_the_childs_command(self):
        self.add_top_helper()
        self.module_imports()
        replace_function(self.itest, "test_TEST_012_cli_main_reads_file",
                         "def test_TEST_012_cli_main_reads_file(tmp_path):\n" + CHILD_ENV +
                         "    f = tmp_path / 'scores.csv'\n    f.write_text('a,1\\nb,2\\n', encoding='utf-8')\n"
                         "    code = ('import sys; import pipeline.report as r; r._top = lambda recs: {\"name\": \"b\"}; '\n"
                         "            'sys.exit(r.main([sys.argv[1]]))')\n"
                         "    res = subprocess.run([sys.executable, '-c', code, str(f)], capture_output=True, env=env,\n"
                         "                         check=True)\n"
                         f"    assert json.loads(res.stdout) == {EXPECTED}\n")
        self.blocked(*self.go("subprocess"))


class ResidualSenderRed(ResidualBase):
    """R2: the request reaching the test's server came from an autouse fixture's thread, not from the test."""

    def test_H3a_autouse_thread_sends_to_a_requested_thread_server(self):
        replace_function(self.itest, "test_TEST_012_cli_main_reads_file",
                         server_fixture(False) +
                         "@pytest.fixture(autouse=True)\ndef warmup():\n"
                         "    import threading\n    import time\n    import urllib.request\n\n"
                         "    def work():\n        time.sleep(0.4)\n"
                         "        url = f\"http://127.0.0.1:{SRV['s'].server_address[1]}/\"\n"
                         "        urllib.request.urlopen(url, data=b'a,1\\nb,2\\n', timeout=30).read()\n\n"
                         "    threading.Thread(target=work, daemon=True).start()\n    yield\n\n\n"
                         "def test_TEST_012_cli_main_reads_file(server):\n"
                         "    import time\n    import urllib.request\n"
                         "    req = urllib.request.Request(f'http://127.0.0.1:{server.server_address[1]}/')\n"
                         "    assert req.get_method() == 'GET'\n"
                         "    time.sleep(1.2)\n")
        self.blocked(*self.go("api"))

    def test_H3b_autouse_thread_sends_to_a_requested_server_process(self):
        self.module_imports()
        replace_function(self.itest, "test_TEST_012_cli_main_reads_file", SERVER_PROC_FIXTURE +
                         "@pytest.fixture(autouse=True)\ndef warmup():\n"
                         "    import threading\n    import time\n    import urllib.request\n\n"
                         "    def work():\n        time.sleep(1.0)\n"
                         "        url = f\"http://127.0.0.1:{PORT['p']}/\"\n"
                         "        urllib.request.urlopen(url, data=b'a,1\\nb,2\\n', timeout=30).read()\n\n"
                         "    threading.Thread(target=work, daemon=True).start()\n    yield\n\n\n"
                         "def test_TEST_012_cli_main_reads_file(server_port):\n"
                         "    import time\n    import urllib.request\n"
                         "    req = urllib.request.Request(f'http://127.0.0.1:{server_port}/')\n"
                         "    assert req.get_method() == 'GET'\n"
                         "    time.sleep(2.5)\n")
        self.blocked(*self.go("api"))


class ResidualControlChar(ResidualBase):
    """Legitimate shapes that must stay Test-level Verified (D48 must not block them)."""

    def test_decorated_provider_functions(self):
        rp = self.sb.root / "src/pipeline/report.py"
        t = rp.read_text(encoding="utf-8")
        t = t.replace("import json\n", "import functools\nimport json\n", 1).replace(
            "\n\ndef summarize(",
            "\n\ndef _logged(f):\n    @functools.wraps(f)\n    def wrapper(*args, **kwargs):\n"
            "        return f(*args, **kwargs)\n\n    return wrapper\n\n\n"
            "@functools.lru_cache(maxsize=None)\ndef _norm(name: str) -> str:\n    return name.strip()\n\n\n"
            "@_logged\ndef summarize(", 1).replace('"top": top["name"]}', '"top": _norm(top["name"])}', 1)
        assert "_norm(top" in t, t
        rp.write_text(t, encoding="utf-8")
        replace_function(self.itest, "test_TEST_012_cli_main_reads_file",
                         "def test_TEST_012_cli_main_reads_file(tmp_path, capsys):\n" + STATIC_012)
        self.assert_test_level(*self.go(None))

    def test_unrelated_autouse_thread_and_the_tests_direct_call(self):
        replace_function(self.itest, "test_TEST_012_cli_main_reads_file",
                         "@pytest.fixture(autouse=True)\ndef ticker():\n"
                         "    import threading\n    stop = threading.Event()\n"
                         "    t = threading.Thread(target=stop.wait, args=(5,), daemon=True)\n    t.start()\n"
                         "    yield\n    stop.set()\n\n\n"
                         "def test_TEST_012_cli_main_reads_file(tmp_path, capsys):\n" + STATIC_012)
        self.assert_test_level(*self.go(None))

    def test_requested_server_fixture_and_the_tests_own_request(self):
        replace_function(self.itest, "test_TEST_012_cli_main_reads_file",
                         server_fixture(False) + "def test_TEST_012_cli_main_reads_file(server):\n" + REQUEST)
        self.assert_test_level(*self.go("api"))

    def test_requested_server_process_fixture_and_the_tests_own_request(self):
        self.module_imports()
        replace_function(self.itest, "test_TEST_012_cli_main_reads_file", SERVER_PROC_FIXTURE +
                         "def test_TEST_012_cli_main_reads_file(server_port):\n"
                         "    import urllib.request\n"
                         "    url = f'http://127.0.0.1:{server_port}/'\n"
                         "    with urllib.request.urlopen(url, data=b'a,1\\nb,2\\n', timeout=30) as resp:\n"
                         f"        assert json.loads(resp.read()) == {EXPECTED}\n")
        self.assert_test_level(*self.go("api"))


if __name__ == "__main__":
    unittest.main()

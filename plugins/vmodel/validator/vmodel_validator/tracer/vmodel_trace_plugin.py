"""VModel DevKit pytest plugin for G6 (0.2.0, review 5). Part of the Validator Core.

G6 loads it with PYTEST_PLUGINS=vmodel_trace_plugin (explicitly named plugins load even with plugin autoload off) next
to the runtime tracer. It only observes: at the start of every test's setup, call and teardown and at the end of the
test it asks the tracer (sitecustomize in this directory) to write a boundary line with the wall-clock time, so the
validator can tell whether a line written by a child process belongs to that test's call. Any problem is swallowed.
"""
import os
import sys

import pytest

# loaded: children of the test run must not inherit the setting (a nested pytest with its own PYTHONPATH cannot import
# this module; review 6 M4). The validator's environment drops any PYTEST_* of the agent, so the value is ours.
if os.environ.get("PYTEST_PLUGINS") == "vmodel_trace_plugin":
    del os.environ["PYTEST_PLUGINS"]


def _mark(nodeid, phase):
    try:
        mark = getattr(sys.modules.get("sitecustomize"), "_vmodel_boundary", None)
        if mark is not None:
            mark(nodeid, phase)
    except Exception:
        pass


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_setup(item):
    _mark(item.nodeid, "setup")


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_call(item):
    _mark(item.nodeid, "call")


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_teardown(item):
    _mark(item.nodeid, "teardown")


@pytest.hookimpl(trylast=True)
def pytest_runtest_logfinish(nodeid, location):
    _mark(nodeid, "end")


@pytest.hookimpl(optionalhook=True)
def pytest_xdist_setupnodes(config, specs):
    """pytest-xdist workers are pytest processes too: they must load this plugin to write their tests' boundaries
    (review 7 R3). Each worker removes the setting again when it imports this module."""
    os.environ["PYTEST_PLUGINS"] = "vmodel_trace_plugin"

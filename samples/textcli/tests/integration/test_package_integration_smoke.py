import importlib


def test_package_reloads():
    mod = importlib.import_module("textcli")
    assert importlib.reload(mod).__doc__

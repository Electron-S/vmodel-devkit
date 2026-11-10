import importlib


def test_package_is_importable_from_the_source_tree():
    assert importlib.import_module("orderdesk").__name__ == "orderdesk"

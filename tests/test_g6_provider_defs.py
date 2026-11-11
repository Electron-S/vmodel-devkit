"""D48 R1: which provider-module names the run-time patch check watches (gates._provider_defs).

Names imported from outside the provider component (another component, an external library) are dependencies: a test
may stub them (Case F stubs report.parse while verifying IF-002) and that stays a G4 warning (D44 item 2, review 8 P1).
Names the module binds itself, and names imported from a module of the same provider component, are the provider's own
code: replacing them with test code is a patch (review 26 shape: `_fmt = _Fmt()` replaced by a test fake).
"""
from __future__ import annotations

import ast
import importlib
import sys
import unittest
from types import SimpleNamespace

from helpers import PLUGIN


def gates_module():
    sys.path.insert(0, str(PLUGIN / "validator"))
    try:
        for m in [m for m in sys.modules if m == "vmodel_validator" or m.startswith("vmodel_validator.")]:
            del sys.modules[m]
        return importlib.import_module("vmodel_validator.gates")
    finally:
        sys.path.remove(str(PLUGIN / "validator"))


class ProviderDefsAccept(unittest.TestCase):
    def test_imports_from_the_same_component_are_watched(self):
        gates = gates_module()
        tree = ast.parse("def run():\n    pass\n")
        mod = SimpleNamespace(functions={"run": tree.body[0]}, classes={}, tree=tree, bindings={
            "run": ("def", tree.body[0]),
            "helper": ("import", ("src", "src/p/impl.py", ("helper",))),
            "parse": ("import", ("src", "src/other/parser.py", ("parse",))),
            "requests": ("import", ("dotted", "requests")),
            "_fmt": ("alias", None)})
        ix = SimpleNamespace(modules={"src/p/api.py": mod})
        d = gates._provider_defs(ix, "src/p/api.py", {"src/p/api.py", "src/p/impl.py"})
        self.assertEqual(d["imported"], ["parse", "requests"])
        self.assertEqual(d["strict"], ["run"])
        d2 = gates._provider_defs(ix, "src/p/api.py", {"src/p/api.py"})
        self.assertEqual(d2["imported"], ["helper", "parse", "requests"])


if __name__ == "__main__":
    unittest.main()

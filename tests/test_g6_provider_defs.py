"""D48 R1: which provider-module names the run-time patch check watches (gates._provider_defs).

Names imported from outside the provider component (another component, an external library) are dependencies: a test
may stub them (Case F stubs report.parse while verifying IF-002) and that stays a G4 warning (D44 item 2, review 8 P1).
Names the module binds itself, and names imported from a module of the same provider component, are the provider's own
code: replacing them with test code is a patch (review 26 shape: `_fmt = _Fmt()` replaced by a test fake).

Review 28 (f3c1cbb): the static index keeps an absolute import as ("dotted", name) - only relative imports become
("src", ...) - so f3c1cbb excluded `from pipeline.fmt import fmt`, `from pipeline import fmt` and `import pipeline.fmt
as m` from the same component too; a test fake replacing one ran as Test-level. RED target: git archive f3c1cbb
plugins/vmodel. The class below builds a real index instead of hand-written binding shapes.
"""
from __future__ import annotations

import ast
import importlib
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from g6_base import RED
from helpers import PLUGIN

API = """import json
import pipeline.fmt
import pipeline.fmt as abs_mod
from pipeline.fmt import fmt as abs_fmt
from pipeline import fmt as pkg_fmt
from . import fmt as rel_mod
from .fmt import fmt as rel_fmt
from other.parser import parse
from other import parser as other_mod


def run(x):
    return abs_fmt(parse(x))
"""


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
        ix = SimpleNamespace(modules={"src/p/api.py": mod},
                             normal=lambda tgt: ("ext", tgt[1]) if tgt[0] == "dotted" else tgt)
        d = gates._provider_defs(ix, "src/p/api.py", {"src/p/api.py", "src/p/impl.py"})
        self.assertEqual(d["imported"], ["parse", "requests"])
        self.assertEqual(d["strict"], ["run"])
        d2 = gates._provider_defs(ix, "src/p/api.py", {"src/p/api.py"})
        self.assertEqual(d2["imported"], ["helper", "parse", "requests"])



class ProviderDefsAbsoluteImportRed(unittest.TestCase):
    def test_absolute_imports_from_the_same_component_are_watched(self):
        gates = gates_module()
        wiring = sys.modules["vmodel_validator.wiring"]
        root = Path(tempfile.mkdtemp(prefix="vmodel-pdefs-"))
        try:
            files = {"src/pipeline/__init__.py": "", "src/pipeline/api.py": API,
                     "src/pipeline/fmt.py": "def fmt(x):\n    return x\n", "src/other/__init__.py": "",
                     "src/other/parser.py": "def parse(x):\n    return x\n"}
            for rel, text in files.items():
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
                (root / rel).write_text(text, encoding="utf-8")
            src = [root / rel for rel in files]
            ix = wiring.Index.build(root, lambda f: f.relative_to(root).as_posix(), src, [], {})
            d = gates._provider_defs(ix, "src/pipeline/api.py", {"src/pipeline/api.py", "src/pipeline/fmt.py"})
            # outside the component (not checked): the stdlib, another component, the package object itself
            self.assertEqual(d["imported"], ["json", "other_mod", "parse", "pipeline"], f"{RED} {d}")
        finally:
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()

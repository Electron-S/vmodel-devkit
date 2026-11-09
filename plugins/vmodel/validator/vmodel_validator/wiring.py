"""Static integration analysis for G4.INTEGRATION_WIRING and G6.IF_COVERAGE (0.2.0, REQ-G6-11', 29, 30).

Python only, an approximation by design (docs/g6/WORKITEM.md section 4.1):
- reach starts only at *calls* in the test function (plus same-file helpers, functions of other test modules and the
  pytest fixtures it requests, depth 3); importing or referencing a module is not a call (import-only tests do not
  reach anything);
- reach = the static import closure of the source modules called;
- a test without a static call path but with a subprocess / IPC / API / dynamic-import call is a runtime-path
  candidate (path B): the verifier declares it at G4 and G6 proves it with the runtime trace;
- a test (with what it follows) without any call is a placeholder.
"""
from __future__ import annotations

import ast
import builtins
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .trace import test_ids_in_text

MAX_DEPTH = 3
# fully qualified call name prefixes -> runtime integration mechanism kind (path B)
MECHANISMS: tuple[tuple[str, str], ...] = (
    ("subprocess.", "subprocess"), ("os.system", "subprocess"), ("os.popen", "subprocess"),
    ("os.spawn", "subprocess"), ("os.exec", "subprocess"), ("os.posix_spawn", "subprocess"),
    ("asyncio.create_subprocess_", "subprocess"), ("pty.spawn", "subprocess"),
    ("multiprocessing.", "ipc"), ("concurrent.futures.ProcessPoolExecutor", "ipc"), ("socket.", "ipc"),
    ("asyncio.open_connection", "ipc"), ("asyncio.open_unix_connection", "ipc"),
    ("http.client.", "api"), ("urllib.request.", "api"), ("requests.", "api"), ("httpx.", "api"),
    ("xmlrpc.client.", "api"), ("aiohttp.", "api"),
    ("importlib.import_module", "dynamic_import"), ("importlib.__import__", "dynamic_import"),
    ("__import__", "dynamic_import"), ("runpy.", "dynamic_import"),
)
KINDS = ("subprocess", "ipc", "api", "dynamic_import")
PATCHERS = {"unittest.mock.patch", "mock.patch", "unittest.mock.patch.object", "mock.patch.object",
            "unittest.mock.patch.dict", "pytest.MonkeyPatch.setattr"}
SIG_RE = re.compile(r"\b(?:async\s+def|def|class)\s+([A-Za-z_][A-Za-z0-9_]*)")
BUILTIN_NAMES = set(dir(builtins))


def signature_symbol(signature: Any) -> str | None:
    m = SIG_RE.search(signature) if isinstance(signature, str) else None
    return m.group(1) if m else None


def module_name(project_root: Path, path: Path) -> str:
    """Dotted import name: the path below the deepest ancestor directory without __init__.py."""
    parts = [] if path.name == "__init__.py" else [path.stem]
    d = path.parent
    root = project_root.resolve()
    while (d / "__init__.py").is_file() and d.resolve() != root:
        parts.insert(0, d.name)
        d = d.parent
    if path.name == "__init__.py" and not parts:
        parts = [path.parent.name]
    return ".".join(parts)


def _longest_module(name: str, index: dict[str, Any]) -> str | None:
    parts = name.split(".")
    for i in range(len(parts), 0, -1):
        cand = ".".join(parts[:i])
        if cand in index:
            return cand
    return None


def _resolve_relative(modname: str, is_pkg: bool, level: int, target: str | None) -> str:
    base = modname.split(".") if is_pkg else modname.split(".")[:-1]
    if level > 1:
        base = base[: max(0, len(base) - (level - 1))]
    return ".".join([*base, *(target.split(".") if target else [])])


def import_table(tree: ast.AST, modname: str = "", is_pkg: bool = False) -> dict[str, str]:
    """Local name -> fully qualified name, from the module's top-level and nested import statements."""
    table: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.asname:
                    table[a.asname] = a.name
                else:
                    table[a.name.split(".")[0]] = a.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom):
            base = _resolve_relative(modname, is_pkg, node.level, node.module) if node.level else (node.module or "")
            for a in node.names:
                if a.name != "*":
                    table[a.asname or a.name] = f"{base}.{a.name}" if base else a.name
    return table


@dataclass
class Module:
    name: str
    rel: str
    tree: ast.AST
    imports: dict[str, str]
    functions: dict[str, ast.AST]  # top-level functions and Class.method
    fixtures: dict[str, ast.AST]


def _functions(tree: ast.AST) -> dict[str, ast.AST]:
    out: dict[str, ast.AST] = {}
    for node in getattr(tree, "body", []):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out[node.name] = node
        elif isinstance(node, ast.ClassDef):
            for n in node.body:
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    out[f"{node.name}.{n.name}"] = n
    return out


def _is_fixture(fn: ast.AST) -> bool:
    for d in getattr(fn, "decorator_list", []):
        target = d.func if isinstance(d, ast.Call) else d
        name = target.attr if isinstance(target, ast.Attribute) else getattr(target, "id", "")
        if name == "fixture":
            return True
    return False


def _module(project_root: Path, rel: str, path: Path, tree: ast.AST) -> Module:
    name = module_name(project_root, path)
    funcs = _functions(tree)
    return Module(name, rel, tree, import_table(tree, name, path.name == "__init__.py"), funcs,
                  {k: v for k, v in funcs.items() if "." not in k and _is_fixture(v)})


@dataclass
class Index:
    root: Path
    source: dict[str, Module] = field(default_factory=dict)  # import name -> module
    tests: dict[str, Module] = field(default_factory=dict)  # test module import name -> module
    by_rel: dict[str, Module] = field(default_factory=dict)
    graph: dict[str, set[str]] = field(default_factory=dict)

    @staticmethod
    def build(project_root: Path, rel_of, source: list[Path], tests: list[Path], trees: dict[str, ast.AST]) -> "Index":
        ix = Index(project_root)
        for group, files in ((ix.source, source), (ix.tests, tests)):
            for f in files:
                rel = rel_of(f)
                tree = trees.get(rel)
                if tree is None:
                    try:
                        tree = ast.parse(f.read_bytes(), filename=rel)
                    except (SyntaxError, ValueError, OSError, RecursionError, MemoryError):
                        continue
                m = _module(project_root, rel, f, tree)
                group.setdefault(m.name, m)
                ix.by_rel[rel] = m
        for name, m in ix.source.items():
            deps: set[str] = set()
            for q in m.imports.values():
                hit = _longest_module(q, ix.source)
                if hit and hit != name:
                    deps.add(hit)
            ix.graph[name] = deps
        return ix

    def closure(self, start: set[str]) -> set[str]:
        seen, todo = set(), list(start)
        while todo:
            m = todo.pop()
            if m in seen:
                continue
            seen.add(m)
            todo.extend(self.graph.get(m, ()))
        return seen

    def conftest_fixtures(self, test_rel: str) -> dict[str, tuple[Module, ast.AST]]:
        """Fixtures from conftest.py files in the test file's directory and its ancestors (nearest wins)."""
        out: dict[str, tuple[Module, ast.AST]] = {}
        parts = test_rel.split("/")[:-1]
        for i in range(len(parts), -1, -1):
            rel = "/".join([*parts[:i], "conftest.py"])
            m = self.by_rel.get(rel)
            if m:
                for k, v in m.fixtures.items():
                    out.setdefault(k, (m, v))
        return out


def qualify(expr: ast.AST, imports: dict[str, str]) -> str | None:
    if isinstance(expr, ast.Name):
        if expr.id in imports:
            return imports[expr.id]
        return expr.id if expr.id in BUILTIN_NAMES else None
    if isinstance(expr, ast.Attribute):
        base = qualify(expr.value, imports)
        return f"{base}.{expr.attr}" if base else None
    return None


@dataclass
class Analysis:
    calls: int = 0
    source_calls: set[str] = field(default_factory=set)  # source modules called directly or via helpers/fixtures
    mechanisms: list[dict] = field(default_factory=list)
    patches: list[dict] = field(default_factory=list)


def _mechanism(qn: str) -> str | None:
    for prefix, kind in MECHANISMS:
        if qn == prefix.rstrip(".") or qn.startswith(prefix):
            return kind
    return None


def _str_arg(call: ast.Call, i: int) -> str | None:
    if len(call.args) > i and isinstance(call.args[i], ast.Constant) and isinstance(call.args[i].value, str):
        return call.args[i].value
    return None


def _patch_target(call: ast.Call, qn: str | None, imports: dict[str, str]) -> str | None:
    is_mp = isinstance(call.func, ast.Attribute) and call.func.attr in ("setattr", "delattr") and \
        isinstance(call.func.value, ast.Name) and call.func.value.id == "monkeypatch"
    if not (is_mp or (qn and (qn in PATCHERS or qn.endswith((".patch", ".patch.object"))))):
        return None
    s = _str_arg(call, 0)
    if s is not None:
        return s
    obj = qualify(call.args[0], imports) if call.args else None
    attr = _str_arg(call, 1)
    return f"{obj}.{attr}" if obj and attr else obj


def analyze(ix: Index, mod: Module, fn: ast.AST, depth: int = 0, seen: set | None = None,
            out: Analysis | None = None) -> Analysis:
    out = out or Analysis()
    seen = seen if seen is not None else set()
    key = (mod.rel, getattr(fn, "name", "?"), getattr(fn, "lineno", 0))
    if key in seen:
        return out
    seen.add(key)
    fixtures = {**ix.conftest_fixtures(mod.rel), **{k: (mod, v) for k, v in mod.fixtures.items()}}
    params = [a.arg for a in [*getattr(fn.args, "posonlyargs", []), *fn.args.args, *fn.args.kwonlyargs]] \
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) else []
    if depth < MAX_DEPTH:  # requested fixtures run as part of the test
        for p in params:
            if p in fixtures and fixtures[p][1] is not fn:
                fm, ff = fixtures[p]
                analyze(ix, fm, ff, depth + 1, seen, out)
    nodes = [*getattr(fn, "decorator_list", []), *getattr(fn, "body", [])]
    nested: dict[str, ast.AST] = {}
    for node in _own_nodes(nodes):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            nested[node.name] = node
    for node in _own_nodes(nodes):
        if not isinstance(node, ast.Call):
            continue
        out.calls += 1
        qn = qualify(node.func, mod.imports)
        target = _patch_target(node, qn, mod.imports)
        if target:
            out.patches.append({"target": target, "line": node.lineno})
        if qn:
            kind = _mechanism(qn)
            if kind:
                out.mechanisms.append({"kind": kind, "call": qn, "line": node.lineno})
            src = _longest_module(qn, ix.source)
            if src:
                out.source_calls.add(src)
            tm = _longest_module(qn, ix.tests)
            if tm and depth < MAX_DEPTH:
                other = ix.tests[tm]
                fname = qn[len(tm) + 1:]
                if fname in other.functions:
                    analyze(ix, other, other.functions[fname], depth + 1, seen, out)
        if isinstance(node.func, ast.Name) and node.func.id not in mod.imports and depth < MAX_DEPTH:
            name = node.func.id
            if name in params and name in fixtures:  # a fixture returning a callable
                fm, ff = fixtures[name]
                for r in ast.walk(ff):
                    if isinstance(r, ast.Return) and r.value is not None:
                        rq = qualify(r.value, fm.imports)
                        src = _longest_module(rq, ix.source) if rq else None
                        if src:
                            out.source_calls.add(src)
            elif name in nested:  # a function defined inside the test and called by it
                analyze(ix, mod, nested[name], depth + 1, seen, out)
            elif name in mod.functions:  # a helper of the same module
                analyze(ix, mod, mod.functions[name], depth + 1, seen, out)
    return out


def _own_nodes(roots: list[ast.AST]):
    """The nodes the function itself executes: nested def/class/lambda bodies are not entered (their calls count only
    when the test calls them by name), so an unused nested function cannot make a placeholder look like a call."""
    todo = list(reversed(roots))
    while todo:
        node = todo.pop()
        yield node
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            todo.extend(reversed([*node.decorator_list, *getattr(node.args, "defaults", []),
                                  *getattr(node.args, "kw_defaults", [])] if not isinstance(node, ast.ClassDef)
                                 else [*node.decorator_list, *node.bases, *node.keywords]))
            continue
        if isinstance(node, ast.Lambda):
            continue
        todo.extend(reversed(list(ast.iter_child_nodes(node))))


def provider_symbols(iface: dict, units: list[dict]) -> set[str]:
    syms = {u.get("name", "").split(".")[-1] for u in units if u.get("component") == iface.get("provider")}
    s = signature_symbol(iface.get("signature"))
    return {x for x in (syms | ({s} if s else set())) if x}


def classify(ix: Index, analysis: Analysis, provider_mods: set[str], consumer_mods: set[str] | None,
             symbols: set[str]) -> dict:
    """One (test function, interface) pair. consumer_mods None = no ARCH consumer (EXTERNAL only)."""
    reach = ix.closure(set(analysis.source_calls))
    rp = bool(reach & provider_mods)
    rc = True if consumer_mods is None else bool(reach & consumer_mods)
    patched = sorted({p["target"] for p in analysis.patches
                      if _longest_module(p["target"], ix.source) in provider_mods
                      or p["target"].split(".")[-1] in symbols})
    if rp and rc:
        path = "static"
    elif analysis.mechanisms:
        path = "runtime_candidate"
    elif analysis.calls == 0:
        path = "placeholder"
    else:
        path = "none"
    return {"path": path, "reaches_provider": rp, "reaches_consumer": rc, "patched_provider": patched,
            "mechanisms": sorted({m["kind"] for m in analysis.mechanisms}),
            "calls_source": sorted(analysis.source_calls), "placeholder": analysis.calls == 0}


def integration_functions(ix: Index, test_rels: list[str], wanted: set[str]) -> dict[str, list[tuple[Module, str]]]:
    """TEST id -> [(module, function name)] for test functions whose name carries exactly that one id."""
    out: dict[str, list[tuple[Module, str]]] = {}
    for rel in test_rels:
        m = ix.by_rel.get(rel)
        if m is None:
            continue
        for name, fn in m.functions.items():
            leaf = name.split(".")[-1]
            if not leaf.startswith("test") or ("." in name and not name.startswith("Test")):
                continue
            ids = test_ids_in_text(name)
            if len(ids) == 1 and (tid := next(iter(ids))) in wanted:
                out.setdefault(tid, []).append((m, name))
    return out


def unit_modules(project_rel_source: dict[str, str], units: list[dict], component: str) -> set[str]:
    """Import names of the design-unit modules of a component (rel path -> import name map)."""
    return {project_rel_source[u["module"].replace("\\", "/")] for u in units
            if u.get("component") == component and isinstance(u.get("module"), str)
            and u["module"].replace("\\", "/") in project_rel_source}


def interface_wiring(ix: Index, graph, test_rels: list[str]) -> dict:
    """Per interface and integration test: the classification of every function carrying that TEST id.

    Returns {"interfaces": {IF: {...}}, "tests": {TEST: [function view]}}, the data both G4 and G6 judge from.
    """
    units = list(graph.units.values())
    rel_to_name = {m.rel: name for name, m in ix.source.items()}
    integ = {tid for tid, t in graph.tests.items() if t.get("level") == "integration"}
    funcs = integration_functions(ix, test_rels, integ)
    analyses: dict[tuple[str, str], Analysis] = {}
    tests_view: dict[str, list[dict]] = {}
    for tid, fl in sorted(funcs.items()):
        for m, name in fl:
            a = analyze(ix, m, m.functions[name])
            analyses[(m.rel, name)] = a
            tests_view.setdefault(tid, []).append({"function": f"{m.rel}::{name}", "file": m.rel,
                                                   "placeholder": a.calls == 0,
                                                   "mechanisms": sorted({x["kind"] for x in a.mechanisms}),
                                                   "calls_source": sorted(a.source_calls)})
    ifs: dict[str, dict] = {}
    for iid, iface in sorted(graph.ifaces.items()):
        prov = unit_modules(rel_to_name, units, str(iface.get("provider")))
        arch_cons = [c for c in iface.get("consumers") or [] if isinstance(c, str) and c != "EXTERNAL"]
        cons = set().union(*(unit_modules(rel_to_name, units, c) for c in arch_cons)) if arch_cons else None
        syms = provider_symbols(iface, units)
        tests: dict[str, dict] = {}
        for tid in sorted(t for t in integ if iid in (graph.tests[t].get("verifies") or [])):
            views = []
            for m, name in funcs.get(tid, []):
                c = classify(ix, analyses[(m.rel, name)], prov, cons, syms)
                views.append({"function": f"{m.rel}::{name}", "file": m.rel, **c})
            rank = {"static": 0, "runtime_candidate": 1, "none": 2, "placeholder": 3}
            best = min(views, key=lambda v: rank[v["path"]]) if views else None
            tests[tid] = {"functions": views, "path": best["path"] if best else "missing",
                          "best": best, "any_placeholder": any(v["placeholder"] for v in views)}
        ifs[iid] = {"provider": iface.get("provider"), "consumers": iface.get("consumers") or [],
                    "provider_modules": sorted(prov), "consumer_modules": sorted(cons) if cons is not None else None,
                    "provider_symbols": sorted(syms), "tests": tests}
    return {"interfaces": ifs, "tests": tests_view}

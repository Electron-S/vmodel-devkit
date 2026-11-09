"""Static integration analysis for G4.INTEGRATION_WIRING and G6.IF_COVERAGE (0.2.0, REQ-G6-11', 29, 30, D42).

Python only, an approximation by design (docs/g6/WORKITEM.md section 4.1). Modules are identified by their file
(project-relative path); a file is importable under every dotted suffix of its path that no other file claims, so src
layouts, namespace packages (no __init__.py) and `src.`-style imports resolve alike.

- Reach starts only at *calls* the test makes: a call counts when its callee resolves, after the test's own local
  scope (parameters, assignments, nested defs, local imports), to a module-level def/class of a source module (or a
  method of such a class), following package re-exports. Referencing a module or calling something reached through
  an attribute of a symbol (`report.__name__.endswith(...)`) is not a call of it.
- Followed (depth 3): same-module helpers, functions of other test modules, nested defs and lambdas the test calls,
  lambdas passed as call arguments, `self.<method>` of the test class, setUp/setup_method, requested pytest fixtures
  (not overridden by parametrize) and callables they return, `self.x = ...` aliases set in setUp.
- Dependency injection: a source def/class passed as an argument to a call into a source module counts as reached.
- reach = the static import closure (all imports, including function-local ones) of the source modules reached.
- No static call path but a subprocess / IPC / API / dynamic-import call: a runtime-path candidate (path B), declared
  by the verifier at G4 and proven by the runtime trace at G6. No call at all: placeholder.
"""
from __future__ import annotations

import ast
import builtins
import posixpath
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
            "unittest.mock.patch.dict"}
SETUP_METHODS = ("setUp", "setup_method")
SIG_RE = re.compile(r"\b(?:async\s+def|def|class)\s+([A-Za-z_][A-Za-z0-9_]*)")
BUILTIN_NAMES = set(dir(builtins))
FUNC = (ast.FunctionDef, ast.AsyncFunctionDef)


def signature_symbol(signature: Any) -> str | None:
    m = SIG_RE.search(signature) if isinstance(signature, str) else None
    return m.group(1) if m else None


def _ids(value: Any) -> list[str]:
    """Agent-written id lists may have any JSON shape; keep only strings."""
    return [x for x in value if isinstance(x, str)] if isinstance(value, list) else []


# ---------------------------------------------------------------- modules
def _parts(rel: str) -> list[str]:
    p = rel[:-3].split("/") if rel.endswith(".py") else rel.split("/")
    return p[:-1] if p and p[-1] == "__init__" else p


def canonical_name(project_root: Path, rel: str) -> str:
    """The dotted name below the deepest ancestor directory without __init__.py (the usual import name)."""
    parts = _parts(rel)
    if not parts:
        return ""
    path = project_root / rel
    d = path.parent if path.name != "__init__.py" else path.parent.parent
    keep = 1
    root = project_root.resolve()
    while keep < len(parts) and (d / "__init__.py").is_file() and d.resolve() != root:
        keep += 1
        d = d.parent
    return ".".join(parts[-keep:])


@dataclass
class Module:
    rel: str
    tree: ast.AST
    functions: dict[str, ast.AST]  # top-level functions and Class.method
    classes: dict[str, ast.ClassDef]
    imports: dict[str, tuple] = field(default_factory=dict)  # module-level bindings: name -> target
    stars: list[tuple] = field(default_factory=list)  # targets of `from x import *`
    aliases: dict[str, ast.AST] = field(default_factory=dict)  # module-level NAME = <expr>
    fixtures: dict[str, ast.AST] = field(default_factory=dict)
    deps: set[str] = field(default_factory=set)  # rels this module imports (anywhere in the file)


def _functions(tree: ast.AST) -> tuple[dict[str, ast.AST], dict[str, ast.ClassDef]]:
    out: dict[str, ast.AST] = {}
    classes: dict[str, ast.ClassDef] = {}
    for node in getattr(tree, "body", []):
        if isinstance(node, FUNC):
            out[node.name] = node
        elif isinstance(node, ast.ClassDef):
            classes[node.name] = node
            for n in node.body:
                if isinstance(n, FUNC):
                    out[f"{node.name}.{n.name}"] = n
    return out, classes


def _is_fixture(fn: ast.AST) -> bool:
    for d in getattr(fn, "decorator_list", []):
        target = d.func if isinstance(d, ast.Call) else d
        name = target.attr if isinstance(target, ast.Attribute) else getattr(target, "id", "")
        if name == "fixture":
            return True
    return False


def _top_statements(tree: ast.AST):
    """Module-level statements, including those nested in top-level if/try/with blocks (not function bodies)."""
    todo = list(getattr(tree, "body", []))
    while todo:
        node = todo.pop(0)
        yield node
        if isinstance(node, (ast.If, ast.Try, ast.With, ast.AsyncWith)) or type(node).__name__ == "TryStar":
            for key in ("body", "orelse", "finalbody", "handlers"):
                for x in getattr(node, key, []) or []:
                    todo.extend(x.body if isinstance(x, ast.ExceptHandler) else [x])


@dataclass
class Index:
    root: Path
    modules: dict[str, Module] = field(default_factory=dict)  # rel -> module (source and tests)
    source: set[str] = field(default_factory=set)  # rels of source modules
    tests: set[str] = field(default_factory=set)
    names: dict[str, str] = field(default_factory=dict)  # dotted import name -> rel

    @staticmethod
    def build(project_root: Path, rel_of, source: list[Path], tests: list[Path], trees: dict[str, ast.AST]) -> "Index":
        ix = Index(project_root)
        claims: dict[str, set[str]] = {}
        canonical: dict[str, str] = {}
        for group, files in ((ix.source, source), (ix.tests, tests)):
            for f in files:
                rel = rel_of(f)
                if rel in ix.modules:
                    continue
                tree = trees.get(rel)
                if tree is None:
                    try:
                        tree = ast.parse(f.read_bytes(), filename=rel)
                    except (SyntaxError, ValueError, OSError, RecursionError, MemoryError):
                        continue
                funcs, classes = _functions(tree)
                ix.modules[rel] = Module(rel, tree, funcs, classes)
                group.add(rel)
                parts = _parts(rel)
                for i in range(len(parts)):
                    claims.setdefault(".".join(parts[i:]), set()).add(rel)
                canonical[rel] = canonical_name(project_root, rel)
        for name, rels in claims.items():
            if len(rels) == 1:
                ix.names[name] = next(iter(rels))
            else:  # ambiguous suffix: only the file whose usual import name it is keeps it
                owners = [r for r in rels if canonical[r] == name]
                if len(owners) == 1:
                    ix.names[name] = owners[0]
        for m in ix.modules.values():
            ix._bind_module(m)
        return ix

    # ---- name resolution --------------------------------------------
    def resolve_dotted(self, dotted: str) -> tuple:
        parts = dotted.split(".")
        for i in range(len(parts), 0, -1):
            rel = self.names.get(".".join(parts[:i]))
            if rel is not None:
                return ("src", rel, tuple(parts[i:]))
        return ("ext", dotted)

    def _relative(self, rel: str, level: int, target: str | None) -> tuple | None:
        base = posixpath.dirname(rel)
        for _ in range(level - 1):
            base = posixpath.dirname(base)
        parts = [p for p in (target or "").split(".") if p]
        for i in range(len(parts), -1, -1):
            stem = posixpath.join(base, *parts[:i]) if (base or parts[:i]) else ""
            for cand in (f"{stem}.py" if stem else None, posixpath.join(stem, "__init__.py") if stem else "__init__.py"):
                if cand and cand in self.modules:
                    return ("src", cand, tuple(parts[i:]))
        return None

    def import_targets(self, m: Module, node: ast.AST) -> list[tuple[str, tuple]]:
        out: list[tuple[str, tuple]] = []
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.asname:
                    out.append((a.asname, ("dotted", a.name)))
                else:
                    out.append((a.name.split(".")[0], ("dotted", a.name.split(".")[0])))
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = self._relative(m.rel, node.level, node.module)
                for a in node.names:
                    if base is None:
                        continue
                    if a.name == "*":
                        out.append(("*", base))
                        continue
                    sub = self._relative(m.rel, node.level, ".".join(x for x in (node.module, a.name) if x))
                    tgt = sub if sub is not None and not sub[2] else ("src", base[1], (*base[2], a.name))
                    out.append((a.asname or a.name, tgt))
            else:
                for a in node.names:
                    if a.name == "*":
                        out.append(("*", ("dotted", node.module or "")))
                    else:
                        out.append((a.asname or a.name, ("dotted", f"{node.module}.{a.name}" if node.module else a.name)))
        return out

    def _bind_module(self, m: Module) -> None:
        for node in _top_statements(m.tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for name, tgt in self.import_targets(m, node):
                    if name == "*":
                        m.stars.append(tgt)
                    else:
                        m.imports[name] = tgt
            elif isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                m.aliases[node.targets[0].id] = node.value
            elif isinstance(node, FUNC) and _is_fixture(node):
                m.fixtures[node.name] = node
        for node in ast.walk(m.tree):  # dependencies: every import, including lazy ones inside functions
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for _name, tgt in self.import_targets(m, node):
                    t = self.normal(tgt)
                    if t and t[0] == "src":
                        if t[1] != m.rel:
                            m.deps.add(t[1])
                        if t[2]:  # `from pkg import submodule` / `import pkg.sub`
                            sub = self.resolve_dotted(".".join([*_parts(t[1]), *t[2]]))
                            if sub[0] == "src" and sub[1] != m.rel:
                                m.deps.add(sub[1])
                    if isinstance(node, ast.Import) and t and t[0] == "src":
                        for a in node.names:  # import pkg.sub binds pkg but loads pkg.sub
                            full = self.resolve_dotted(a.name)
                            if full[0] == "src" and full[1] != m.rel:
                                m.deps.add(full[1])

    def normal(self, tgt: tuple | None) -> tuple | None:
        if tgt is None:
            return None
        if tgt[0] == "dotted":
            return self.resolve_dotted(tgt[1])
        return tgt

    def closure(self, start: set[str]) -> set[str]:
        seen, todo = set(), list(start)
        while todo:
            r = todo.pop()
            if r in seen or r not in self.source:
                continue
            seen.add(r)
            todo.extend(self.modules[r].deps)
        return seen

    def symbol(self, tgt: tuple | None, depth: int = 0) -> tuple[str, tuple] | None:
        """(source rel, symbol path) when tgt names a module-level def/class (or a method of such a class) of a
        source module, following package re-exports and submodule attributes; None for modules, attributes of
        symbols and anything external."""
        tgt = self.normal(tgt)
        if not tgt or tgt[0] != "src" or depth > 4:
            return None
        rel, path = tgt[1], tgt[2]
        m = self.modules.get(rel)
        if m is None or rel not in self.source or not path:
            return None
        head = path[0]
        if head in m.classes:
            if len(path) == 1 or (len(path) == 2 and f"{head}.{path[1]}" in m.functions):
                return rel, path
            return None
        if head in m.functions:
            return (rel, path) if len(path) == 1 else None
        if head in m.imports:  # re-export, e.g. `from .report import summarize` in a package __init__
            inner = self.normal(m.imports[head])
            if inner and inner[0] == "src":
                return self.symbol(("src", inner[1], (*inner[2], *path[1:])), depth + 1)
            return None
        sub = self.resolve_dotted(".".join([*_parts(rel), *path]))  # submodule attribute: pkg.sub.f
        if sub[0] == "src" and sub[1] != rel:
            return self.symbol(sub, depth + 1)
        return None

    def conftest_fixtures(self, test_rel: str) -> dict[str, tuple[Module, ast.AST]]:
        out: dict[str, tuple[Module, ast.AST]] = {}
        parts = test_rel.split("/")[:-1]
        for i in range(len(parts), -1, -1):
            m = self.modules.get("/".join([*parts[:i], "conftest.py"]))
            if m:
                for k, v in m.fixtures.items():
                    out.setdefault(k, (m, v))
        return out


# ---------------------------------------------------------------- function analysis
@dataclass
class Analysis:
    calls: int = 0
    source_calls: set[str] = field(default_factory=set)  # source rels reached by calls (and injected symbols)
    mechanisms: list[dict] = field(default_factory=list)
    patches: list[dict] = field(default_factory=list)


@dataclass
class Scope:
    """What names mean inside one function: local bindings shadow imports; local imports come before the module's."""
    locals: set[str] = field(default_factory=set)
    imports: dict[str, tuple] = field(default_factory=dict)
    aliases: dict[str, ast.AST] = field(default_factory=dict)  # local NAME = <Name|Attribute|Lambda>
    nested: dict[str, ast.AST] = field(default_factory=dict)
    fixtures: set[str] = field(default_factory=set)
    self_aliases: dict[str, ast.AST] = field(default_factory=dict)  # self.x = <expr> in setUp / setup_method
    cls: str | None = None


def _parametrized(fn: ast.AST) -> set[str]:
    out: set[str] = set()
    for d in getattr(fn, "decorator_list", []):
        if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.func.attr == "parametrize" and d.args:
            a = d.args[0]
            if isinstance(a, ast.Constant) and isinstance(a.value, str):
                out |= {x.strip() for x in a.value.split(",") if x.strip()}
            elif isinstance(a, (ast.List, ast.Tuple)):
                out |= {x.value for x in a.elts if isinstance(x, ast.Constant) and isinstance(x.value, str)}
    return out


def _walk_own(roots: list[ast.AST]):
    """(node, parent) for the nodes the function itself executes. Nested def/class/lambda bodies are not entered,
    except lambdas passed directly as call arguments (pytest.raises(E, lambda: f()))."""
    todo: list[tuple[ast.AST, ast.AST | None]] = [(r, None) for r in reversed(roots)]
    while todo:
        node, parent = todo.pop()
        yield node, parent
        if isinstance(node, (*FUNC, ast.ClassDef)):
            extra = [*node.decorator_list]
            if isinstance(node, ast.ClassDef):
                extra += [*node.bases, *node.keywords]
            else:
                extra += [*node.args.defaults, *[d for d in node.args.kw_defaults if d is not None]]
            todo.extend((x, node) for x in reversed(extra))
            continue
        if isinstance(node, ast.Lambda):
            if isinstance(parent, (ast.Call, ast.keyword)):
                todo.append((node.body, node))
            continue
        todo.extend((c, node) for c in reversed(list(ast.iter_child_nodes(node))))


def _scope(ix: Index, mod: Module, fn: ast.AST, cls: str | None) -> Scope:
    sc = Scope(cls=cls)
    args = fn.args if isinstance(fn, FUNC) else None
    if args is not None:
        named = [*args.posonlyargs, *args.args, *args.kwonlyargs]
        sc.locals |= {a.arg for a in [*named, *(a for a in (args.vararg, args.kwarg) if a is not None)]}
        sc.fixtures = {a.arg for a in named} - _parametrized(fn) - {"self", "cls"}
    for node, _parent in _walk_own(list(getattr(fn, "body", []))):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for name, tgt in ix.import_targets(mod, node):
                if name != "*":
                    sc.imports[name] = tgt
        elif isinstance(node, (*FUNC, ast.ClassDef)):
            sc.nested[node.name] = node
            sc.locals.add(node.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for t in targets:
                if isinstance(t, ast.Attribute):
                    continue
                sc.locals |= {n.id for n in ast.walk(t) if isinstance(n, ast.Name)}
                if isinstance(t, ast.Name) and isinstance(node, ast.Assign) and \
                        isinstance(node.value, (ast.Name, ast.Attribute, ast.Lambda)):
                    sc.aliases[t.id] = node.value
        elif isinstance(node, (ast.For, ast.AsyncFor, ast.comprehension)):
            sc.locals |= {n.id for n in ast.walk(node.target) if isinstance(n, ast.Name)}
        elif isinstance(node, ast.withitem) and node.optional_vars is not None:
            sc.locals |= {n.id for n in ast.walk(node.optional_vars) if isinstance(n, ast.Name)}
        elif isinstance(node, ast.ExceptHandler) and node.name:
            sc.locals.add(node.name)
        elif isinstance(node, ast.NamedExpr):
            sc.locals.add(node.target.id)
    sc.locals -= set(sc.imports)
    return sc


def _bind(ix: Index, mod: Module, sc: Scope, expr: ast.AST, depth: int = 0) -> tuple | None:
    """What an expression names: ("src", rel, path) / ("ext", dotted) / ("lambda", node) / ("nested", name) /
    ("fixture", name) / ("testfn", rel, name) / ("method", rel, name) / None (a value the analysis does not follow)."""
    if depth > 6:
        return None
    if isinstance(expr, ast.Name):
        n = expr.id
        if n in sc.aliases:
            v = sc.aliases[n]
            return ("lambda", v) if isinstance(v, ast.Lambda) else _bind(ix, mod, sc, v, depth + 1)
        if n in sc.nested:
            return ("nested", n)
        if n in sc.fixtures and n in sc.locals:
            return ("fixture", n)
        if n in sc.locals:
            return None
        if n in sc.imports:
            return ix.normal(sc.imports[n])
        if n in mod.imports:
            return ix.normal(mod.imports[n])
        if n in mod.functions:
            return ("src", mod.rel, (n,)) if mod.rel in ix.source else ("testfn", mod.rel, n)
        if n in mod.classes:
            return ("src", mod.rel, (n,)) if mod.rel in ix.source else None
        if n in mod.aliases:  # NAME = Report(...) at module level: an instance of that class
            v = mod.aliases[n]
            return _bind(ix, mod, Scope(), v.func if isinstance(v, ast.Call) else v, depth + 1)
        for star in mod.stars:
            t = ix.normal(star)
            if t and t[0] == "src":
                hit = ix.symbol(("src", t[1], (*t[2], n)))
                if hit:
                    return ("src", hit[0], hit[1])
        return ("ext", n) if n in BUILTIN_NAMES else None
    if isinstance(expr, ast.Attribute):
        if isinstance(expr.value, ast.Name) and expr.value.id == "self" and sc.cls:
            if expr.attr in sc.self_aliases:
                return _bind(ix, mod, sc, sc.self_aliases[expr.attr], depth + 1)
            if f"{sc.cls}.{expr.attr}" in mod.functions:
                return ("method", mod.rel, f"{sc.cls}.{expr.attr}")
            return None
        base = _bind(ix, mod, sc, expr.value, depth + 1)
        if base is None:
            return None
        if base[0] == "src":
            return ("src", base[1], (*base[2], expr.attr))
        if base[0] == "ext":  # e.g. a namespace package: pipeline.report resolves only as a whole
            return ix.resolve_dotted(f"{base[1]}.{expr.attr}")
    return None


def _mechanism(qn: str) -> str | None:
    for prefix, kind in MECHANISMS:
        if qn == prefix.rstrip(".") or qn.startswith(prefix):
            return kind
    return None


def _str_arg(call: ast.Call, i: int) -> str | None:
    if len(call.args) > i and isinstance(call.args[i], ast.Constant) and isinstance(call.args[i].value, str):
        return call.args[i].value
    return None


def _patch(ix: Index, mod: Module, sc: Scope, call: ast.Call, b: tuple | None) -> tuple | None:
    is_mp = isinstance(call.func, ast.Attribute) and call.func.attr in ("setattr", "delattr") and \
        isinstance(call.func.value, ast.Name) and call.func.value.id == "monkeypatch"
    qn = b[1] if b and b[0] == "ext" else None
    if not (is_mp or (qn and (qn in PATCHERS or qn.endswith((".patch", ".patch.object"))))):
        return None
    s = _str_arg(call, 0)
    if s is not None:
        return ix.resolve_dotted(s)
    obj = _bind(ix, mod, sc, call.args[0]) if call.args else None
    attr = _str_arg(call, 1)
    if obj and obj[0] == "src" and attr:
        return ("src", obj[1], (*obj[2], attr))
    return obj


def analyze(ix: Index, mod: Module, fn: ast.AST, depth: int = 0, seen: set | None = None,
            out: Analysis | None = None, cls: str | None = None, parent: Scope | None = None) -> Analysis:
    out = out if out is not None else Analysis()
    seen = seen if seen is not None else set()
    key = (mod.rel, getattr(fn, "name", "lambda"), getattr(fn, "lineno", 0), getattr(fn, "col_offset", 0))
    if key in seen:
        return out
    seen.add(key)
    if isinstance(fn, ast.Lambda):
        sc = parent or Scope(cls=cls)
        roots: list[ast.AST] = [fn.body]
    else:
        sc = _scope(ix, mod, fn, cls)
        if parent is not None:  # nested function: the enclosing test's names stay visible unless shadowed
            for k in ("imports", "aliases", "nested", "self_aliases"):
                setattr(sc, k, {**getattr(parent, k), **getattr(sc, k)})
            sc.locals |= parent.locals - set(sc.imports)
            sc.fixtures |= parent.fixtures
        roots = [*getattr(fn, "decorator_list", []), *getattr(fn, "body", [])]
    fixtures = {**ix.conftest_fixtures(mod.rel), **{k: (mod, v) for k, v in mod.fixtures.items()}}
    if depth < MAX_DEPTH and parent is None and not isinstance(fn, ast.Lambda):
        if cls and getattr(fn, "name", "") not in SETUP_METHODS:  # setUp / setup_method run with every test
            for sm in SETUP_METHODS:
                setup = mod.functions.get(f"{cls}.{sm}")
                if setup is None:
                    continue
                for node, _p in _walk_own(list(setup.body)):
                    if isinstance(node, ast.Assign) and len(node.targets) == 1:
                        t = node.targets[0]
                        if isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name) and t.value.id == "self":
                            sc.self_aliases[t.attr] = node.value
                analyze(ix, mod, setup, depth + 1, seen, out, cls=cls)
        for p in sorted(sc.fixtures):  # requested fixtures run as part of the test
            if p in fixtures and fixtures[p][1] is not fn:
                fm, ff = fixtures[p]
                analyze(ix, fm, ff, depth + 1, seen, out)
    for node, _parent in _walk_own(roots):
        if not isinstance(node, ast.Call):
            continue
        out.calls += 1
        b = _bind(ix, mod, sc, node.func)
        target = _patch(ix, mod, sc, node, b)
        if target:
            out.patches.append({"target": target, "line": node.lineno})
        hit = ix.symbol(b) if b and b[0] == "src" else None
        if hit:
            out.source_calls.add(hit[0])
            for arg in [*node.args, *[k.value for k in node.keywords]]:  # dependency injection
                ab = _bind(ix, mod, sc, arg)
                inj = ix.symbol(ab) if ab and ab[0] == "src" else None
                if inj:
                    out.source_calls.add(inj[0])
        if b and b[0] == "ext":
            kind = _mechanism(b[1])
            if kind:
                out.mechanisms.append({"kind": kind, "call": b[1], "line": node.lineno})
        if depth >= MAX_DEPTH or b is None:
            continue
        if b[0] == "src" and b[1] in ix.tests and len(b[2]) == 1 and b[2][0] in ix.modules[b[1]].functions:
            other = ix.modules[b[1]]
            analyze(ix, other, other.functions[b[2][0]], depth + 1, seen, out)
        elif b[0] == "testfn" and b[2] in mod.functions:
            analyze(ix, mod, mod.functions[b[2]], depth + 1, seen, out)
        elif b[0] == "method":
            analyze(ix, mod, mod.functions[b[2]], depth + 1, seen, out, cls=sc.cls)
        elif b[0] == "nested":
            analyze(ix, mod, sc.nested[b[1]], depth + 1, seen, out, cls=sc.cls, parent=sc)
        elif b[0] == "lambda":
            analyze(ix, mod, b[1], depth + 1, seen, out, cls=sc.cls, parent=sc)
        elif b[0] == "fixture" and b[1] in fixtures:  # a fixture returning a callable
            fm, ff = fixtures[b[1]]
            fsc = _scope(ix, fm, ff, None)
            for r in ast.walk(ff):
                if isinstance(r, (ast.Return, ast.Yield)) and r.value is not None:
                    got = ix.symbol(_bind(ix, fm, fsc, r.value))
                    if got:
                        out.source_calls.add(got[0])
    return out


# ---------------------------------------------------------------- interfaces
def provider_symbols(iface: dict, units: list[dict]) -> set[str]:
    syms = {u.get("name", "").split(".")[-1] for u in units if u.get("component") == iface.get("provider")
            and isinstance(u.get("name"), str)}
    s = signature_symbol(iface.get("signature"))
    return {x for x in (syms | ({s} if s else set())) if x}


def classify(ix: Index, analysis: Analysis, provider: set[str], consumer: set[str] | None, symbols: set[str]) -> dict:
    """One (test function, interface) pair. provider/consumer are source rels; consumer None = EXTERNAL only."""
    reach = ix.closure(set(analysis.source_calls))
    rp = bool(reach & provider)
    rc = True if consumer is None else bool(reach & consumer)
    patched = set()
    for p in analysis.patches:
        t = p["target"]
        if t and t[0] == "src" and (t[1] in provider or (t[2] and t[2][-1] in symbols)):
            patched.add(".".join([*_parts(t[1]), *t[2]]))
    if rp and rc:
        path = "static"
    elif analysis.mechanisms:
        path = "runtime_candidate"
    elif analysis.calls == 0:
        path = "placeholder"
    else:
        path = "none"
    return {"path": path, "reaches_provider": rp, "reaches_consumer": rc, "patched_provider": sorted(patched),
            "mechanisms": sorted({m["kind"] for m in analysis.mechanisms}),
            "calls_source": sorted(analysis.source_calls), "placeholder": analysis.calls == 0}


def integration_functions(ix: Index, test_rels: list[str], wanted: set[str]) -> dict[str, list[tuple[Module, str]]]:
    """TEST id -> [(module, function name)] for test functions whose name carries exactly that one id."""
    out: dict[str, list[tuple[Module, str]]] = {}
    for rel in test_rels:
        m = ix.modules.get(rel)
        if m is None:
            continue
        for name in m.functions:
            leaf = name.split(".")[-1]
            if not leaf.startswith("test") or ("." in name and not name.startswith("Test")):
                continue
            ids = test_ids_in_text(name)
            if len(ids) == 1 and (tid := next(iter(ids))) in wanted:
                out.setdefault(tid, []).append((m, name))
    return out


def component_rels(ix: Index, units: list[dict], component: str) -> set[str]:
    return {u["module"].replace("\\", "/") for u in units
            if u.get("component") == component and isinstance(u.get("module"), str)
            and u["module"].replace("\\", "/") in ix.source}


RANK = {"static": 0, "runtime_candidate": 1, "none": 2, "placeholder": 3}


def interface_wiring(ix: Index, graph, test_rels: list[str]) -> dict:
    """Per interface and integration test: the classification of every function carrying that TEST id.

    Returns {"interfaces": {IF: {...}}, "tests": {TEST: [function view]}}, what G4 and G6 judge from. Module ids are
    project-relative file paths.
    """
    units = list(graph.units.values())
    integ = {tid for tid, t in graph.tests.items() if t.get("level") == "integration"}
    funcs = integration_functions(ix, test_rels, integ)
    analyses: dict[tuple[str, str], Analysis] = {}
    tests_view: dict[str, list[dict]] = {}
    for tid, fl in sorted(funcs.items()):
        for m, name in fl:
            a = analyze(ix, m, m.functions[name], cls=name.split(".")[0] if "." in name else None)
            analyses[(m.rel, name)] = a
            tests_view.setdefault(tid, []).append({"function": f"{m.rel}::{name}", "file": m.rel, "name": name,
                                                   "placeholder": a.calls == 0,
                                                   "mechanisms": sorted({x["kind"] for x in a.mechanisms}),
                                                   "calls_source": sorted(a.source_calls)})
    ifs: dict[str, dict] = {}
    for iid, iface in sorted(graph.ifaces.items()):
        prov = component_rels(ix, units, str(iface.get("provider")))
        arch_cons = [c for c in _ids(iface.get("consumers")) if c != "EXTERNAL"]
        cons = set().union(*(component_rels(ix, units, c) for c in arch_cons)) if arch_cons else None
        syms = provider_symbols(iface, units)
        tests: dict[str, dict] = {}
        for tid in sorted(t for t in integ if iid in _ids(graph.tests[t].get("verifies"))):
            views = []
            for m, name in funcs.get(tid, []):
                c = classify(ix, analyses[(m.rel, name)], prov, cons, syms)
                views.append({"function": f"{m.rel}::{name}", "file": m.rel, "name": name, **c})
            best = min(views, key=lambda v: RANK[v["path"]]) if views else None
            worst = max(views, key=lambda v: RANK[v["path"]]) if views else None
            tests[tid] = {"functions": views, "path": best["path"] if best else "missing",
                          "worst_path": worst["path"] if worst else "missing", "best": best,
                          "any_placeholder": any(v["placeholder"] for v in views)}
        ifs[iid] = {"provider": iface.get("provider"), "consumers": _ids(iface.get("consumers")),
                    "provider_modules": sorted(prov), "consumer_modules": sorted(cons) if cons is not None else None,
                    "provider_symbols": sorted(syms), "tests": tests}
    return {"interfaces": ifs, "tests": tests_view}

"""VModel DevKit runtime tracer for G6 (0.2.0, REQ-G6-31). Part of the Validator Core.

G6 puts this directory first on PYTHONPATH and VMODEL_TRACE_SPEC in the environment of the integration test command,
so every Python process of the run (pytest and the processes it starts) imports this file at start-up. For the
watched files (interface provider/consumer modules and integration test files) it records which functions started,
together with the pytest test id (parameters dropped) and phase. The main thread follows PYTEST_CURRENT_TEST (inherited
by child processes); another thread belongs to the test that started it, in that test's live phase ("detached" once
another test runs). One line per new (test, phase, file,
function); a forked child writes its own file; past the record limit a {"truncated": true} line is written. Module
and class bodies are not counted, so importing a module is not execution.

Trust: this runs inside the processes under test, like the test runner itself (SPEC 5.7); the validator hashes the
files after the run and records them in the signed evidence. Any problem here is swallowed: the traced program must
behave exactly as without the tracer. A project's own sitecustomize (later on sys.path) still runs.
"""


def _vmodel_trace_install():
    import os
    import sys

    spec_path = os.environ.get("VMODEL_TRACE_SPEC")
    if not spec_path:
        return
    import json
    import threading

    with open(spec_path, encoding="utf-8") as fh:
        spec = json.load(fh)

    def norm(p):
        return os.path.normcase(os.path.realpath(p))

    watch = {norm(k): v for k, v in spec["watch"].items()}
    limit = int(spec.get("limit", 100000))
    byte_limit = int(spec.get("byte_limit", 24 * 1024 * 1024))  # below the validator's per-file reading limit
    mon = getattr(sys, "monitoring", None)
    tool = None
    if mon is not None and not spec.get("force_setprofile"):
        for tid in (4, 3, 5):
            try:
                mon.use_tool_id(tid, "vmodel-trace")
                tool = tid
                break
            except (ValueError, RuntimeError):
                continue
    method = "sys.monitoring" if tool is not None else "setprofile"
    state = {"out": None, "seen": set(), "full": False, "bytes": 0}
    lock = threading.Lock()

    def open_out():
        """One file per process; a forked child gets its own (it must not write into its parent's file)."""
        state["out"] = open(os.path.join(spec["out"], f"{os.getpid()}-{os.urandom(4).hex()}.jsonl"), "a",
                            encoding="utf-8", buffering=1)
        state["seen"] = set()
        state["full"] = False
        state["bytes"] = 0
        state["out"].write(json.dumps({"v": 1, "pid": os.getpid(), "ppid": os.getppid(),
                                       "python": sys.version.split()[0], "method": method,
                                       "argv": [str(a) for a in getattr(sys, "orig_argv", sys.argv)][:20]},
                                      ensure_ascii=True) + "\n")

    open_out()
    if hasattr(os, "register_at_fork"):
        def _child():
            try:
                open_out()
            except Exception:
                state["out"] = None
        os.register_at_fork(after_in_child=_child)

    def env_context():
        test = os.environ.get("PYTEST_CURRENT_TEST")
        if not test or not test.endswith(")") or " (" not in test:
            return None, None
        node, phase = test[:-1].rsplit(" (", 1)
        return node.split("[", 1)[0], phase  # parameters dropped (they may contain '::'): evidence per function

    def context():
        """The test a running function belongs to. The main thread follows pytest's current test. Another thread
        belongs to the test that started it (owner), in that test's live phase; once the owner is no longer the
        current test its records are "detached"; a thread started outside any test belongs to none."""
        main = threading.main_thread()
        ident = threading.get_ident()  # no current_thread(): it would create a _DummyThread for raw threads
        if ident == main.ident:
            return env_context()
        th = getattr(threading, "_active", {}).get(ident)  # looked up each time: fork rebuilds it
        owner = getattr(th, "_vmodel_owner", None) if th is not None else None
        if owner is None:
            return None, None
        test, phase = env_context()
        return owner, (phase if test == owner else "detached")

    original_start = threading.Thread.start

    def start(self, *args, **kwargs):
        try:
            self._vmodel_owner = context()[0]
        except Exception:
            pass
        return original_start(self, *args, **kwargs)

    threading.Thread.start = start
    labels = {}

    def label_of(filename):
        try:
            return labels[filename]
        except KeyError:
            lab = None
            if filename and not filename.startswith("<"):
                try:
                    lab = watch.get(norm(filename))
                except (OSError, ValueError):
                    lab = None
            labels[filename] = lab
            return lab

    def record(code):
        """None: not watched; True: watched (recorded when it is a function)."""
        lab = label_of(code.co_filename)
        if lab is None:
            return None
        if not code.co_flags & 0x1:  # CO_OPTIMIZED: functions only, not module or class bodies (import time)
            return True
        test, phase = context()
        key = (test, phase, lab, getattr(code, "co_qualname", code.co_name))
        seen = state["seen"]
        if key not in seen and state["out"] is not None:
            with lock:
                if key in seen or state["full"]:
                    return True
                line = json.dumps({"t": key[0], "p": key[1], "m": key[2], "f": key[3]}, ensure_ascii=True) + "\n"
                if len(seen) >= limit or state["bytes"] + len(line) > byte_limit:
                    state["full"] = True  # the validator must not read absence as "did not run"
                    state["out"].write(json.dumps({"truncated": True}) + "\n")
                    return True
                seen.add(key)
                state["bytes"] += len(line)
                state["out"].write(line)
        return True

    if tool is not None:
        disable = mon.DISABLE

        def on_start(code, offset):
            try:
                return None if record(code) else disable
            except Exception:
                return disable

        mon.register_callback(tool, mon.events.PY_START, on_start)
        mon.set_events(tool, mon.events.PY_START)
    else:
        def on_call(frame, event, arg):
            if event == "call":
                try:
                    record(frame.f_code)
                except Exception:
                    pass

        sys.setprofile(on_call)
        threading.setprofile(on_call)


def _vmodel_chain_site():
    """Run the next sitecustomize on sys.path (the project's or the environment's), as without the tracer."""
    import importlib.util
    import os
    import sys

    here = os.path.normcase(os.path.dirname(os.path.abspath(__file__)))
    for entry in sys.path:
        if not entry or os.path.normcase(os.path.abspath(entry)) == here:
            continue
        cand = os.path.join(entry, "sitecustomize.py")
        if os.path.isfile(cand):
            spec = importlib.util.spec_from_file_location("_vmodel_chained_sitecustomize", cand)
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                sys.modules["_vmodel_chained_sitecustomize"] = mod
                spec.loader.exec_module(mod)
            return


try:
    _vmodel_trace_install()
except Exception:  # never break the program under test
    pass
_vmodel_chain_site()

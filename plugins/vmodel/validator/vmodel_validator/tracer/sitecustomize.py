"""VModel DevKit runtime tracer for G6 (0.2.0, REQ-G6-31). Part of the Validator Core.

G6 puts this directory first on PYTHONPATH and VMODEL_TRACE_SPEC in the environment of the integration test command,
so every Python process of the run (pytest and the processes it starts) imports this file at start-up. For the
watched files (interface provider/consumer modules and integration test files) it records which functions started,
together with the pytest test id that was current (PYTEST_CURRENT_TEST, inherited by child processes): one line per
new (test, file, function). Module and class bodies are not counted, so importing a module is not execution.

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
    limit = int(spec.get("limit", 20000))
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
    out = open(os.path.join(spec["out"], f"{os.getpid()}-{os.urandom(4).hex()}.jsonl"), "a", encoding="utf-8",
               buffering=1)
    out.write(json.dumps({"v": 1, "pid": os.getpid(), "ppid": os.getppid(), "python": sys.version.split()[0],
                          "method": method, "argv": [str(a) for a in getattr(sys, "orig_argv", sys.argv)][:20]},
                         ensure_ascii=True) + "\n")
    labels = {}
    seen = set()
    lock = threading.Lock()

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
        test = os.environ.get("PYTEST_CURRENT_TEST")
        if test:
            test = test.rsplit(" (", 1)[0]
        key = (test, lab, getattr(code, "co_qualname", code.co_name))
        if key not in seen:
            with lock:
                if key not in seen and len(seen) < limit:
                    seen.add(key)
                    out.write(json.dumps({"t": key[0], "m": key[1], "f": key[2]}, ensure_ascii=True) + "\n")
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

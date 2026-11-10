"""VModel DevKit runtime tracer for G6 (0.2.0, REQ-G6-31, D44). Part of the Validator Core.

G6 puts this directory first on PYTHONPATH and VMODEL_TRACE_SPEC in the environment of the integration test command,
so every Python process of the run (pytest and the processes it starts) imports this file at start-up. For the
watched files (interface provider/consumer modules and integration test files) it records which functions started,
together with the pytest test id (parameters dropped) and phase. The main thread follows PYTEST_CURRENT_TEST (inherited
by child processes); another thread belongs to the test that started it, and a thread-pool work item to the test that
submitted it, in that test's live phase ("detached" once another test runs). One line per new (test, phase, file,
function); a forked child writes its own file; past the record limit a {"truncated": true} line is written. Module
and class bodies are not counted, so importing a module is not execution.

Connections (D44, reviews 5-6): for a provider file named in the spec's "providers", each time one of its functions
starts the tracer walks the call stack (and takes what was inherited from the stack that started the thread or
submitted the pool work item it runs in). It writes {"e": provider file, "f": entry, "s": started function, "a":
anchors} (the provider ran)
and {"e", "f": entry, "c": consumer file, "a"} (a consumer called it). The entry is the outermost provider-file function
between the starting function and the consumer (for "ran": on the whole stack): the interface function actually
called, so a helper run by a constructor is recorded as the constructor (review 6 M1). The anchors are the functions of
integration test files and conftest.py ("tests" in the spec) on the stack: the validator counts a line only when one of
them is the test function or a fixture/setUp it requested, never only an autouse fixture (review 5 N7; a set, so a
decorator wrapper around the test does not hide it, review 6 M2). One line per (test, phase, file, entry, consumer,
anchors). Stack scans per (test, phase, function) stop once the function was entered directly with the test's own
anchor for every consumer, or at the cap ({"edge_scan_capped": ...}: absence is not proof).

Time (reviews 4-6): every line carries "ts" (wall clock) and "tc" (time.perf_counter_ns(), the system-wide monotonic
high-resolution counter, compared instead of the wall clock: Windows CPython <= 3.12 has a 15.6 ms wall clock). A process started during a test (it inherits
PYTEST_CURRENT_TEST, header "spawned_in") keeps that test id for its whole life, so the validator re-reads its lines
against exact test phase boundaries written by the validator's pytest plugin (vmodel_trace_plugin.py, loaded through
PYTEST_PLUGINS): a line outside that test's phases is "detached", one inside its call is "call".

Spawn origin (D45, policy B): starting a process writes {"spawn": token, "t", "p", "a": anchors of the starting stack and
what its thread inherited, "via"} and hands the child the token: subprocess.Popen, os.system and os.posix_spawn[p] in
VMODEL_TRACE_ORIGIN (the child's header has "origin"), os.fork (also pty.spawn and the POSIX os.spawn*) through the
fork hooks, multiprocessing (spawn, forkserver, fork) on the Process object (the child writes {"origin": token}). The
validator follows token -> spawn line -> that process's own origin, so a child's work is credited to a test only when
the test function or a fixture it requested started it (directly or through further children). Windows os.spawn* and
C-level spawns have no origin. Consumer files also get {"t", "p", "k": consumer file, "a": anchors} lines (review 12
H2): a runtime path credits only a consumer run of the test itself.

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
    import time

    with open(spec_path, encoding="utf-8") as fh:
        spec = json.load(fh)

    def norm(p):
        return os.path.normcase(os.path.realpath(p))

    watch = {norm(k): v for k, v in spec["watch"].items()}
    providers = {k: frozenset(v) for k, v in (spec.get("providers") or {}).items() if isinstance(v, list)}
    consumers = frozenset(c for v in providers.values() for c in v)
    test_labels = frozenset(x for x in spec.get("tests") or [] if isinstance(x, str))
    limit = int(spec.get("limit", 100000))
    byte_limit = int(spec.get("byte_limit", 24 * 1024 * 1024))  # below the validator's per-file reading limit
    scan_limit = int(spec.get("edge_scan_limit", 2000))
    stack_depth = int(spec.get("stack_depth", 256))
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
    ORIGIN = "VMODEL_TRACE_ORIGIN"  # the spawn line (in the starting process's file) a subprocess.Popen child came from
    state = {"out": None, "seen": set(), "full": False, "bytes": 0, "found": {}, "scans": {}}
    lock = threading.Lock()
    local = threading.local()  # the thread-pool work item running in this thread: (owner test, consumer labels)
    unset = object()

    def open_out():
        """One file per process; a forked child gets its own (it must not write into its parent's file). spawned_in:
        the test this process was started in (inherited PYTEST_CURRENT_TEST), None for the pytest process itself."""
        state["name"] = f"{os.getpid()}-{os.urandom(4).hex()}"
        state["out"] = open(os.path.join(spec["out"], state["name"] + ".jsonl"), "a", encoding="utf-8", buffering=1)
        state["spawns"] = 0
        state["kdone"] = set()
        state["seen"] = set()
        state["full"] = False
        state["bytes"] = 0
        state["found"] = {}
        state["scans"] = {}
        born = env_context()
        state["spawned"] = born[0] is not None
        origin = os.environ.get(ORIGIN)
        state["out"].write(json.dumps({"v": 2, "pid": os.getpid(), "ppid": os.getppid(),
                                       "python": sys.version.split()[0], "method": method,
                                       "spawned_in": list(born) if born[0] is not None else None,
                                       "origin": origin if origin else None,
                                       "argv": [str(a) for a in getattr(sys, "orig_argv", sys.argv)][:20]},
                                      ensure_ascii=True) + "\n")

    def env_context():
        test = os.environ.get("PYTEST_CURRENT_TEST")
        if not test or not test.endswith(")") or " (" not in test:
            return None, None
        node, phase = test[:-1].rsplit(" (", 1)
        i = node.find(".py::")  # parameters dropped (they may contain '::'); a '[' in the path is not one (review 4)
        cut = node.find("[", i + 5 if i >= 0 else 0)
        return (node if cut < 0 else node[:cut]), phase

    open_out()
    if hasattr(os, "register_at_fork"):
        def _before():
            """D45 (review 12 M3): a forked child's origin is the forking stack and what that thread inherited (the
            child's only thread becomes its main thread, which inherits nothing)."""
            try:
                state["fork"] = new_spawn(sys._getframe(1), "fork")
            except Exception:
                state["fork"] = None

        def _parent():
            state["fork"] = None

        def _child():
            try:
                state["sysenv"] = {"lock": threading.Lock(), "active": [], "base": None}
                if state.get("fork"):
                    os.environ[ORIGIN] = state["fork"]  # also for a program the child execs (os.spawn*, pty.spawn)
                open_out()
            except Exception:
                state["out"] = None
        os.register_at_fork(before=_before, after_in_parent=_parent, after_in_child=_child)

    def this_thread():
        return getattr(threading, "_active", {}).get(threading.get_ident())  # looked up each time: fork rebuilds it

    def context():
        """The test a running function belongs to. The main thread follows pytest's current test. A pool work item
        belongs to the test that submitted it, another thread to the test that started it (owner), in that test's live
        phase; once the owner is no longer the current test its records are "detached"; a thread started outside any
        test belongs to none."""
        if threading.get_ident() == threading.main_thread().ident:  # no current_thread(): no _DummyThread
            return env_context()
        owner = getattr(local, "owner", unset)
        if owner is unset:
            th = this_thread()
            owner = getattr(th, "_vmodel_owner", None) if th is not None else None
        if owner is None:
            return None, None
        test, phase = env_context()
        return owner, (phase if test == owner else "detached")

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

    def inherited():
        """(consumer labels, anchors) from the stack that started this thread or submitted the pool work item it runs."""
        if threading.get_ident() == threading.main_thread().ident:
            return frozenset(), frozenset()
        via = getattr(local, "via", unset)
        if via is unset:
            th = this_thread()
            via = getattr(th, "_vmodel_via", None) if th is not None else None
        return via or (frozenset(), frozenset())

    def stack_info(frame, prov=None, entry=None):
        """Walk from `frame` to the root: {consumer label: entry} (the outermost function of the provider file `prov`
        seen before that consumer), the outermost provider-file function, and the test-file functions (anchors)."""
        cons, anchors, n = {}, set(), 0
        while frame is not None and n < stack_depth:
            code = frame.f_code
            if code.co_flags & 0x1:  # functions only: a module body importing is not a call, as in record()
                lab = label_of(code.co_filename)
                if lab is not None:
                    qn = getattr(code, "co_qualname", code.co_name)
                    if lab == prov:
                        if "<locals>" not in qn or entry is None:  # a decorator's wrapper does not hide the
                            entry = qn                               # function it wraps (review 7 R1)
                    elif lab in consumers:
                        cons.setdefault(lab, entry)
                    elif lab in test_labels and len(anchors) < 64:
                        anchors.add(qn)
            frame = frame.f_back
            n += 1
        return cons, entry, anchors

    def via_here(frame):
        """What a thread started / a work item submitted from here inherits: consumers and anchors on this stack plus
        the starter's own inheritance."""
        if not providers:
            return frozenset(), frozenset()
        cons, _e, anchors = stack_info(frame)
        inh_c, inh_a = inherited()
        return frozenset(cons) | inh_c, frozenset(anchors) | inh_a

    def write(key, obj):
        """One line per new key; past the limits one truncation line (the validator must not read absence as proof)."""
        seen = state["seen"]
        if key in seen or state["out"] is None:
            return
        with lock:
            if key in seen or state["full"]:
                return
            line = json.dumps({**obj, "ts": round(time.time(), 6), "tc": time.perf_counter_ns()},
                              ensure_ascii=True) + "\n"
            if len(seen) >= limit or state["bytes"] + len(line) > byte_limit:
                state["full"] = True
                state["out"].write(json.dumps({"truncated": True}) + "\n")
                return
            seen.add(key)
            state["bytes"] += len(line)
            state["out"].write(line)

    def own_anchor(test):
        """The test function's qualname from its node id (file.py::Class::test -> Class.test)."""
        i = test.find(".py::") if test else -1
        return test[i + 5:].replace("::", ".") if i >= 0 else None

    def note_provider(test, phase, lab, func, frame):
        want = providers[lab]
        k = (test, phase, lab, func)
        own = own_anchor(test)
        done = state["found"].setdefault(k, set())
        if "ran" in done and done >= want:
            return
        n = state["scans"].get(k, 0)
        if n >= scan_limit:
            return
        state["scans"][k] = n + 1
        cons, entry, anchors = stack_info(frame, lab, func)
        inh_c, inh_a = inherited()
        for c in inh_c - set(cons):
            cons[c] = entry  # a consumer that started this thread / submitted this work item
        anchors = tuple(sorted(set(anchors) | inh_a))
        a = list(anchors)
        write(("r", test, phase, lab, entry, func, anchors), {"t": test, "p": phase, "e": lab, "f": entry, "s": func,
                                                              "a": a})
        for c, c_entry in cons.items():
            if c in want:
                write(("e", test, phase, lab, c_entry, c, anchors), {"t": test, "p": phase, "e": lab, "f": c_entry,
                                                                     "c": c, "a": a})
                if own in anchors and c_entry == func:  # entered directly by the consumer within the test itself
                    done.add(c)
        if own in anchors and entry == func:
            done.add("ran")
        if n + 1 == scan_limit and not ("ran" in done and done >= want):
            write(("cap", test, phase, lab, func), {"edge_scan_capped": True, "t": test, "p": phase, "e": lab,
                                                    "f": func})

    def note_consumer(test, phase, lab, frame):
        """D45 (review 12 H2): the anchors a consumer ran under, so that a runtime path credits only the test's own
        consumer run (not an autouse fixture's). One line per (test, phase, consumer, anchors); scans stop once the
        test function itself is an anchor, or at the cap."""
        k = (test, phase, lab)
        if k in state["kdone"]:
            return
        sk = ("k", k, threading.get_ident())  # per thread: another thread's runs cannot use up this one's budget
        n = state["scans"].get(sk, 0)
        if n >= scan_limit:
            return
        state["scans"][sk] = n + 1
        _c, _e, anchors = stack_info(frame)
        anchors = tuple(sorted(set(anchors) | inherited()[1]))
        write(("k", test, phase, lab, anchors), {"t": test, "p": phase, "k": lab, "a": list(anchors)})
        if own_anchor(test) in anchors:
            state["kdone"].add(k)
        elif n + 1 == scan_limit:
            write(("kcap", test, phase, lab, threading.get_ident()),
                  {"edge_scan_capped": True, "t": test, "p": phase, "k": lab})

    def record(code, frame=None):
        """None: not watched; True: watched (recorded when it is a function)."""
        lab = label_of(code.co_filename)
        if lab is None:
            return None
        if not code.co_flags & 0x1:  # CO_OPTIMIZED: functions only, not module or class bodies (import time)
            return True
        test, phase = context()
        func = getattr(code, "co_qualname", code.co_name)
        write((test, phase, lab, func), {"t": test, "p": phase, "m": lab, "f": func})
        if lab in providers:
            note_provider(test, phase, lab, func, frame)
        if lab in consumers and frame is not None:
            note_consumer(test, phase, lab, frame)
        return True

    def boundary(nodeid, phase):
        """Called by the validator's pytest plugin at the start of each phase and at the end of a test."""
        state["n"] = state.get("n", 0) + 1
        i = nodeid.find(".py::")
        cut = nodeid.find("[", i + 5 if i >= 0 else 0)
        write(("b", state["n"]), {"b": nodeid if cut < 0 else nodeid[:cut], "p": phase})

    globals()["_vmodel_boundary"] = boundary

    pool = {"patched": False}

    def patch_pool():
        """Work items carry the submitting test and the consumer labels on the submitting stack (patched once the
        thread pool module is in use: its first worker starts inside submit, so the first item has the worker's)."""
        if pool["patched"]:
            return
        mod = sys.modules.get("concurrent.futures.thread")
        item = getattr(mod, "_WorkItem", None) if mod is not None else None
        if item is None:
            return
        pool["patched"] = True
        original_init, original_run = item.__init__, item.run

        def init(self, *args, **kwargs):
            try:
                self._vmodel_ctx = (context()[0], via_here(sys._getframe(1)))
            except Exception:
                pass
            original_init(self, *args, **kwargs)

        def run(self, *args, **kwargs):
            ctx = getattr(self, "_vmodel_ctx", None)
            if ctx is None:
                return original_run(self, *args, **kwargs)
            prev = (getattr(local, "owner", unset), getattr(local, "via", unset))
            local.owner, local.via = ctx
            try:
                return original_run(self, *args, **kwargs)
            finally:
                for name, value in zip(("owner", "via"), prev):
                    if value is unset:
                        try:
                            delattr(local, name)
                        except AttributeError:
                            pass
                    else:
                        setattr(local, name, value)

        item.__init__, item.run = init, run

    original_start = threading.Thread.start

    def start(self, *args, **kwargs):
        try:
            self._vmodel_owner = context()[0]
            self._vmodel_via = via_here(sys._getframe(1))
            patch_pool()
        except Exception:
            pass
        return original_start(self, *args, **kwargs)

    threading.Thread.start = start

    def new_spawn(frame, via):
        """Policy B (D45): a spawn line for a process about to start from `frame` - the test-file functions (anchors)
        on that stack and what its thread inherited - and its token, which reaches the child as VMODEL_TRACE_ORIGIN
        (environment, survives a venv launcher on Windows) or on the multiprocessing Process object."""
        test, phase = context()
        _c, _e, anchors = stack_info(frame)
        anchors = sorted(set(anchors) | set(inherited()[1]))
        with lock:
            state["spawns"] += 1
            token = f"{state['name']}:{state['spawns']}"
        write(("spawn", token), {"spawn": token, "t": test, "p": phase, "a": anchors, "via": via})
        return token

    def patch_spawners():
        """subprocess.Popen (env=None becomes an explicit copy of os.environ plus the token), multiprocessing
        Process.start/_bootstrap (spawn, forkserver, fork; the child writes an {"origin": token} line), os.system (the
        token is put into os.environ for the call), os.posix_spawn[p] (the env argument). os.fork, pty.spawn and the
        POSIX os.spawn* (fork + exec) are covered by the fork hooks above. Windows os.spawn* and C-level spawns are
        not: such a process has no origin."""
        import functools
        import subprocess

        original_init = subprocess.Popen.__init__

        @functools.wraps(original_init)
        def init(self, args, *rest, **kwargs):
            try:
                token = new_spawn(sys._getframe(1), "subprocess.Popen")
                if len(rest) > 9:  # env passed positionally (bufsize ... cwd, env)
                    rest = (*rest[:9], {**(os.environ if rest[9] is None else rest[9]), ORIGIN: token}, *rest[10:])
                else:
                    base = kwargs.get("env")
                    kwargs["env"] = {**(os.environ if base is None else base), ORIGIN: token}
            except Exception:
                pass
            return original_init(self, args, *rest, **kwargs)

        subprocess.Popen.__init__ = init

        original_system = os.system
        state["sysenv"] = {"lock": threading.Lock(), "active": [], "base": None}

        def set_env(token, add):
            """The token of the latest running os.system call in os.environ (bookkeeping under a short lock, never
            held while a command runs: review 13 found deadlocks); the previous value once none runs."""
            s = state["sysenv"]
            with s["lock"]:
                if add:
                    if not s["active"]:
                        s["base"] = os.environ.get(ORIGIN)
                    s["active"].append(token)
                elif token in s["active"]:
                    s["active"].remove(token)
                if s["active"]:
                    os.environ[ORIGIN] = s["active"][-1]
                elif s["base"] is None:
                    os.environ.pop(ORIGIN, None)
                else:
                    os.environ[ORIGIN] = s["base"]

        @functools.wraps(original_system)
        def system(command):
            try:
                token = new_spawn(sys._getframe(1), "os.system")
                set_env(token, True)
            except Exception:
                return original_system(command)
            try:
                return original_system(command)
            finally:
                try:
                    set_env(token, False)
                except Exception:
                    pass

        os.system = system

        def wrap_posix_spawn(name):
            original = getattr(os, name)

            @functools.wraps(original)
            def spawn(path, argv, env, *rest, **kwargs):
                try:
                    env = {**env, ORIGIN: new_spawn(sys._getframe(1), name)}
                except Exception:
                    pass
                return original(path, argv, env, *rest, **kwargs)

            setattr(os, name, spawn)

        for name in ("posix_spawn", "posix_spawnp"):
            if hasattr(os, name):
                wrap_posix_spawn(name)

        try:
            import multiprocessing.process as mp_process
        except Exception:
            return
        base = mp_process.BaseProcess
        original_mp_start, original_bootstrap = base.start, base._bootstrap

        @functools.wraps(original_mp_start)
        def mp_start(self, *args, **kwargs):
            try:
                self._vmodel_origin = new_spawn(sys._getframe(1), "multiprocessing")
            except Exception:
                pass
            return original_mp_start(self, *args, **kwargs)

        @functools.wraps(original_bootstrap)
        def mp_bootstrap(self, *args, **kwargs):
            try:
                token = getattr(self, "_vmodel_origin", None)
                if isinstance(token, str):
                    os.environ[ORIGIN] = token
                    write(("origin", token), {"origin": token})
            except Exception:
                pass
            return original_bootstrap(self, *args, **kwargs)

        base.start, base._bootstrap = mp_start, mp_bootstrap

    try:
        patch_spawners()
    except Exception:
        pass

    if tool is not None:
        disable = mon.DISABLE

        def on_start(code, offset):
            try:
                return None if record(code, sys._getframe(1)) else disable  # frame 1: the function starting
            except Exception:
                return disable

        mon.register_callback(tool, mon.events.PY_START, on_start)
        mon.set_events(tool, mon.events.PY_START)
    else:
        def on_call(frame, event, arg):
            if event == "call":
                try:
                    record(frame.f_code, frame)
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

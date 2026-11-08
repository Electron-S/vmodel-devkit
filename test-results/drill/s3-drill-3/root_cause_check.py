"""Independent root-cause cross-check for drill-3 (no model calls, no validator records).

    python3 -I root_cause_check.py <seeded percentile.py> <fixed percentile.py> <tests/test_percentile.py>

Evaluates every literal `percentile(...)` call in the test file (parametrize cases included) with the seeded code, the
fixed code and an independent reference taken from the sealed drill plan (rank r = ceil(p*N/100), sorted[r-1]).
Prints every case where the seeded or the fixed code disagrees with the reference, with the plan's manifestation
condition (p*N/100 is an integer smaller than N). Exit 0 when the fixed code agrees everywhere.
"""
from __future__ import annotations

import ast
import importlib.util
import math
import sys

sys.dont_write_bytecode = True


def load(path: str, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod.percentile


def reference(scores, p):
    ordered = sorted(scores)
    return ordered[math.ceil(p * len(ordered) / 100) - 1]


def main() -> int:
    seeded, fixed = load(sys.argv[1], "seeded"), load(sys.argv[2], "fixed")
    tree = ast.parse(open(sys.argv[3], encoding="utf-8").read())
    env: dict = {}
    for node in tree.body:  # module-level constants such as SAMPLE
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            try:
                env[node.targets[0].id] = eval(compile(ast.Expression(node.value), "t", "eval"), {}, env)
            except Exception:
                pass
    checked, mismatches, fixed_wrong = 0, [], 0
    for fn in (n for n in tree.body if isinstance(n, ast.FunctionDef)):
        names, cases = [], [()]
        for dec in fn.decorator_list:
            if isinstance(dec, ast.Call) and getattr(dec.func, "attr", "") == "parametrize":
                names = [s.strip() for s in ast.literal_eval(dec.args[0]).split(",")]
                cases = eval(compile(ast.Expression(dec.args[1]), "t", "eval"), {}, env)
        calls = [c for c in ast.walk(fn) if isinstance(c, ast.Call) and getattr(c.func, "id", "") == "percentile"]
        for case in cases:
            local = {**env, **dict(zip(names, case if isinstance(case, tuple) else (case,)))}
            for call in calls:
                try:
                    scores, p = (eval(compile(ast.Expression(a), "t", "eval"), {}, local) for a in call.args)
                    ref = reference(scores, p)
                except Exception:
                    continue  # abnormal-input cases (ValueError) are outside this check
                checked += 1
                s_val, f_val = seeded(scores, p), fixed(scores, p)
                x = p * len(scores) / 100
                if f_val != ref:
                    fixed_wrong += 1
                if s_val != ref or f_val != ref:
                    mismatches.append(f"{fn.name} p={p} N={len(scores)} p*N/100={x} "
                                      f"integer<N={x.is_integer() and x < len(scores)} ref={ref} seeded={s_val} "
                                      f"fixed={f_val}")
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    print("\n".join(mismatches))
    print(f"normal-input calls checked: {checked}; seeded/fixed disagreements: {len(mismatches)}; "
          f"fixed code wrong: {fixed_wrong}")
    return 0 if fixed_wrong == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

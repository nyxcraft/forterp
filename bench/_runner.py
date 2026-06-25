"""Time one benchmark case against whatever `forterp` is on the import path.

Run in a *subprocess* (never imported by bench.py) so each measurement uses a fresh
interpreter and the `forterp` resolved from `PYTHONPATH` -- that is how bench.py times an
older commit's src/ without a `git checkout` of the working tree (copy-tree + PYTHONPATH;
checkout/pyc churn confounds timing). Prints one JSON line: {steps, ms_min} or {error}.

Usage:  PYTHONPATH=<src> python bench/_runner.py '<case-json>'
  case-json = {"files": [...abs paths...], "program": "NAME", "dialect": "fortran10",
               "target": "native", "reps": 5}
"""

import json
import pathlib
import sys
import time


def main():
    case = json.loads(sys.argv[1])
    try:
        import forterp as fp  # the interpreter under test (resolved via PYTHONPATH)

        # Resolve via the root-exported constants (forterp.FORTRAN10 / forterp.NATIVE) -- stable
        # across the whole forterp-era history, unlike the DIALECTS/TARGETS lookup dicts.
        dialect = getattr(fp, case["dialect"].upper())
        target = getattr(fp, case["target"].upper())
        src = "".join(pathlib.Path(f).read_text() for f in case["files"])
        units = fp.parse_source(src, dialect=dialect)

        # make_engine moved into the forterp.runtime namespace partway through history; accept
        # either location so the benchmark can span older commits too.
        rt = getattr(fp, "runtime", fp)
        make_engine = getattr(rt, "make_engine", None) or fp.make_engine

        prog = case["program"]
        # Measure RUN only (parse once, outside the timed loop), so every commit is compared
        # like-with-like. A commit predating Engine.run_program is reported as a gap rather than
        # measured a different (parse-inflated) way -- a misleading point is worse than none.
        best = None
        steps = 0
        for _ in range(case.get("reps", 5)):
            eng = make_engine(units, dialect=dialect, target=target)
            t0 = time.perf_counter()
            eng.run_program(prog)
            dt = (time.perf_counter() - t0) * 1000.0
            best = dt if best is None else min(best, dt)
            steps = eng.steps  # deterministic: identical every rep
        print(json.dumps({"steps": steps, "ms_min": round(best, 2)}))
    except Exception as e:  # an old/incompatible src -> recorded as a gap, not a crash
        print(json.dumps({"error": f"{type(e).__name__}: {str(e)[:120]}"}))


if __name__ == "__main__":
    main()

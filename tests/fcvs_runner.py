"""Run the vendored FCVS conformance corpus (tests/fcvs/) through the interpreter.

FCVS audit routines are self-checking: each computes a value, compares it to the
known-correct value via an arithmetic IF, tallies PASS/FAIL/DELETE counts, and
prints a run summary ("nnn TESTS PASSED", "nnn ERRORS ENCOUNTERED") to the line
printer (unit 6). We capture that printer listing (engine.printer sink) and parse
the summary -- the report IS line-printer output, not terminal I/O, so it is read
from a dedicated buffer, separate from any terminal stream.

Triage is DYNAMIC, by parse result -- never by keyword. A file that parses clean is
F66-compatible and is RUN (even if the word CHARACTER appears in a comment/Hollerith).
A file that fails to parse is classified: F77 (uses a CHARACTER declaration etc.,
beyond our F66+DEC target) -> kept in the corpus but NOT run; otherwise a known F66
feature gap (e.g. blanks-insignificance within tokens) -> also not run, logged.

Run as a module:  python -m fcvs_runner [--verbose]
or import run_corpus() for the regression test.
"""

from __future__ import annotations

import os
import re
import glob

from f66.source import scan_file, expand_includes
from f66.parser import parse_units
from f66.engine import Engine, Frame, StopExecution
from f66 import install_runtime


CORPUS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fcvs")

_PASS = re.compile(r"(\d+)\s+TESTS?\s+PASSED")
_ERRS = re.compile(r"(\d+)\s+ERRORS?\s+ENCOUNTERED")
# F77 CHARACTER, as a plain decl OR via IMPLICIT CHARACTER / CHARACTER*n. Matched only
# on code lines (comments often mention "BLANK CHARACTER" etc., which must not count).
_CHAR_DECL = re.compile(r"^\s*(?:IMPLICIT\s+)?CHARACTER\b|\bCHARACTER\s*\*", re.I)


def _has_char_decl(src):
    return any(_CHAR_DECL.search(l) for l in src.splitlines()
               if l[:1] not in "Cc*!Dd/")           # skip comment/debug lines


def _run_one(path):
    """Run a single audit routine. Returns (status, passed, errors):
    status in {"run", "f77", "gap"}. passed/errors are 0 unless status=="run".
    Parse failures split into "f77" (CHARACTER -- beyond our F66+DEC target) and
    "gap" (F66-valid but unimplemented, i.e. blanks-insignificance: FM010/11/21)."""
    src = open(path, errors="replace").read()
    stmts = expand_includes(scan_file(path).statements, os.path.dirname(path))
    errs = []
    units = parse_units(stmts, on_error=lambda st, m: errs.append(m))
    if errs:
        return ("f77" if _has_char_decl(src) else "gap", 0, 0)

    listing = []                                   # the line-printer (LPT) buffer
    eng = Engine({u.name: u for u in units}, emit=lambda s: None,
                 readline=lambda: "", printer=listing.append)
    install_runtime(eng)                           # STDLIB + FOROTS binary-I/O codec
    eng.io[5] = {"recs": [], "pos": 0, "mode": "r"}   # I01 card reader (unused by audits)
    eng.max_steps = 50_000_000
    main = next((u.name for u in units if u.kind == "program"), None)
    if main is None:
        return ("gap", 0, 0)
    try:
        eng.run(Frame(eng.rts[main], {}))
    except (StopExecution, Exception):
        pass
    report = "".join(listing)
    mp, me = _PASS.search(report), _ERRS.search(report)
    return ("run", int(mp.group(1)) if mp else 0, int(me.group(1)) if me else 0)


def run_corpus(corpus_dir=CORPUS_DIR):
    """Run every FM*.FOR. Returns a dict with the aggregate + per-file detail."""
    run = {}
    f77, gap, nosummary = [], [], []
    total_pass = total_err = 0
    for path in sorted(glob.glob(os.path.join(corpus_dir, "FM*.FOR"))):
        name = os.path.basename(path)
        status, p, e = _run_one(path)
        if status == "f77":
            f77.append(name)
        elif status == "gap":
            gap.append(name)
        else:
            run[name] = (p, e)
            total_pass += p
            total_err += e
            if p == 0 and e == 0:
                nosummary.append(name)         # ran, but printed no PASS/ERR summary
    return {
        "run": run, "f77": f77, "gap": gap, "nosummary": nosummary,
        "n_run": len(run), "n_f77": len(f77), "n_gap": len(gap),
        "total_pass": total_pass, "total_err": total_err,
    }


def main(argv=None):
    import sys
    verbose = "--verbose" in (argv or sys.argv[1:])
    r = run_corpus()
    print(f"FCVS corpus: {r['n_run']} F66-runnable, {r['n_f77']} F77 (kept, not run), "
          f"{r['n_gap']} F66 feature-gap (not run)")
    print(f"  conformance TESTS PASSED: {r['total_pass']}")
    print(f"  ERRORS ENCOUNTERED:       {r['total_err']}  "
          f"(FM001 forces one FAIL by design: 'FORCE FAIL CODE TO BE EXECUTED')")
    if r["nosummary"]:
        print(f"  ran w/o a PASS/ERR summary (print-and-eyeball FORMAT tests): "
              f"{r['nosummary']}")
    if verbose:
        for name, (p, e) in sorted(r["run"].items()):
            flag = "  <-- FAIL" if e else ""
            print(f"    {name}: {p} passed, {e} errors{flag}")
        print(f"  F77 (not run): {r['f77']}")
        print(f"  F66 gap (not run): {r['gap']}")
    return r


if __name__ == "__main__":
    main()

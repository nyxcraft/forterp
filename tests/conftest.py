"""Shared pytest harness for the forterp interpreter.

`run(src)` compiles and runs a small FORTRAN program through the real pipeline
(source reader -> lexer -> parser -> engine) and returns the Engine so tests can read
results out of COMMON. By convention test programs are named `T` and write results into
`COMMON /OUT/ V(40)`; read them with `out(eng, n)` (1-based, faithful to FORTRAN).

Dialect gating of the *tests* (mirrors the dialect gating of the *language*): a snippet
that is valid ANSI F66 must behave identically under both `F66` and `FORTRAN10` (the DEC
dialect is a strict superset), so `run()` exercises it under BOTH and asserts they agree.
A snippet that uses a DEC extension won't run under F66, so it is run under FORTRAN10 only.
Classification is automatic (try F66; if it raises, it's DEC-specific). A test that wants
to pin one dialect -- e.g. an F66 reject-test -- passes an explicit `dialect=`.

(src/ is on sys.path via pyproject's [tool.pytest.ini_options] pythonpath.)
"""

from __future__ import annotations

import math
import os
import tempfile

import forterp
from forterp.dialect import F66, FORTRAN10
from forterp.source import scan_file, expand_includes
from forterp.parser import parse_units
from forterp.engine import Engine, Frame, StopExecution


def _run_one(src, dlc, program, inputs, setup, target, path):
    """Compile+run `src` under one dialect `dlc`; return the Engine (raises on error)."""
    stmts = expand_includes(scan_file(path, dialect=dlc).statements, os.path.dirname(path))
    errs = []
    units = parse_units(
        stmts, dialect=dlc, on_error=lambda st, m: errs.append((st.line, m, st.text))
    )
    if errs:
        raise AssertionError("parse errors: " + "; ".join(f"L{ln}: {m} | {t}" for ln, m, t in errs))
    feed = iter(inputs or [])  # fresh per run -- the dual-run mustn't share an iterator
    rl = (lambda: next(feed, "")) if inputs is not None else None
    printout = []  # line-printer (LPT) capture buffer
    eng = Engine(
        {u.name: u for u in units},
        readline=rl,
        printer=printout.append,
        target=target or forterp.PDP10,  # default: validate the PDP-10 target
        **forterp.engine_kwargs(dlc),  # dialect-derived engine flags (single source)
    )
    eng.printout = printout  # tests read it via printed(eng)
    forterp.install_runtime(eng)  # STDLIB + FOROTS binary-I/O codec
    if setup is not None:
        setup(eng)
    try:
        eng.run(Frame(eng.rts[program], {}))
    except StopExecution:
        pass  # explicit STOP is normal program termination
    return eng


def _vals_agree(x, y):
    """Deep equality that treats NaN==NaN (so non-fatal-math results compare equal)."""
    if isinstance(x, float) and isinstance(y, float):
        return x == y or (math.isnan(x) and math.isnan(y))
    if isinstance(x, (list, tuple)) and isinstance(y, (list, tuple)):
        return len(x) == len(y) and all(_vals_agree(a, b) for a, b in zip(x, y))
    if isinstance(x, dict) and isinstance(y, dict):
        return x.keys() == y.keys() and all(_vals_agree(x[k], y[k]) for k in x)
    return x == y


def _assert_dialects_agree(f66_eng, f10_eng, src):
    """An F66-compliant program must produce identical results under F66 and FORTRAN10."""
    if (
        _vals_agree(f66_eng.commons, f10_eng.commons)
        and f66_eng.printout == f10_eng.printout
        and f66_eng.out == f10_eng.out  # terminal (TYPE / list-directed / unit-5) output too
    ):
        return
    raise AssertionError(
        "F66 and FORTRAN10 disagree on an F66-compliant program -- the dialect changed its "
        "behavior, or a gate over-rejects.\n"
        f"  COMMON  F66={f66_eng.commons!r}\n          F10={f10_eng.commons!r}\n"
        f"  LPT     F66={f66_eng.printout!r}\n          F10={f10_eng.printout!r}\n"
        f"  TTY     F66={f66_eng.out!r}\n          F10={f10_eng.out!r}\n"
        f"--- src ---\n{src}"
    )


def run(src, program="T", inputs=None, setup=None, target=None, dialect=None):
    """Compile+run a FORTRAN snippet; return the Engine. Raises on parse error.
    `inputs` is an optional list of lines fed to READ/ACCEPT (one per call).
    `setup(eng)` is an optional hook to tweak the engine before the program runs.
    `target` selects the value model; defaults to PDP10 (the unit suite asserts it).
    `dialect` pins the front-end to exactly one dialect (for dialect-specific tests, e.g.
    F66 reject-tests). When omitted, the snippet is classified automatically: if it is valid
    ANSI F66 it is run under BOTH F66 and FORTRAN10 and the two must agree (the superset
    property); if it uses a DEC extension it is run under FORTRAN10 only."""
    with tempfile.NamedTemporaryFile("w", suffix=".FOR", delete=False) as f:
        f.write(src)
        path = f.name
    try:
        if dialect is not None:
            return _run_one(src, dialect, program, inputs, setup, target, path)
        # Auto-classify: an F66-compliant snippet runs identically under both dialects;
        # a DEC-specific snippet (F66 raises) runs under FORTRAN10 only.
        try:
            f66_eng = _run_one(src, F66, program, inputs, setup, target, path)
        except Exception:
            f66_eng = None  # uses a DEC extension -> FORTRAN10-specific
        f10_eng = _run_one(src, FORTRAN10, program, inputs, setup, target, path)
        if f66_eng is not None:
            _assert_dialects_agree(f66_eng, f10_eng, src)
        return f10_eng
    finally:
        os.unlink(path)


def out(eng, n):
    """Read COMMON /OUT/ V(n) -- 1-based FORTRAN index."""
    return eng.commons["OUT"][n - 1]


def printed(eng):
    """Return everything written to the line printer (LPT, units 3/6) as one string."""
    return "".join(eng.printout)


# convenience preamble for integer-valued programs (FORTRAN-10's default IMPLICIT)
HEAD = "        PROGRAM T\n        IMPLICIT INTEGER(A-Z)\n        COMMON /OUT/ V(40)\n"
TAIL = "        END\n"


def run_int(body, target=None, dialect=None):
    """Run an integer program: HEAD + body (assignments to V(n)) + END."""
    return run(HEAD + body + TAIL, target=target, dialect=dialect)

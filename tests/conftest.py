"""Shared pytest harness for the forterp interpreter.

`run(src)` compiles and runs a small FORTRAN program through the real pipeline
(source reader -> lexer -> parser -> engine) and returns the Engine so tests can read
results out of COMMON. By convention test programs are named `T` and write results into
`COMMON /OUT/ V(40)`; read them with `out(eng, n)` (1-based, faithful to FORTRAN).

(src/ is on sys.path via pyproject's [tool.pytest.ini_options] pythonpath.)
"""

from __future__ import annotations

import os
import tempfile

import forterp
from forterp.source import scan_file, expand_includes
from forterp.parser import parse_units
from forterp.engine import Engine, Frame, StopExecution


def run(src, program="T", inputs=None, setup=None, target=None, dialect=None):
    """Compile+run a FORTRAN snippet; return the Engine. Raises on parse error.
    `inputs` is an optional list of lines fed to READ/ACCEPT (one per call).
    `setup(eng)` is an optional hook to tweak the engine before the program runs.
    `target` selects the value model; defaults to PDP10 (the unit suite asserts it).
    `dialect` selects the front-end. The library default is F66 (ANSI), but this harness
    defaults to FORTRAN10 so test snippets may use the DEC extensions (octal, tab-format,
    `!`, free-form input) freely; dialect-specific tests pass an explicit dialect."""
    dlc = dialect or forterp.FORTRAN10
    with tempfile.NamedTemporaryFile("w", suffix=".FOR", delete=False) as f:
        f.write(src)
        path = f.name
    try:
        stmts = expand_includes(scan_file(path, dialect=dlc).statements, os.path.dirname(path))
        errs = []
        units = parse_units(
            stmts, dialect=dlc, on_error=lambda st, m: errs.append((st.line, m, st.text))
        )
        if errs:
            raise AssertionError(
                "parse errors: " + "; ".join(f"L{ln}: {m} | {t}" for ln, m, t in errs)
            )
        feed = iter(inputs or [])
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

"""pyf66 -- a FORTRAN-66 / DEC FORTRAN-10 interpreter in Python.

A faithful interpreter for 1970s DEC FORTRAN-10 / FORTRAN-66, with the machine value
model (36-bit words, SIXBIT/A5 packing, .TRUE.=-1) and the front-end dialect both
pluggable. PDP-10/FORTRAN-10 is the default and shipped target.

Quick start::

    import f66
    eng = f66.run_source('''      PROGRAM HI
          WRITE(6,10)
     10   FORMAT(' HELLO, WORLD')
          END
    ''', printer=print)

Public API:
    Engine, Frame, StopExecution    -- the execution engine
    Target, PDP10, NATIVE           -- the machine value model (NATIVE 64-bit is the
                                       default; PDP10 is the faithful 36-bit DEC target)
    Dialect, FORTRAN10, STRICT_F66  -- front-end dialect selection
    STDLIB                          -- the standard FORTRAN-10 intrinsic/library table
    install_runtime(eng)            -- wire the FORTRAN-10 runtime (STDLIB + FOROTS I/O)
    make_engine(units, ...)         -- build a ready-to-run engine
    parse_source(text, ...)         -- parse source text into program units
    run_source(text, ...)           -- parse + run a source string, return the Engine
"""
from f66.engine import Engine, Frame, StopExecution
from f66.target import Target, PDP10, NATIVE
from f66.dialect import Dialect, FORTRAN10, STRICT_F66
from f66.forlib import STDLIB
from f66 import forbin

__version__ = "0.1.0"

__all__ = [
    "Engine", "Frame", "StopExecution", "Target", "PDP10", "NATIVE",
    "Dialect", "FORTRAN10", "STRICT_F66", "STDLIB", "forbin",
    "install_runtime", "make_engine", "parse_source", "run_source",
]


def install_runtime(eng):
    """Install the DEC FORTRAN-10 runtime onto an engine: the standard library and the
    FOROTS unformatted-I/O codec used by binary (unformatted) READ/WRITE."""
    eng.register_builtins(STDLIB)
    eng.binio = forbin
    return eng


def make_engine(units, **kwargs):
    """Build an Engine over `units` ({name: ProgramUnit}) with the FORTRAN-10 runtime
    installed and ready to run. Extra kwargs (root, emit, readline, getch, printer,
    target, ...) pass through to Engine."""
    eng = Engine(units, **kwargs)
    install_runtime(eng)
    return eng


def parse_source(text, dialect=FORTRAN10):
    """Parse FORTRAN source text into a {name: ProgramUnit} dict."""
    import os
    import tempfile
    from f66.source import scan_file, expand_includes
    from f66.parser import parse_units
    with tempfile.NamedTemporaryFile("w", suffix=".FOR", delete=False) as fh:
        fh.write(text)
        path = fh.name
    try:
        stmts = expand_includes(scan_file(path, dialect=dialect).statements,
                                os.path.dirname(path))
        return {u.name: u for u in parse_units(stmts, dialect=dialect)}
    finally:
        os.unlink(path)


def run_source(text, program=None, dialect=FORTRAN10, **kwargs):
    """Parse + run a FORTRAN source string; return the Engine to inspect its state.
    `program` selects the main PROGRAM (defaults to the first program unit)."""
    units = parse_source(text, dialect=dialect)
    eng = make_engine(units, **kwargs)
    name = program or next((n for n, u in units.items() if u.kind == "program"), None)
    try:
        eng.run(Frame(eng.rts[name], {}))
    except StopExecution:
        pass
    return eng

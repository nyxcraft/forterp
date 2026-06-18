"""pyf66 -- a FORTRAN-66 / DEC FORTRAN-10 interpreter in Python.

A configurable FORTRAN-66 interpreter: the machine value model (`Target`) and the
front-end dialect (`Dialect`) are both pluggable. The default target is NATIVE (a
portable 64-bit host); PDP10 (36-bit, packed ASCII, .TRUE.=-1) is the faithful DEC
FORTRAN-10 target, selected with `Engine(..., target=PDP10)`.

Quick start::

    import f66
    eng = f66.run_source('''      PROGRAM HI
          WRITE(6,10)
     10   FORMAT(' HELLO, WORLD')
          END
    ''', printer=print)

Public API:
    Engine, Frame, StopExecution    -- the execution engine
    Target, PDP10, NATIVE, VAX      -- the machine value model (NATIVE 64-bit is the
                                       default; PDP10 is the faithful 36-bit DEC target;
                                       VAX is a provisional/unvalidated 32-bit target)
    Dialect, FORTRAN10, STRICT_F66  -- front-end dialect selection
    STDLIB                          -- the standard FORTRAN-10 intrinsic/library table
    install_runtime(eng)            -- wire the FORTRAN-10 runtime (STDLIB + FOROTS I/O)
    make_engine(units, ...)         -- build a ready-to-run engine
    parse_source(text, ...)         -- parse source text into program units (raises ParseError)
    run_source(text, ...)           -- parse + run a source string, return the Engine
    ParseError                      -- raised by parse_source/run_source on bad source
"""
from f66.engine import Engine, Frame, StopExecution
from f66.parser import ParseError
from f66.target import Target, PDP10, NATIVE, VAX
from f66.dialect import Dialect, FORTRAN10, STRICT_F66
from f66.forlib import STDLIB
from f66 import forbin

__version__ = "0.1.0"

__all__ = [
    "Engine", "Frame", "StopExecution", "ParseError",
    "Target", "PDP10", "NATIVE", "VAX",
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


def parse_source(text, dialect=FORTRAN10, on_error=None):
    """Parse FORTRAN source text into a {name: ProgramUnit} dict.

    Raises ``ParseError`` on malformed source, with every diagnostic in the message --
    invalid statements are NOT silently dropped. Pass ``on_error(statement, message)``
    to instead receive each diagnostic yourself and keep the (partial) result.
    """
    import os
    import tempfile
    from f66.source import scan_file, expand_includes
    from f66.parser import parse_units
    errs = []
    cb = on_error if on_error is not None else (lambda st, m: errs.append((st.line, m)))
    with tempfile.NamedTemporaryFile("w", suffix=".FOR", delete=False) as fh:
        fh.write(text)
        path = fh.name
    try:
        stmts = expand_includes(scan_file(path, dialect=dialect).statements,
                                os.path.dirname(path))
        units = {u.name: u for u in parse_units(stmts, dialect=dialect, on_error=cb)}
    finally:
        os.unlink(path)
    if on_error is None and errs:
        raise ParseError("parse error(s):\n"
                         + "\n".join(f"  line {ln}: {m}" for ln, m in errs))
    return units


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

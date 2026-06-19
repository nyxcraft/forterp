"""forterp -- a configurable FORTRAN-66 / DEC FORTRAN-10 interpreter in Python.

A configurable FORTRAN-66 interpreter: the machine value model (`Target`) and the
front-end dialect (`Dialect`) are both pluggable. The default target is NATIVE (a
portable 64-bit host); PDP10 (36-bit, packed ASCII, .TRUE.=-1) is the faithful DEC
FORTRAN-10 target, selected with `Engine(..., target=PDP10)`.

Quick start::

    import forterp
    eng = forterp.run_source('''      PROGRAM HI
          WRITE(6,10)
     10   FORMAT(' HELLO, WORLD')
          END
    ''', printer=print)

Public API:
    Engine, Frame, StopExecution    -- the execution engine
    Target, PDP10, NATIVE, VAX      -- the machine value model (NATIVE 64-bit is the
                                       default; PDP10 is the faithful 36-bit DEC target;
                                       VAX is a provisional/unvalidated 32-bit target)
    Dialect, F66, FORTRAN10         -- front-end dialect (F66 is the default; FORTRAN10
                                       is the DEC superset: octal/tab/!/free-form input)
    SourceOptions                   -- source-recovery handling (orthogonal to the
                                       dialect; e.g. recover statement text shifted past
                                       col 72). Default: faithful, no recovery.
    STDLIB                          -- the standard FORTRAN-10 intrinsic/library table
    install_runtime(eng)            -- wire the FORTRAN-10 runtime (STDLIB + FOROTS I/O)
    make_engine(units, ...)         -- build a ready-to-run engine
    parse_source(text, ...)         -- parse source text into program units (raises ParseError)
    run_source(text, ...)           -- parse + run a source string, return the Engine
    ParseError                      -- raised by parse_source/run_source on bad source
"""

from forterp.engine import Engine, Frame, StopExecution
from forterp.parser import ParseError, parse_expression
from forterp.target import Target, PDP10, NATIVE, VAX, TARGETS
from forterp.dialect import Dialect, F66, FORTRAN10, DIALECTS
from forterp.source import SourceOptions
from forterp.forlib import STDLIB
from forterp import forbin

__version__ = "0.1.0"

__all__ = [
    "Engine",
    "Frame",
    "StopExecution",
    "ParseError",
    "Target",
    "PDP10",
    "NATIVE",
    "VAX",
    "Dialect",
    "F66",
    "FORTRAN10",
    "TARGETS",
    "DIALECTS",
    "SourceOptions",
    "STDLIB",
    "forbin",
    "install_runtime",
    "engine_kwargs",
    "make_engine",
    "parse_source",
    "parse_expression",
    "run_source",
]


def install_runtime(eng):
    """Install the DEC FORTRAN-10 runtime onto an engine: the standard library and the
    FOROTS unformatted-I/O codec used by binary (unformatted) READ/WRITE."""
    eng.register_builtins(STDLIB)
    eng.binio = forbin
    return eng


def engine_kwargs(dialect):
    """The dialect-derived runtime behaviors the Engine needs -- it is otherwise
    dialect-agnostic: `free_form_input` (widthless input fields read free-form vs
    column) and `dec_intrinsics` (the DEC/F77 library beyond F66 Tables 3 & 4). The
    single source of truth, so adding a future engine-relevant dialect flag is a
    one-line change here rather than an edit at every engine-construction site."""
    return {
        "free_form_input": dialect.free_form_input,
        "dec_intrinsics": dialect.dec_intrinsics,
    }


def make_engine(units, dialect=None, **kwargs):
    """Build an Engine over `units` ({name: ProgramUnit}) with the FORTRAN-10 runtime
    installed and ready to run. Passing `dialect` applies its engine-relevant flags (see
    engine_kwargs); explicit kwargs win. Other kwargs (root, emit, readline, getch,
    printer, target, ...) pass through to Engine."""
    if dialect is not None:
        kwargs = {**engine_kwargs(dialect), **kwargs}
    eng = Engine(units, **kwargs)
    install_runtime(eng)
    return eng


def parse_source(text, dialect=F66, on_error=None, options=None):
    """Parse FORTRAN source text into a {name: ProgramUnit} dict.

    `dialect` selects the language (F66 default / FORTRAN10 superset). `options` is a
    `SourceOptions` for source-recovery handling (orthogonal to the dialect; default is
    faithful, no recovery).

    Raises ``ParseError`` on malformed source, with every diagnostic in the message --
    invalid statements are NOT silently dropped. Pass ``on_error(statement, message)``
    to instead receive each diagnostic yourself and keep the (partial) result.
    """
    from forterp.source import scan_text, expand_includes, DEFAULT_OPTIONS
    from forterp.parser import parse_units

    errs = []
    cb = on_error if on_error is not None else (lambda st, m: errs.append((st.line, m)))
    opts = options if options is not None else DEFAULT_OPTIONS
    stmts = expand_includes(scan_text(text, dialect=dialect, options=opts).statements, ".")
    units = {u.name: u for u in parse_units(stmts, dialect=dialect, on_error=cb)}
    if on_error is None and errs:
        raise ParseError("parse error(s):\n" + "\n".join(f"  line {ln}: {m}" for ln, m in errs))
    return units


def run_source(text, program=None, dialect=F66, options=None, **kwargs):
    """Parse + run a FORTRAN source string; return the Engine to inspect its state.
    `program` selects the main PROGRAM (defaults to the first program unit). `options`
    is an optional `SourceOptions` for source-recovery handling."""
    units = parse_source(text, dialect=dialect, options=options)
    eng = make_engine(units, dialect=dialect, **kwargs)
    name = program or next((n for n, u in units.items() if u.kind == "program"), None)
    try:
        eng.run(Frame(eng.rts[name], {}))
    except StopExecution:
        pass
    return eng

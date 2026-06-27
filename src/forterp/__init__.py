"""forterp -- a configurable FORTRAN 66 / 77 / DEC FORTRAN-10 interpreter in Python.

The machine value model (`Target`) and the front-end dialect (`Dialect`) are both
pluggable. Dialects: F77 (the default, full ANSI X3.9-1978), F66 (strict ANSI
X3.9-1966), and FORTRAN10 (the DEC FORTRAN-10 superset). The default target
is NATIVE (a portable 64-bit host); PDP10 (36-bit, packed ASCII, .TRUE.=-1) is the
faithful DEC FORTRAN-10 target, selected with `Engine(..., target=PDP10)`.

Quick start::

    import forterp
    eng = forterp.run_source('''      PROGRAM HI
          WRITE(6,10)
     10   FORMAT(' HELLO, WORLD')
          END
    ''', printer=print)

Public API (see ``__all__``):
    run_source(text, ...)       -- parse + run a source string; returns the Engine
    parse_source(text, ...)     -- parse source -> {name: ProgramUnit} (raises ParseError)
    f66, fortran10              -- prebuilt, ready-to-run interpreters (the easy path:
                                   forterp.fortran10.run_source(src) / .parse_dir(dir) /
                                   .build_engine(units)); Interpreter to roll your own
    F77, F66, FORTRAN10, Dialect -- the front-end dialect (F77 is the default; F66 strict ANSI;
                                   FORTRAN10 the DEC superset: octal / tab-format / '!' / free-form)
    NATIVE, PDP10, VAX, Target  -- the machine value model (NATIVE 64-bit is the default;
                                   PDP10 the 36-bit DEC target; VAX provisional)
    ParseError, SourceOptions   -- the parse error, and source-recovery options (orthogonal
                                   to the dialect; default: no recovery)

Expert surfaces live behind explicit namespaces (the package root exposes only the names in
``__all__`` above -- there are no back-compat aliases):
    forterp.frontend  -- lexer + parser stages (scan_file, parse_units, tokenize, ...)
    forterp.format    -- the FORMAT engine (parse_format, render, read_values, ...)
    forterp.runtime   -- the Engine and engine builders (Engine, Frame, make_engine, ...)
    forterp.hostlib   -- declarative marshalling for host-defined builtins
    forterp.ast       -- the AST node classes the parser produces
    forterp.debug     -- OOB-access census + the interactive tracer / profiler
"""

# The package root exposes ONLY the focused public surface (see __all__). Everything else --
# the Engine and builders, the lexer/parser stages, the FORMAT engine, the AST nodes -- lives
# in the expert namespaces (forterp.frontend / .format / .runtime / .ast / .hostlib), imported
# at the bottom of this module. There are no back-compat root aliases.
from forterp.dialect import F66, F77, FORTRAN10, Dialect
from forterp.interpreter import Interpreter, f66, f77, fortran10
from forterp.parser import ParseError
from forterp.source import SourceOptions
from forterp.target import LP64LE, NATIVE, PDP10, VAX, Target
from forterp.uuolib import UnmodeledMonitorTable

# The one place the version is written. pyproject.toml reads it via
# [tool.setuptools.dynamic] (attr = "forterp.__version__"), so the package metadata and
# this attribute can never drift apart.
__version__ = "0.2.0"

# The complete public surface: the package root exposes exactly these names. Everything else
# lives in the expert namespaces (forterp.frontend / .format / .runtime / .ast / .hostlib).
__all__ = [
    # parse + run
    "run_source",
    "parse_source",
    # prebuilt interpreters and the class behind them
    "f66",
    "f77",
    "fortran10",
    "Interpreter",
    # dialects
    "F66",
    "F77",
    "FORTRAN10",
    "Dialect",
    # machine value models
    "NATIVE",
    "PDP10",
    "VAX",
    "LP64LE",
    "Target",
    # commonly-needed types
    "ParseError",
    "SourceOptions",
    "UnmodeledMonitorTable",
]


def parse_source(text, dialect=F77, on_error=None, options=None, include_dir="."):
    """Parse FORTRAN source text into a {name: ProgramUnit} dict.

    `dialect` selects the language (F77 default; F66 strict / FORTRAN10 superset). `options` is a
    `SourceOptions` for source-recovery handling (orthogonal to the dialect; default is
    no recovery). `include_dir` is the base directory INCLUDE targets resolve
    against (default the current directory; the CLI passes the source file's directory).

    Raises ``ParseError`` on malformed source, with every diagnostic in the message --
    invalid statements are NOT silently dropped. Pass ``on_error(statement, message)``
    to instead receive each diagnostic yourself and keep the (partial) result.
    """
    from forterp.parser import parse_units
    from forterp.source import DEFAULT_OPTIONS, expand_includes, scan_text

    errs = []
    cb = on_error if on_error is not None else (lambda st, m: errs.append((st.line, m)))
    opts = options if options is not None else DEFAULT_OPTIONS
    stmts = expand_includes(
        scan_text(text, dialect=dialect, options=opts).statements, include_dir, dialect=dialect
    )
    units = {u.name: u for u in parse_units(stmts, dialect=dialect, on_error=cb)}
    if on_error is None and errs:
        raise ParseError("parse error(s):\n" + "\n".join(f"  line {ln}: {m}" for ln, m in errs))
    return units


def run_source(
    text, program=None, dialect=F77, options=None, include_dir=".", setup=None, **kwargs
):
    """Parse + run a FORTRAN source string; return the Engine to inspect its state.
    `program` selects the main PROGRAM (defaults to the first program unit). `options`
    is an optional `SourceOptions` for source-recovery handling. `include_dir` is the
    base directory for INCLUDE resolution (default the current directory). `setup` is an
    optional `fn(eng)` called after the engine is built and the runtime/builtins installed,
    but before the program runs -- the place to register OPEN devices, prime COMMON, or do
    any host-side engine setup the program needs."""
    from forterp.runtime import default_terminal_echo, make_engine

    units = parse_source(text, dialect=dialect, options=options, include_dir=include_dir)
    eng = make_engine(units, dialect=dialect, **kwargs)
    # Default terminal-echo control: unless the caller wired its own `set_echo`, honor the
    # program's ECHOON/ECHOFF on an interactive tty (no-op off a terminal), restored after.
    restore = None
    if "set_echo" not in kwargs:
        set_echo, restore = default_terminal_echo()
        if set_echo is not None:
            eng._set_echo = set_echo
    if setup is not None:
        setup(eng)
    try:
        return eng.run_program(program)
    finally:
        if restore is not None:
            restore()


# Expert namespaces -- the organized API beyond the focused public names above:
# forterp.frontend (lexer/parser), .format (FORMAT engine), .runtime (Engine + builders),
# .ast (AST nodes), .hostlib (host-builtin marshalling), .debug (OOB census + tracer).
from forterp import ast, debug, format, frontend, hostlib, runtime  # noqa: E402,F401

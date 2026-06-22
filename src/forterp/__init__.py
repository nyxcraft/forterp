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

Public API (see ``__all__``):
    run_source(text, ...)       -- parse + run a source string; returns the Engine
    parse_source(text, ...)     -- parse source -> {name: ProgramUnit} (raises ParseError)
    f66, fortran10              -- prebuilt, ready-to-run interpreters (the easy path:
                                   forterp.fortran10.run_source(src) / .parse_dir(dir) /
                                   .build_engine(units)); Interpreter to roll your own
    F66, FORTRAN10, Dialect     -- the front-end dialect (F66 is the default; FORTRAN10 the
                                   DEC superset: octal / tab-format / '!' / free-form input)
    NATIVE, PDP10, VAX, Target  -- the machine value model (NATIVE 64-bit is the default;
                                   PDP10 the 36-bit DEC target; VAX provisional)
    ParseError, SourceOptions   -- the parse error, and source-recovery options (orthogonal
                                   to the dialect; default: no recovery)

Expert surfaces live behind explicit namespaces (their names also remain importable from
the package root as deprecated aliases):
    forterp.frontend  -- lexer + parser stages (scan_file, parse_units, tokenize, ...)
    forterp.format    -- the FORMAT engine (parse_format, render, read_values, ...)
    forterp.runtime   -- the Engine and engine builders (Engine, Frame, make_engine, ...)
    forterp.hostlib   -- declarative marshalling for host-defined builtins
    forterp.ast       -- the AST node classes the parser produces
"""

# The focused public surface (see __all__).
from forterp import ast_nodes, forbin  # noqa: F401
from forterp.diagnostics import diag, show  # noqa: F401
from forterp.dialect import (
    DIALECTS,  # noqa: F401
    F66,
    FORTRAN10,
    Dialect,
)

# Deprecated root aliases. The organized homes are the forterp.frontend / .format /
# .runtime / .ast namespaces (and forterp.hostlib); these names stay importable from the
# package root for back-compat and are deliberately kept off __all__.
from forterp.engine import ArrayView, Engine, Frame, StopExecution, TempRef  # noqa: F401
from forterp.fmt import (  # noqa: F401
    InputConversionError,
    apply_carriage,
    parse_format,
    read_values,
    render,
)
from forterp.forlib import STDLIB

# Prebuilt, reusable interpreters -- the easy-reuse entry point: forterp.fortran10
# (faithful DEC FORTRAN-10) and forterp.f66 (strict ANSI), plus the Interpreter class.
from forterp.interpreter import Interpreter, f66, fortran10
from forterp.lexer import LexError, Token, tokenize  # noqa: F401
from forterp.parser import ParseError, parse_expression, parse_units  # noqa: F401
from forterp.source import SourceOptions, expand_includes, scan_file  # noqa: F401
from forterp.target import (
    NATIVE,
    PDP10,
    TARGETS,  # noqa: F401
    VAX,
    Target,
)

# The one place the version is written. pyproject.toml reads it via
# [tool.setuptools.dynamic] (attr = "forterp.__version__"), so the package metadata and
# this attribute can never drift apart.
__version__ = "0.1.0"

# The focused public surface. Expert layers live behind explicit namespaces --
# forterp.frontend (lexer/parser stages), forterp.format (the FORMAT engine),
# forterp.runtime (Engine + builders), forterp.hostlib, forterp.ast -- and many of
# their names also remain importable from the package root as deprecated aliases.
__all__ = [
    # parse + run
    "run_source",
    "parse_source",
    # prebuilt interpreters and the class behind them
    "f66",
    "fortran10",
    "Interpreter",
    # dialects
    "F66",
    "FORTRAN10",
    "Dialect",
    # machine value models
    "NATIVE",
    "PDP10",
    "VAX",
    "Target",
    # commonly-needed types
    "ParseError",
    "SourceOptions",
]


def install_runtime(eng):
    """Install the DEC FORTRAN-10 runtime onto an engine: the DEC library subprograms and
    the FOROTS unformatted-I/O codec used by binary (unformatted) READ/WRITE.

    The DEC library (RAN, DATE, ERRSET, ...) is a DEC facility, absent from strict ANSI
    F66 -- so it is installed only when the engine's `dec_intrinsics` is on. A library
    name that the program defines itself is never shadowed (the program's unit wins)."""
    if eng.dec_intrinsics:
        eng.register_builtins({k: v for k, v in STDLIB.items() if k not in eng.units})
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


def parse_source(text, dialect=F66, on_error=None, options=None, include_dir="."):
    """Parse FORTRAN source text into a {name: ProgramUnit} dict.

    `dialect` selects the language (F66 default / FORTRAN10 superset). `options` is a
    `SourceOptions` for source-recovery handling (orthogonal to the dialect; default is
    no recovery). `include_dir` is the base directory INCLUDE targets resolve
    against (default the current directory; the CLI passes the source file's directory).

    Raises ``ParseError`` on malformed source, with every diagnostic in the message --
    invalid statements are NOT silently dropped. Pass ``on_error(statement, message)``
    to instead receive each diagnostic yourself and keep the (partial) result.
    """
    from forterp.source import DEFAULT_OPTIONS, scan_text

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


def run_source(text, program=None, dialect=F66, options=None, include_dir=".", **kwargs):
    """Parse + run a FORTRAN source string; return the Engine to inspect its state.
    `program` selects the main PROGRAM (defaults to the first program unit). `options`
    is an optional `SourceOptions` for source-recovery handling. `include_dir` is the
    base directory for INCLUDE resolution (default the current directory)."""
    units = parse_source(text, dialect=dialect, options=options, include_dir=include_dir)
    eng = make_engine(units, dialect=dialect, **kwargs)
    return eng.run_program(program)


# Expert namespaces -- imported last so forterp.runtime can re-export the builders defined
# above. `forterp.frontend / .format / .runtime / .ast / .hostlib` organize the surface that
# used to crowd the package root.
from forterp import ast, format, frontend, hostlib, runtime  # noqa: E402,F401

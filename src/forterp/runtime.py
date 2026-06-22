"""Engine construction and the installable runtime (expert/embedding API).

The `Engine` and its reference objects, plus the helpers that wire a dialect's behavior and
the DEC FORTRAN-10 library onto an engine. The focused top-level API (`run_source` /
`parse_source` / the prebuilt `f66` & `fortran10` interpreters) is usually enough; reach
here to build and drive engines yourself.
"""

from forterp import forbin
from forterp.engine import ArrayView, Engine, Frame, StopExecution, TempRef
from forterp.forlib import STDLIB

__all__ = [
    "Engine",
    "Frame",
    "StopExecution",
    "ArrayView",
    "TempRef",
    "STDLIB",
    "forbin",
    "make_engine",
    "install_runtime",
    "engine_kwargs",
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


def make_engine(units, dialect=None, builtins=None, **kwargs):
    """Build an Engine over `units` ({name: ProgramUnit}) with the FORTRAN-10 runtime
    installed and ready to run. Passing `dialect` applies its engine-relevant flags (see
    engine_kwargs); explicit kwargs win. `builtins` is an optional {name: fn} table of extra
    host routines, registered after the standard library so they extend or override it. Other
    kwargs (root, emit, readline, getch, printer, target, ...) pass through to Engine."""
    if dialect is not None:
        kwargs = {**engine_kwargs(dialect), **kwargs}
    eng = Engine(units, **kwargs)
    install_runtime(eng)
    if builtins:
        eng.register_builtins(dict(builtins))
    return eng

"""Engine construction and the installable runtime (expert/embedding API).

The `Engine` and its reference objects, plus the helpers that wire a dialect's behavior and
the DEC FORTRAN-10 library onto an engine. The focused top-level API (`run_source` /
`parse_source` / the prebuilt `f66` & `fortran10` interpreters) is usually enough; reach
here to build and drive engines yourself.
"""

from forterp import forbin
from forterp.engine import ArrayView, Engine, Frame, StopExecution, TempRef
from forterp.forlib import STDLIB
from forterp.uuolib import UUOLIB

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
    "default_terminal_echo",
]


def install_runtime(eng):
    """Install the DEC FORTRAN-10 runtime onto an engine: the DEC library subprograms and
    the FOROTS unformatted-I/O codec used by binary (unformatted) READ/WRITE.

    The DEC library (RAN, DATE, ERRSET, ...) is a DEC facility, absent from strict ANSI
    F66 -- so it is installed only when the engine's `dec_intrinsics` is on. A library
    name that the program defines itself is never shadowed (the program's unit wins).

    The standard TOPS-10 monitor UUOs (OUTSTR/OUTCHR/MSTIME/SLEEP/GETTAB; see `uuolib`) install
    on the same FORTRAN-10 gate, so a program that CALLs them just runs; a host registering its
    own (richer/translated) variant afterward overrides these baseline ones."""
    if eng.dec_intrinsics:
        eng.register_builtins({k: v for k, v in STDLIB.items() if k not in eng.units})
        eng.register_builtins({k: v for k, v in UUOLIB.items() if k not in eng.units})
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
        "character_type": dialect.character_type,
        "zero_trip_do": dialect.zero_trip_do,
    }


def forots_default(target, dialect):
    """Default for Engine.forots (run under the FORTRAN-10 Object Time System): True only for
    real DEC FORTRAN-10 -- the PDP10 target (36-bit words / PDP-10 floats) AND the FORTRAN10
    dialect (FOROTS is FORTRAN-10's runtime, not a generic PDP-10 thing). Any other target or
    dialect stays portable (newline-after + JSON files). Callers may override explicitly."""
    from forterp.dialect import FORTRAN10
    from forterp.target import PDP10

    return target is PDP10 and dialect is FORTRAN10


def make_engine(units, dialect=None, builtins=None, monitor=None, **kwargs):
    """Build an Engine over `units` ({name: ProgramUnit}) with the FORTRAN-10 runtime
    installed and ready to run. Passing `dialect` applies its engine-relevant flags (see
    engine_kwargs); explicit kwargs win. `builtins` is an optional {name: fn} table of extra
    host routines, registered after the standard library so they extend or override it.
    `monitor` is an optional factory `fn(eng) -> facade` (e.g. a `hostlib.Monitor`
    subclass) installed as `eng.monitor` so `@uuo` routines use it instead of the baseline.
    Other kwargs (root, emit, readline, getch, printer, target, ...) pass through to Engine."""
    if dialect is not None:
        kwargs = {**engine_kwargs(dialect), **kwargs}
        kwargs.setdefault("forots", forots_default(kwargs.get("target"), dialect))
    eng = Engine(units, **kwargs)
    install_runtime(eng)
    if monitor is not None:
        eng.monitor = monitor(eng)
    if builtins:
        # a program's own unit wins over a same-named host builtin (as install_runtime does)
        eng.register_builtins({k: v for k, v in builtins.items() if k not in eng.units})
    return eng


def default_terminal_echo(fd=None):
    """The default terminal-echo control for `eng.set_echo`: flip the controlling tty's termios
    `ECHO` bit, lazily saving the original on first use. Returns `(set_echo, restore)`, or
    `(None, None)` when `fd` (default stdin) isn't a terminal -- piped/redirected, or no termios
    -- so it's a clean no-op there.

    A program's `ECHOON`/`ECHOFF` (e.g. a TOPS-10 SETSTS/INIT host routine) drives `eng.set_echo`;
    `run_source` installs this by default so that "just works" on an interactive terminal without
    each front-end re-rolling termios. A front-end that owns the terminal differently (a raw
    char-mode reader, a GUI) passes its own `set_echo` instead, and `restore()` undoes any change
    at the end of the run (so a program that left echo off can't leave the shell silent)."""
    import sys

    try:
        import termios

        if fd is None:
            fd = sys.stdin.fileno()
        termios.tcgetattr(fd)  # raises unless fd is a real terminal
    except Exception:
        return None, None

    saved = []

    def set_echo(on):
        if not saved:  # capture the entry state once, so restore() can put it back
            saved.append(termios.tcgetattr(fd))
        mode = termios.tcgetattr(fd)
        mode[3] = (mode[3] | termios.ECHO) if on else (mode[3] & ~termios.ECHO)  # lflag ECHO
        termios.tcsetattr(fd, termios.TCSANOW, mode)

    def restore():
        if saved:
            try:
                termios.tcsetattr(fd, termios.TCSADRAIN, saved[0])
            except Exception:
                pass

    return set_echo, restore

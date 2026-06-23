"""Declarative authoring for host routines (builtins).

A builtin is the uniform callable ``fn(eng, frame, arg_nodes)`` registered via
``eng.register_builtins`` and dispatched identically for a function reference (its
return value is used) and a ``CALL`` statement (its return value is ignored). Writing
one by hand means repeating ``eng.eval(arg_nodes[i], frame)`` to read inputs and
``eng.arg_ref(arg_nodes[j], frame).write(v)`` to write outputs, which buries the actual
logic and is easy to get subtly wrong (wrong index, a read where a write was meant, a
forgotten by-reference handle).

This module lets a host declare each parameter's *mode* instead, so the body is clean
Python and the marshalling is generated::

    from forterp.hostlib import builtin, INT, OUT, ARRAY

    @builtin("IDIST", args=(INT, INT))
    def idist(a, b):                       # inputs arrive as plain Python values
        return max(abs(a // 100 - b // 100), abs(a % 100 - b % 100))

    @builtin("SWAP", args=(OUT, OUT))      # by-reference outputs arrive as handles
    def swap(x, y):
        a, b = x.get(), y.get()
        x.set(b); y.set(a)

A routine that is both a function and writes arguments (the common PDP-10 case) just
``return``\\ s its value *and* writes its OUT handles -- there is no separate
"subroutine" decorator, because forterp's dispatch is already uniform.

For the routines that genuinely need the AST nodes and engine internals -- block moves,
by-name COMMON access, variadics -- declare ``raw=True`` and the body receives the
unwrapped ``(eng, frame, arg_nodes)``. This escape hatch lives in the *same* registry
and is a first-class mode, so a host never has to fork into a second, lower-level
convention for its messy 30%.

``OutRef`` deliberately hides the engine's private reference objects
(``CellRef``/``ArrayView``/``TempRef``) behind ``get``/``set`` (plus ``get_at``/``set_at``
and the raw ``store``/``base`` for the rare block op), so host code stops reaching into
engine internals directly.

Two kinds of host routine, two decorators
-----------------------------------------
The PDP-10 programs this serves had host routines of two kinds: pure *computation* called
through the FORTRAN calling sequence, and routines that *talk to the operating system*
(terminal I/O, file reads, the clock). forterp is an interpreter, not an emulator, so there
is no literal UUO trap -- a "system call" is just a CALL to a host subroutine -- but the
*services* such a routine needs are real and generic, so this module provides them:

- ``@fcall`` (an alias of ``@builtin``) -- a FORTRAN-callable computation.
- ``@uuo`` -- a routine that talks to the host: its body receives a baseline ``Host``
  facade (``mon``: ``tty`` / ``files`` / ``clock``, over the engine's host seam) as its first
  argument.

The facade is **injectable**: an embedder may set ``eng.host`` to a *richer* facade
(one that adds OS-level identity, locks, shared memory, ...) before the engine runs, and
``@uuo`` routines receive that instead of the baseline. So a fuller monitor layers on without
forterp depending on it -- the baseline alone is enough to run a program that only needs basic
I/O.
"""

import os

from forterp.ast import StrLit

__all__ = [
    "Mode",
    "IN",
    "INT",
    "FLOAT",
    "STR",
    "OUT",
    "INOUT",
    "ARRAY",
    "OutRef",
    "builtin",
    "fcall",
    "uuo",
    "make_builtin",
    "builtins_in",
    "Host",
    "host",
]


class Mode:
    """Binds one actual-argument node to the value or handle the body receives.

    Subclass and override ``bind`` to add host-specific modes (e.g. a string mode that
    knows a particular target's character packing)."""

    def bind(self, eng, frame, node):
        raise NotImplementedError


class _In(Mode):
    """By-value input: ``eng.eval`` the actual, with an optional coercion."""

    def __init__(self, coerce=None):
        self.coerce = coerce

    def bind(self, eng, frame, node):
        if node is None:  # fewer actuals than declared modes (an optional trailing arg)
            return None
        v = eng.eval(node, frame)
        return self.coerce(v) if self.coerce is not None else v


IN = _In()  # raw value (whatever eval returns: an int word, float, packed string, ...)
INT = _In(int)  # the overwhelmingly common case: an integer word
FLOAT = _In(float)


class _Str(Mode):
    """A string actual, as a Python ``str``: a quoted literal's text verbatim, or a packed-word
    value decoded through the target's char codec. Encapsulates the StrLit-vs-packed-word
    resolution that string/filename args (OUTSTR, OPEN's ``FILE=``, a save-detect) all repeat,
    so the body doesn't reach for ``eng.eval``/``tgt.unpack`` itself."""

    def bind(self, eng, frame, node):
        if node is None:
            return None
        if isinstance(node, StrLit):  # a quoted literal -> its text verbatim (no word-packing)
            return node.value
        v = eng.eval(node, frame)
        return eng.tgt.unpack(v) if isinstance(v, int) else str(v)


STR = _Str()  # a string / filename arg -> Python str (literal text, or a packed word decoded)


class OutRef:
    """Writable handle over a forterp argument reference (a ``CellRef`` for a scalar or
    array element, a ``TempRef`` for a by-value/const actual, an ``ArrayView`` for a whole
    array). Scalars use ``get``/``set``; arrays use ``get_at``/``set_at`` (or ``loc``);
    block ops reach the backing ``store``/``base`` directly."""

    __slots__ = ("ref",)

    def __init__(self, ref):
        self.ref = ref

    # scalar / element access
    def get(self):
        return self.ref.read()

    def set(self, v):
        self.ref.write(v)

    # whole-array access (ref is an ArrayView)
    def loc(self, i):
        return self.ref.loc(i)

    def get_at(self, i):
        return self.ref.loc(i).read()

    def set_at(self, i, v):
        self.ref.loc(i).write(v)

    # the backing list + offset, for block moves / fills that index memory directly
    @property
    def store(self):
        return getattr(self.ref, "store", None)

    @property
    def base(self):
        r = self.ref
        return getattr(r, "base", getattr(r, "idx", None))


class _Out(Mode):
    """By-reference argument: an ``OutRef`` over ``eng.arg_ref``. Used for OUT (write),
    INOUT (read-modify-write), and whole arrays."""

    def bind(self, eng, frame, node):
        if node is None:
            return None
        return OutRef(eng.arg_ref(node, frame))


OUT = _Out()  # the body writes via .set(v)
INOUT = _Out()  # the body reads .get() then writes .set(v)
ARRAY = _Out()  # the body uses .get_at(i)/.set_at(i,v)/.store/.base


def make_builtin(fn, *, args=None, raw=False):
    """Wrap a clean-body function into the uniform ``fn(eng, frame, arg_nodes)`` callable.

    ``raw=True`` passes the body through unchanged (it is the escape hatch and receives
    ``(eng, frame, arg_nodes)``). Otherwise ``args`` is a tuple of ``Mode`` instances, one
    per parameter; each actual is bound per its mode and the body is called with the bound
    values/handles. The body's return value is propagated (used by the function-reference
    dispatch path, ignored by ``CALL``)."""
    if raw:
        return fn
    modes = tuple(args or ())

    def wrapper(eng, frame, arg_nodes):
        bound = [
            mode.bind(eng, frame, arg_nodes[i] if i < len(arg_nodes) else None)
            for i, mode in enumerate(modes)
        ]
        return fn(*bound)

    wrapper.__name__ = getattr(fn, "__name__", "builtin")
    wrapper.__doc__ = fn.__doc__
    return wrapper


def _aliases(alias):
    """Normalize an ``alias=`` argument to a tuple of extra names."""
    if not alias:
        return ()
    return tuple(alias) if isinstance(alias, (list, tuple)) else (alias,)


def _tag(wrapper, name, fn, alias=(), origin=None):
    """Attach the discovery/introspection metadata a registry reads off a wrapped builtin:
    its primary ``builtin_name``, any ``builtin_aliases`` (extra names registered to the same
    routine), an optional ``builtin_origin`` (free-form provenance, e.g. a source-file name),
    and ``fcall_fn`` -- the original documented body, for the doc lint and introspection."""
    wrapper.builtin_name = name
    wrapper.builtin_aliases = _aliases(alias)
    wrapper.builtin_origin = origin
    wrapper.fcall_fn = fn
    return wrapper


def builtin(name, *, args=None, raw=False, alias=(), origin=None):
    """Decorator: declare a builtin's calling convention. Attaches ``builtin_name`` and the
    original ``fcall_fn`` so a registry can collect ``{name: wrapper}`` and still reach the
    documented body. ``alias`` registers the same routine under extra names (a str or a
    list/tuple); ``origin`` records free-form provenance both surfaced via ``builtins_in``."""

    def deco(fn):
        wrapper = make_builtin(fn, args=args, raw=raw)
        return _tag(wrapper, name, fn, alias=alias, origin=origin)

    return deco


fcall = builtin  # a FORTRAN-callable computation -- the PDP-10 authoring name for @builtin


def builtins_in(module):
    """Collect the host builtins a module provides, as ``{name: wrapper}``.

    Two conventions, so a Python module can be dropped in beside FORTRAN source and have its
    routines discovered without a hand-written registry:

    - every ``@builtin``-decorated callable, keyed by its ``builtin_name``;
    - a module-level ``BUILTINS`` dict (e.g. one a registry built), merged on top.

    Used by the CLI to register host routines from ``.py`` arguments, and available to any
    embedder that wants the same drop-in discovery.
    """
    table = {}
    for value in vars(module).values():
        name = getattr(value, "builtin_name", None)
        if name and callable(value):
            table[name] = value
            for a in getattr(value, "builtin_aliases", ()):
                table[a] = value
    extra = getattr(module, "BUILTINS", None)
    if isinstance(extra, dict):
        table.update(extra)
    return table


# --------------------------------------------------------------------------------------------
# Baseline host services + the @uuo authoring decorator
#
# A @uuo routine talks to the host through a Host facade ("mon") rather than reaching
# eng.emit / eng.root / eng.clock itself, so "talks to the OS" is one explicit dependency. The
# baseline facade below is built over the engine's host seam only (no OS-level state); a richer
# facade is layered on by setting eng.host (see host()).
# --------------------------------------------------------------------------------------------


class _Tty:
    """The terminal: the (emit, getch, readline) seam, tracking the horizontal cursor column
    so a newline/space/tab can be column-aware, plus ``echo`` -- the terminal's echo mode the
    program toggles (the monitor's TTY echo, e.g. a TOPS-10 SETSTS/INIT for raw single-key
    input). Assigning ``echo`` drives the engine's ``set_echo`` hook, so the front-end changes
    its *actual* terminal mode; with no hook wired it just records the requested state."""

    def __init__(self, eng):
        self._eng = eng
        self.col = 0
        self._echo = True

    @property
    def echo(self):
        return self._echo

    @echo.setter
    def echo(self, on):
        self._echo = bool(on)
        setter = getattr(self._eng, "set_echo", None)
        if setter:  # drive the real terminal-mode change (front-ends that own a terminal)
            setter(self._echo)

    def write(self, s):
        if not s:
            return
        self._eng.emit(s)
        nl = s.rfind("\n")
        self.col = (len(s) - nl - 1) if nl >= 0 else self.col + len(s)

    def crlf(self):
        """A smart newline: only if not already at the left margin (no double blanks)."""
        if self.col > 0:
            self.write("\n")

    def space(self, n=1):
        self.write(" " * max(0, n))

    def tab(self, col):
        """Advance to absolute column `col` (no-op if already past it)."""
        if col > self.col:
            self.write(" " * (col - self.col))

    def getch(self):
        return self._eng.getch()

    def readline(self):
        return self._eng.readline()


class _Files:
    """Bundled read-only data files. The original routines OPEN/LOOKUP a host file; this reads
    a real file under the engine's root (or save root)."""

    def __init__(self, eng):
        self._eng = eng

    def root_path(self, name):
        return os.path.join(self._eng.root, name)

    def save_path(self, name):
        return os.path.join(self._eng.save_root, name)

    def read(self, name, *, missing=None, errors=None):
        """Read a file under the engine root; return `missing` if it isn't there."""
        try:
            with open(self.root_path(name), errors=errors) as fh:
                return fh.read()
        except OSError:
            return missing


class _Clock:
    """The clock the time UUOs read: the engine's fixed millisecond reading, plus a monotonic
    tick that advances a little per query so elapsed times stay positive."""

    def __init__(self, eng):
        self._eng = eng
        self._ms = 0

    @property
    def ms(self):
        return self._eng.clock

    def tick(self):
        self._ms += 100
        return self._ms


class Host:
    """The baseline host-services facade (``mon``) passed to ``@uuo`` routines: ``tty`` (the
    terminal seam), ``files`` (bundled data under the engine root), and ``clock``. Built over
    the engine's host seam only -- it carries no OS-level state, so it runs anywhere the engine
    does. A richer facade subclasses this (adding services, e.g. identity/locks) and is injected
    via ``eng.host`` (see ``host``)."""

    def __init__(self, eng):
        self.eng = eng
        self.tty = _Tty(eng)
        self.files = _Files(eng)
        self.clock = _Clock(eng)


def host(eng):
    """The engine's ``Host`` facade, building (and caching on ``eng.host``) the
    baseline on first use. An embedder may set ``eng.host`` to a richer facade before
    the engine runs to override the baseline -- ``@uuo`` routines then receive that instead."""
    mon = getattr(eng, "host", None)
    if mon is None:
        mon = Host(eng)
        eng.host = mon
    return mon


def uuo(name, *, args=None, raw=True, alias=(), origin=None):
    """Decorator for a host routine that talks to the host. Its body's first parameter is the
    ``Host`` facade (``mon``); with ``raw=True`` (the default) the rest of the body is
    ``(eng, frame, arg_nodes)``, otherwise the declared ``args`` modes follow ``mon`` (each
    actual marshalled exactly as for ``@builtin``). ``alias``/``origin`` behave as for
    ``@builtin``. Registered/discovered identically -- the only difference from ``@fcall`` is
    the injected ``mon`` first argument."""

    def deco(fn):
        if raw:

            def wrapper(eng, frame, arg_nodes):
                return fn(host(eng), eng, frame, arg_nodes)

        else:
            modes = tuple(args or ())

            def wrapper(eng, frame, arg_nodes):
                bound = [
                    m.bind(eng, frame, arg_nodes[i] if i < len(arg_nodes) else None)
                    for i, m in enumerate(modes)
                ]
                return fn(host(eng), *bound)

        wrapper.__name__ = getattr(fn, "__name__", name)
        wrapper.__doc__ = fn.__doc__
        return _tag(wrapper, name, fn, alias=alias, origin=origin)

    return deco

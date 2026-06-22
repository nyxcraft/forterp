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
"""

__all__ = [
    "Mode",
    "IN",
    "INT",
    "FLOAT",
    "OUT",
    "INOUT",
    "ARRAY",
    "OutRef",
    "builtin",
    "make_builtin",
    "builtins_in",
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


def builtin(name, *, args=None, raw=False):
    """Decorator: declare a builtin's calling convention. Attaches ``builtin_name`` and the
    original ``fcall_fn`` so a registry can collect ``{name: wrapper}`` and still reach the
    documented body."""

    def deco(fn):
        wrapper = make_builtin(fn, args=args, raw=raw)
        wrapper.builtin_name = name
        wrapper.fcall_fn = fn
        return wrapper

    return deco


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
    extra = getattr(module, "BUILTINS", None)
    if isinstance(extra, dict):
        table.update(extra)
    return table

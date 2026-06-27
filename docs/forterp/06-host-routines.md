# Host routines
## Custom host routines (builtins)

A host can add its own routines that FORTRAN `CALL`s or references — the
geometry/bit-packing/pathfinding helpers and the "system calls" (terminal I/O, file reads,
the clock) that programs of this era kept in hand-written assembly. `forterp.hostlib` is the
authoring layer: declare each parameter's *mode* and write a clean Python body; the argument
marshalling is generated. (For *how* it is generated, see the [design notes](11-seams-intrinsics.md).)

### Two decorators

The programs being run had host routines of two kinds, and there is a decorator for each:

- **`@fcall`** — a FORTRAN-callable *computation*. The body receives the
  marshalled arguments and nothing else.
- **`@uuo`** — a routine that *talks to the host* (terminal, files, clock). Its body receives
  a `Monitor` facade (`mon`) as its first argument, then the marshalled arguments.
  (forterp is an interpreter, not an emulator, so there is no literal UUO trap — a "system
  call" is just a `CALL` to a host subroutine — but the *services* such a routine needs are
  real, so `@uuo` provides them.)

```python
from forterp.hostlib import fcall, uuo, INT

@fcall("IDIST", args=(INT, INT))         # a computation
def idist(a, b):
    return max(abs(a // 100 - b // 100), abs(a % 100 - b % 100))

@uuo("DECPRT", args=(INT,))              # talks to the terminal
def decprt(mon, n):
    mon.tty.write(str(n))
```

Both are dispatched identically whether called as a function (the return value is the result)
or via `CALL` (return ignored) — a routine that is both a function *and* writes its arguments
just `return`s and writes its `OUT` handles; there is no separate "subroutine" decorator. Both
take `alias=` (extra names for the same routine — a str or list) and `origin=` (free-form
provenance, e.g. the source-file name), surfaced by `builtins_in`.

### Argument modes

Declare `args=(MODE, …)`, one mode per parameter; each actual is bound per its mode before the
body runs. A missing trailing actual binds `None`.

| Mode | The body receives |
|------|-------------------|
| `IN` | the raw evaluated value (int word, float, or packed string — whatever `eval` returns) |
| `INT` / `FLOAT` | the value coerced to a Python `int` / `float` |
| `STR` | a Python `str` — a quoted literal's text verbatim, or a packed word decoded through the target's char codec |
| `OUT` | an `OutRef` write handle (`.set(v)`) |
| `INOUT` | an `OutRef` — read `.get()`, then `.set(v)` |
| `ARRAY` | an `OutRef` over a whole array (`.get_at(i)` / `.set_at(i, v)` / `.loc(i)`) |

`OutRef` deliberately hides the engine's private reference objects behind `get`/`set` (plus
`get_at`/`set_at`/`loc`, and `store`/`base` for the rare block op), so host code never touches
`CellRef`/`ArrayView`/`TempRef` directly.

```python
from forterp.hostlib import fcall, ARRAY, INT, IN

@fcall("SET", args=(ARRAY, INT, IN))     # fill the first DIM elements with VAL
def set_(arr, dim, val):
    for i in range(dim):
        arr.set_at(i, val)
```

### The raw escape hatch

A routine that genuinely needs the AST nodes and engine internals — block moves, by-name
`COMMON` access, variadics — declares `raw=True`, and the body is the unwrapped uniform
callable: `(eng, frame, arg_nodes)` for `@fcall`, and `(mon, eng, frame, arg_nodes)` for
`@uuo`. The escape hatch lives in the *same* registry, so a host never forks into a second
low-level convention for its messy 30%. The toolkit a raw body uses:

| Call | What |
|------|------|
| `eng.eval(node, frame)` | evaluate an argument node to its value |
| `eng.arg_ref(node, frame)` | a write handle (`CellRef`/`ArrayView`) for a by-reference actual: `.read()` / `.write(v)`, and `.loc(i)` for an array |
| `OutRef(eng.arg_ref(node, frame))` | wrap that handle in the same `get`/`set`/`get_at`/`set_at` surface the modes hand you |
| `eng.commons["BLK"]` | a `COMMON` block as a flat mutable list of words |
| `eng.arrayview(frame, "NAME")` | a based `ArrayView` over a local/`COMMON` array by name |

```python
from forterp.hostlib import fcall

@fcall("PATH", raw=True, origin="PATH.MAC")
def path(eng, frame, nodes):
    beg = int(eng.eval(nodes[0], frame))      # scalars by value
    okview = eng.arg_ref(nodes[3], frame)     # a 5-element array, by reference
    flagref = eng.arg_ref(nodes[4], frame)    # an OUT scalar
    OK = [okview.loc(i).read() for i in range(5)]
    IARROW = eng.commons["IARROW"]            # read COMMON directly
    ...
    flagref.write(flag)
    return move
```

The design line: pure computation over the arguments → use modes (the body never sees the
engine); a routine that reaches engine state, `COMMON`, or the AST → `raw=True` (or `@uuo`,
if it only needs host *services*). Don't blur it — a non-raw body touching `.store`/`.idx` is
a smell.

### Registering them

```python
from forterp.hostlib import builtins_in
eng.register_builtins(builtins_in(my_module))   # every @fcall/@uuo + a module-level BUILTINS dict
```

`builtins_in(module)` collects every decorated routine by its name (and aliases), plus a
module-level `BUILTINS` dict merged on top. The CLI uses it to load `.py` host modules dropped
in beside FORTRAN source; any embedder can too. Or register one routine directly:
`eng.register_builtins({"IDIST": idist})`. Host routines never shadow a routine the program
defines itself.

### The monitor (`@uuo`'s `mon`)

A `@uuo` body's first argument, `mon`, is a `Monitor` — the program's view of the host
executive (the thing a UUO calls), a facade over the engine's host seam. Its services:

- `mon.tty` — the terminal: `write(s)` (column-tracking), `crlf()` (smart newline),
  `space(n)`, `tab(col)`, `getch()`, `readline()`, the carriage `width` (the free-CR-LF margin;
  `0` = no wrap), and two terminal modes — `echo` (default on; off for raw single-key input) and
  `autowrap` (default on; the "free CR-LF" switch, off for a full-screen cursor display). Under
  the DEC dialect the engine wraps output at `width` host-side, as the TOPS-10 monitor did;
  assigning a mode changes the real behavior (and also notifies the matching front-end hook).
- `mon.files` — read-only data under the engine root: `read(name, missing=…)`,
  `root_path(name)`, `save_path(name)`.
- `mon.clock` — `ms` (the engine's fixed clock reading) and a monotonic `tick()`.
- `mon.identity` — the host OS user mapped onto TOPS-10 fields: `uid`/`gid`, `user` (the login
  name), and `ppn` (the `[project,,programmer]` word, `gid,,uid`). Read-only host facts in the
  baseline — what a monitor call like `GETTAB(2,-1)` or `USRNAM` reports. The standalone helpers
  `forterp.hostlib.host_ppn()` and `host_user()` return that PPN word and login name directly
  (what `mon.identity` is built from) — handy for an `eng.gettab` mapping without building a `Monitor`.

The baseline reads only read-only host facts and the engine's own seam, so it runs anywhere the
engine does — enough for a program that needs only basic terminal I/O, files, and the clock.

#### Overriding the monitor with your own

The facade is **replaceable**: subclass `Monitor` to override a service, add a new one, or
report a different identity, and every `@uuo` routine you write receives *your* monitor instead
of the baseline. (See the next section for how this relates to the bundled `uuolib` UUOs.)

```python
import time
import forterp
from forterp.hostlib import Monitor, uuo, INT

class RealClock:                       # replaces the baseline's fixed reading
    def __init__(self):
        self._t0 = time.monotonic()
    @property
    def ms(self):
        return int((time.monotonic() - self._t0) * 1000)
    def tick(self):
        return self.ms

class OperIdentity:                    # what GETTAB(.GTPPN) / USRNAM should report
    uid, gid = 0o67, 0o1234
    user = "OPER"
    ppn = (0o1234 << 18) | 0o67        # [project,,programmer]

class GameMonitor(Monitor):
    """A richer monitor for an embedded run: a real clock, a fixed login identity, and a
    `locks` service the baseline doesn't have."""
    def __init__(self, eng, locks):
        super().__init__(eng)          # keep the baseline tty / files
        self.clock = RealClock()       # override a service: mon.clock.ms is now wall time
        self.locks = locks             # add a new one — @uuo routines can reach mon.locks

    @property                          # identity is a *property* on the base, so override it
    def identity(self):
        return OperIdentity()
```

A `@uuo` body just reaches through `mon`, so the override is invisible to the routine — this
custom monitor call uses the added `locks` service:

```python
@uuo("LOCK", args=(INT,), raw=False)
def lock(mon, channel):
    mon.locks.acquire(channel)
```

**Inject it** as a factory `fn(eng) -> Monitor`, by any entry point (all equivalent):

```python
mk = lambda eng: GameMonitor(eng, my_locks)

forterp.fortran10.run_source(src, monitor=mk)                    # a prebuilt interpreter
forterp.run_source(src, dialect=forterp.FORTRAN10, monitor=mk)   # the top-level helper
eng = forterp.runtime.make_engine(units, dialect=forterp.FORTRAN10, monitor=mk)
eng = forterp.fortran10.build_engine(units, monitor=mk)
```

…or set it directly on an already-built engine, any time before the first `@uuo` runs:

```python
eng = forterp.fortran10.build_engine(units)
eng.monitor = GameMonitor(eng, my_locks)
eng.run_program()
```

Under the hood a `@uuo` routine fetches the facade through `hostlib.monitor(eng)`, which
returns `eng.monitor` if you set one and otherwise builds and caches the baseline on first use —
so injecting before the run is all it takes, and nothing is built until a `@uuo` actually runs.

### Standard monitor UUOs (`forterp.uuolib`)

A FORTRAN-10 program expects certain TOPS-10 monitor calls to simply exist. `forterp.uuolib`
provides them, so a program that `CALL`s one just runs rather than bundling its own glue:

| Routine | What |
|---------|------|
| `OUTSTR(STR)` | write a string to the terminal |
| `OUTCHR(CH)` | write one character (low 7 bits) |
| `MSTIME(T)` | the job's millisecond runtime clock, returned into `T` |
| `SLEEP(SECS)` | suspend the job — a no-op under the interpreter |
| `GETTAB(TABLE,ITEM)` | read a monitor table word — recognized: `(2,-1)` `.GTPPN` → guest `[0,0]`, `(120,-1)` octal `.GTJTC` → `0` (unclassed); a table in `eng.gettab` → its value (override/add); any other raises `UnmodeledMonitorTable` (register it, or catch it at the driver) |

These are installed by `install_runtime` only under the **FORTRAN-10 dialect** (like the DEC
library `STDLIB`). They are *monitor* facilities — distinct from `forlib.STDLIB`, the
FORTRAN-10 V5 *language library* (`TIME`/`DATE`/`EXIT`/`RAN`/…).

**They read the engine seam directly, not the `Monitor` facade.** The bundled UUOs are plain
`fn(eng, frame, arg_nodes)` builtins that reach `eng.emit` / `eng.clock` / `eng.tgt` themselves
(the same way `STDLIB` does), so injecting an `eng.monitor` does *not* by itself change `OUTSTR`
or `MSTIME` — those follow the engine's [I/O callbacks](04-running-embedding.md#embedding-and-io) (`emit`, `clock`),
which is the lowest seam to override if you only want to redirect their output.

To override a bundled call itself, **register your own routine for that name** — a host routine
registered after the runtime wins over the bundled one (it never shadows a routine the *program*
defines). Your replacement can be a `@uuo`, so it routes through your injected monitor:

```python
from forterp.hostlib import uuo, STR

@uuo("OUTSTR", args=(STR,), raw=False)        # wins over uuolib's OUTSTR
def outstr(mon, s):
    mon.tty.write(s.rstrip())                  # now OUTSTR goes through your Monitor

eng = forterp.fortran10.build_engine(units, monitor=mk, builtins={"OUTSTR": outstr})
```

For `GETTAB` specifically there's a lighter hook: map the tables you care about through the
`eng.gettab` registry (`{table: value | fn(eng, item) -> value}`) instead of replacing the
routine — e.g. `eng.gettab[2] = lambda eng, item: monitor(eng).identity.ppn` to report your
injected identity's PPN for `.GTPPN`.

### Pluggable `OPEN` devices

A related seam: `eng.register_device("GAM", fn(eng, unit, specs, frame))` lets a program
`OPEN(…, DEVICE='GAM')` route to your handler; the core knows only TTY + ordinary files.

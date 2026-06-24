# Python API guide

`forterp` is usable as a library: parse and run FORTRAN from Python, inspect the result,
swap the value model or dialect, embed the engine in a host program, or instrument it. The
package root exposes a focused surface; deeper machinery lives in explicit namespaces.

## The public surface

`import forterp` gives exactly these names (everything else is in a namespace, below):

| Name | What |
|------|------|
| `run_source(text, …)` | parse + run a source string; returns the `Engine` |
| `parse_source(text, …)` | parse → `{name: ProgramUnit}` (raises `ParseError`) |
| `f66`, `fortran10` | prebuilt, ready-to-run interpreters |
| `Interpreter` | roll your own (target + dialect + runtime) |
| `F66`, `FORTRAN10`, `Dialect` | the front-end dialect axis |
| `NATIVE`, `PDP10`, `VAX`, `Target` | the machine value-model axis |
| `ParseError`, `SourceOptions` | the parse error; source-recovery options |

## Run and inspect

`run_source` returns the `Engine`, so you read results out of it after the run. By
convention, programs write results into a `COMMON` block, which the engine exposes as a flat
list of words:

```python
import forterp

src = """      PROGRAM T
      COMMON /OUT/ V(40)
      V(1) = 2 ** 10
      END
"""
eng = forterp.run_source(src, dialect=forterp.FORTRAN10)
print(eng.commons["OUT"][0])        # 1024
```

`run_source(text, program=None, dialect=F66, options=None, include_dir=".", **kwargs)`:
`program` picks the main unit (default: the first); `dialect` is `F66` (default) or
`FORTRAN10`; `include_dir` is where `INCLUDE` resolves; extra `**kwargs` pass through to the
`Engine` (see [Embedding](#embedding-and-io)).

`parse_source(text, dialect=F66, on_error=None, options=None, include_dir=".")` parses
without running and returns `{name: ProgramUnit}`. It raises `ParseError` (with every
diagnostic in the message) unless you pass `on_error(statement, message)`, which receives
each diagnostic and keeps the partial result.

## The two axes: target and dialect

They are orthogonal — any pairing is valid.

**Target** — the machine value model (integer word width + overflow, the logical-truth
convention, the character codec):

- `forterp.NATIVE` — a clean 64-bit host: 64-bit two's-complement, 8-bit ASCII, `.TRUE.`=1
  with boolean logicals. **The default**, for running standard F66 portably.
- `forterp.PDP10` — the DEC FORTRAN-10 machine: 36-bit two's-complement, 5×7-bit packed
  ASCII, `.TRUE.`=−1 with bit-wise logicals. The faithful, validated opt-in.
- `forterp.VAX` — a provisional, unvalidated 32-bit guess.
- `forterp.Target(word_bits=…, chars_per_word=…, bits_per_char=…, logical_true=…,
  bitwise_logic=…, little_endian=…, truth=…)` — build your own.

```python
forterp.run_source(src, target=forterp.PDP10)   # 36-bit arithmetic, packed ASCII
```

**Dialect** — the front-end language (`forterp.F66` strict ANSI vs `forterp.FORTRAN10` the
DEC superset). F66 genuinely *rejects* non-F66 constructs; FORTRAN10 enables octal,
tab-format, `!` comments, apostrophe strings, random-access I/O, free-form input, and the
DEC intrinsic library.

**SourceOptions** — orthogonal to the dialect; it copes with imperfect *input*, not a
language variant. `forterp.SourceOptions(recover_shifted_cols=True)` keeps statement text
that spilled past column 72 in a mechanically re-indented deck. The default is no recovery
(columns 7–72, sequence field dropped).

## Prebuilt interpreters and the `Interpreter` class

`forterp.fortran10` (`PDP10` + `FORTRAN10` + free-form input) and `forterp.f66` (`NATIVE` +
strict `F66`) are ready-to-run presets. Build your own with `Interpreter(target, dialect,
*, free_form_input=None, dec_intrinsics=None, runtime=True, source_options=None)` — the two
flags default from the dialect, so you can't construct a contradictory pairing.

Each interpreter offers a uniform surface:

```python
fp = forterp.fortran10

eng              = fp.run_source(src, program=None, **engine_kwargs)   # parse + run
units, errors    = fp.parse_text(src)                                  # parse a string
units, errors    = fp.parse_file("PROG.FOR")                           # parse a file
units, errors    = fp.parse_dir("src/", exclude={"SCRATCH"})           # parse a directory
eng              = fp.build_engine(units, runtime=True, **engine_kwargs)  # engine, ready to run
```

`parse_text`/`parse_file` return `(units, errors)` where `errors` is a list of
`(line, message)`; `parse_dir` errors are `(file, line, message)` (a directory spans files).
`build_engine` installs the DEC runtime (the library + FOROTS binary-I/O codec) unless
`runtime=False`, and never shadows a routine the program defines itself.

## Embedding and I/O

The `Engine` is the runtime. Build one with `forterp.runtime.make_engine(units,
dialect=None, **kwargs)` (it installs the runtime and applies the dialect's engine flags),
then `eng.run_program(name)`. The engine's host touchpoints are injected callbacks, so it
stays host-agnostic:

| `Engine`/`make_engine` kwarg | Role |
|------|------|
| `emit` | sink for terminal output (`TYPE`, list-directed, unit 5) — a `str -> None` callback |
| `printer` | sink for the line printer (units 3/6) |
| `readline` | source for `READ`/`ACCEPT` — returns one line (`""` at EOF) |
| `getch` | single-character input, if needed |
| `set_echo` | `bool -> None` — change the terminal echo mode (a program's `ECHOON`/`ECHOFF`); `run_source` defaults it to `runtime.default_terminal_echo` (flips termios `ECHO` on a tty, restored after) |
| `set_autowrap` | `bool -> None` — *optional* extra hook for the PDP-10 "free CR-LF" mode (`TRMOP.` `.TONFC`). Under the DEC dialect the engine already wraps terminal output at `tty_width` host-side, so this is only for a front-end that renders elsewhere (e.g. an ANSI terminal emitting `ESC[?7l`/`?7h`) |
| `target` | the value model (default `NATIVE`) |
| `root` | base directory for `INCLUDE` and `OPEN` file specs |
| `max_array_words` | cap on a single array/`COMMON` allocation (default 50M) |
| `dec_files` | read/write unformatted sequential files as real FOROTS binary (opt-in; default off — the portable JSON word-list otherwise) |
| `tty_width` | terminal carriage width for the FORTRAN-10 free-CR-LF wrap (default 80; `0` = no wrap) |
| `tty_autowrap` | whether terminal output wraps at `tty_width` (default on; a program toggles it via `TRMOP.` `.TONFC`) |

```python
out = []
units = forterp.parse_source(src, dialect=forterp.FORTRAN10)
eng = forterp.runtime.make_engine(units, dialect=forterp.FORTRAN10, printer=out.append)
eng.run_program()                # or run_program("MAIN")
print("".join(out))
```

Reading results back is just inspecting engine state: `eng.commons["BLK"]` (a flat word
list) is the usual channel for using FORTRAN as a compute kernel.

## Expert namespaces

The root stays focused; the rest is organized into namespaces (`import forterp` makes them
available as `forterp.<namespace>`):

| Namespace | Holds |
|-----------|-------|
| `forterp.runtime` | `Engine`, `Frame`, `make_engine`, `install_runtime`, `engine_kwargs`, `STDLIB` |
| `forterp.frontend` | the parse stages: `scan_file`, `expand_includes`, `parse_units`, `parse_expression`, `tokenize`, `Token`, `LexError` |
| `forterp.format` | the FORMAT engine: `parse_format`, `render`, `read_values`, `apply_carriage`, `InputConversionError` |
| `forterp.ast` | the AST node classes the parser produces |
| `forterp.hostlib` | declarative authoring of host builtins (below) |
| `forterp.debug` | the OOB-access census (below) and the interactive tracer/profiler |

## Custom host routines (builtins)

A host can add its own routines that FORTRAN `CALL`s or references — the
geometry/bit-packing/pathfinding helpers and the "system calls" (terminal I/O, file reads,
the clock) that programs of this era kept in hand-written assembly. `forterp.hostlib` is the
authoring layer: declare each parameter's *mode* and write a clean Python body; the argument
marshalling is generated. (For *how* it is generated, see the [design notes](DESIGN.md).)

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
  baseline — what a monitor call like `GETTAB(2,-1)` or `USRNAM` reports.

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
or `MSTIME` — those follow the engine's [I/O callbacks](#embedding-and-io) (`emit`, `clock`),
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

## Instrumentation: the OOB census

The engine reproduces the unchecked PDP-10 faithfully — an out-of-bounds read yields `0`, an
OOB write is dropped (the 1978 overrun behavior). `forterp.debug` lets you *observe* that
without changing it:

```python
import forterp, forterp.debug

with forterp.debug.oob_census() as census:        # mode "log" by default
    forterp.fortran10.run_source(src)
print(census.reads, census.writes)                # counts during the block
for site in census.sites:                          # per-site records (mode "log")
    print(site["op"], site["routine"], site["array"], site["idx"], site["len"])
```

The context manager restores the prior mode on exit (even on exception). For finer control
there is a standalone surface: `set_oob_mode("off"|"log"|"raise")` / `oob_mode()`,
`oob_counts()` → `(reads, writes)`, and `oob_log()` / `clear_oob_log()`. In `"raise"` mode
an overrun raises `forterp.debug.OobError` — turning the faithful overrun into a hard error
for a checker or fuzzer.

## Errors

| Exception | Raised when |
|-----------|-------------|
| `forterp.ParseError` | malformed source (front-end); message carries every diagnostic |
| `forterp.format.InputConversionError` | a bad numeric field on formatted/list-directed/NAMELIST input |
| `forterp.debug.OobError` | an out-of-bounds access while the census mode is `"raise"` |

A runtime fault inside a FORTRAN program surfaces as an ordinary Python exception
(`RuntimeError`, `ValueError`, …) out of `run_source`/`run_program`; an explicit `STOP`
raises `forterp.runtime.StopExecution`, which `run_program` swallows as normal termination.

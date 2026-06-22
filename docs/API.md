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
| `target` | the value model (default `NATIVE`) |
| `root` | base directory for `INCLUDE` and `OPEN` file specs |
| `max_array_words` | cap on a single array/`COMMON` allocation (default 50M) |

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

A host can add its own intrinsics/subprograms. The low-level contract is a callable
`fn(eng, frame, arg_nodes)` registered with `eng.register_builtins({...})`. `forterp.hostlib`
generates the argument marshalling so the body is clean Python — declare each parameter's
*mode*:

```python
from forterp.hostlib import builtin, INT, OUT, ARRAY

@builtin("IDIST", args=(INT, INT))      # two integer-word inputs
def idist(a, b):
    return abs(a - b)                    # return value used as the function result

eng.register_builtins({"IDIST": idist})
```

Modes: `IN` (raw value), `INT`, `FLOAT` (typed inputs), `OUT`/`INOUT` (write-back via a
reference), `ARRAY` (a based array view). A builtin is dispatched identically whether called
as a function (its return value is used) or via `CALL` (ignored).

Pluggable `OPEN` devices use the same idea: `eng.register_device("GAM",
fn(eng, unit, specs, frame))` lets a program `OPEN(…, DEVICE='GAM')` route to your handler;
the core knows only TTY + files.

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

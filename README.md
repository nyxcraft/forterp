# forterp

[![Tests](https://github.com/nyxcraft/forterp/actions/workflows/tests.yml/badge.svg)](https://github.com/nyxcraft/forterp/actions/workflows/tests.yml)
[![PyPI](https://img.shields.io/pypi/v/forterp.svg)](https://pypi.org/project/forterp/)
[![Python versions](https://img.shields.io/pypi/pyversions/forterp.svg)](https://pypi.org/project/forterp/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

A **configurable FORTRAN-66 interpreter** in Python: the machine value model and the
front-end dialect are both pluggable, so one core runs FORTRAN against whatever
representation you select.

The value model is a `Target` — integer word width and overflow, the logical-truth
convention, and how characters pack into words. Two ship:

- **`NATIVE` (the default)** — a clean 64-bit host machine for running standard
  FORTRAN-66 portably: 64-bit two's-complement integers, 8-bit ASCII, `.TRUE.`=1 with
  boolean logical operators. `import forterp; forterp.run_source(...)` uses this.
- **`PDP10`** — the DEC FORTRAN-10 model: 36-bit two's-complement words,
  5×7-bit packed character storage, `.TRUE.`=−1 with bit-wise logicals. Select with
  `Engine(..., target=forterp.PDP10)`.

The PDP-10 target was extracted from an interpreter built to run real 1970s DEC FORTRAN
unmodified, so it is exercised against real period code — not just toy snippets — and
validated against the DEC FORTRAN-10 V5 manual and the **FCVS** conformance corpus.

## Install

```sh
pip install forterp          # (once published)
# or, from a checkout:
pip install -e .
```

## Quick start

```python
import forterp

# The default dialect is strict ANSI F66; FORTRAN10 enables the DEC niceties
# (here the quoted-string FORMAT -- F66 itself uses Hollerith nH). Note fixed form:
# the statement label sits in columns 1-5 and the body starts in column 7.
eng = forterp.run_source('''      PROGRAM HELLO
      WRITE(6,10)
   10 FORMAT(' HELLO, WORLD')
      END
''', dialect=forterp.FORTRAN10, printer=print)
```

Lower-level building blocks (the expert surface lives under `forterp.runtime`):

```python
units = forterp.parse_source(src)              # {name: ProgramUnit}
eng   = forterp.runtime.make_engine(units)     # Engine with the FORTRAN-10 runtime installed
eng.run_program("MAIN")                         # or run_program() for the first unit
```

The package root exposes only the focused names above; the rest is organized into
namespaces: `forterp.runtime` (the `Engine` and builders), `forterp.frontend` (lexer/parser
stages), `forterp.format` (the FORMAT engine), `forterp.ast` (AST nodes), `forterp.hostlib`
(host-builtin marshalling), and `forterp.debug` (the interactive tracer/profiler and the
out-of-bounds census — `forterp.debug.oob_census()` counts or logs the faithful unchecked-array
accesses without changing them).

## Command line

Installing puts three commands on your PATH — thin dialect front-ends over the engine
(like `g77`/`gfortran` over gcc):

```sh
pyf66 prog.for              # run as strict ANSI FORTRAN-66 (rejects DEC extensions)
pyfortran10 prog.for        # run as DEC FORTRAN-10 (the superset: octal, IMPLICIT, '...', …)
forterp --std fortran10 prog.for   # general driver; --std f66|fortran10 (default: f66)
```

`--target native|pdp10|vax` selects the value model and `--program NAME` picks the main
unit. `--check` parses and lists every diagnostic without running (a compile-check) — so
`pyf66 --check prog.for` is a strict-ANSI-F66 conformance linter. `--version` prints the
version, `--help` the usage. Before install, use `python -m forterp …`.

Pass several source files and they are linked together by unit name, the way a compiler
links `f77 main.f lib.f` — so a driver and a separately-held library run as one program:

```sh
forterp main.for lib.for           # main.for's PROGRAM calls SUBROUTINEs in lib.for
```

Launched with **no file**, each command drops into an interactive monitor (a small,
FORTRAN-focused descendant of the TOPS-10 `.` prompt — it operates on whole source
files, not a statement REPL, since F66 has no incremental-execution model):

```text
f66> RUN prog.for            # compile + run (alias EXECUTE); CHECK = parse-only
f66> SET STD fortran10       # switch dialect, target, or main unit between runs
f10> LOAD prog.for           # parse into the session; START runs it
f10> SHOW /BLOCK/            # inspect a COMMON block after a run; SHOW = settings
f10> !cmd   @file   HELP   EXIT
```

The command set is identical across the three commands; only the starting dialect
differs (`pyf66` → f66, `pyfortran10` → fortran10), and `SET STD` flips it.

`IMMEDIATE` (alias `REPL`) drops into interactive FORTRAN — statements run as you type,
a DO loop is collected across lines, and a bare expression is evaluated (so typing a
name inspects it). After a `LOAD`, the REPL can call straight into the program:

```text
f66* NFAC = 1
f66* DO 10 I=1,5
cont> NFAC = NFAC * I
cont> 10 CONTINUE
f66* NFAC                    # -> 120
f66* ISQ(9)                  # call a function from the LOADed program -> 81
f66* 2 + 3 * 4               # calculator -> 14
```

(`COMMON`/`EQUIVALENCE` need a full program unit — put those in a file and `LOAD` it;
F66 has no incremental model for control flow, so the unit of work is a statement or a
DO block, never a bare `GOTO`.)

The monitor also debugs and profiles a `RUN`/`START`. `BREAK <line>` + `STEP` drop into
a `(dbg)` prompt where you step (`step`/`next`/`cont`), backtrace (`where`), and inspect
any expression by typing it; `TRACE` echoes each statement; `PROFILE`/`COVERAGE` report
per-line execution counts and which lines were reached. The profiler counts *statements*
(deterministic), not wall-clock seconds. All of it rides one off-by-default hook, so a
plain run pays nothing:

```text
f66> BREAK 6
f66> RUN fac.for
-- stopped at FAC:6 (Assign)
(dbg) NF                     # inspect a variable by name -> 1
(dbg) where                  # backtrace -> #0 FAC:6
(dbg) cont
f66> PROFILE                 #    5  FAC:6   (the loop body ran 5 times)
```

## What's pluggable

- **Machine target** — `forterp.Target(word_bits, chars_per_word, logical_true, bitwise_logic,
  bits_per_char, little_endian, truth)` fixes the value model. `forterp.NATIVE` (64-bit, 8-bit
  ASCII, boolean logicals) is the default; `forterp.PDP10` (36-bit, 5×7-bit packed, `.TRUE.`=−1,
  bit-wise logicals) is the DEC target; `forterp.VAX` (32-bit, little-endian, low-bit
  logical) is a *provisional, unvalidated* guess. Pass `Engine(..., target=...)`.
- **Front-end dialect** — `forterp.FORTRAN10` (DEC extensions on) vs `forterp.F66`
  (ANSI). Threaded through the source reader and lexer.
- **OPEN devices** — `eng.register_device(name, handler)` plugs in special devices.
- **Unformatted I/O codec** — `forterp.runtime.install_runtime(eng)` wires the FOROTS binary-record +
  DEC-10 float codec used by binary `READ`/`WRITE`.

## Supported language

Standard FORTRAN-66 (arithmetic/logical/relational expressions, the full control-flow
set, `DO` loops with F66 one-trip semantics, `COMMON`/`EQUIVALENCE` storage association,
`DATA`, subprograms + `ENTRY`, statement functions), formatted + list-directed +
unformatted I/O with the complete `FORMAT` edit-descriptor set, `ENCODE`/`DECODE`, and
the DEC FORTRAN-10 extensions (octal literals, Hollerith, `IAND`/`IOR`/shift intrinsics,
tab-format source, random-access `READ(u'r)`). See [`docs/`](docs/).

## Examples & demos

Two directories of runnable material:

- **[`examples/`](examples/)** — short Python scripts showing how to *use forterp as a
  library*: running source and capturing output, choosing a dialect or target, feeding
  input via `readline`, and reading results back out of `COMMON`. Start with
  [`examples/run_and_capture.py`](examples/run_and_capture.py).
- **[`demos/`](demos/)** — genuine 1970s FORTRAN to *run through* the interpreter:
  verbatim netlib numerical libraries (EISPACK, LINPACK, FFT, RKF45) each with a small
  driver, DECsystem-10 sources recovered from DECUS tapes, and a 1971 Game of Life. Every
  one is real period source, run as-is — the corpus that flushes out interpreter gaps.

## Tests & lint

```sh
pip install -e ".[dev]"
pytest
ruff check           # lint (config in pyproject.toml)
ruff format --check  # formatting — run `ruff format` to apply
```

The suite is the interpreter's unit tests plus the **FCVS** (FORTRAN Compiler Validation
System) conformance corpus — the standard-conformance audits — exercised through the
real source-reader → lexer → parser → engine pipeline.

## Security & trust model

forterp is an **interpreter, not a sandbox**. A program it runs executes with the full
privileges of the invoking process: FORTRAN `OPEN`/`READ`/`WRITE` reach the real
filesystem, and an absolute path or one containing `..` reads or writes files *outside*
the `save_root` base directory. There is no network access, Python `eval`, or subprocess
reachable from a FORTRAN program — but file access alone means **you should not run
untrusted source expecting containment.** To run code you don't trust, confine the process
at the OS level (an unprivileged user, a container, a read-only filesystem, seccomp).

Two guards keep an accidental or hostile program from taking down the host, each raising a
clean error rather than hanging or OOM-ing: a statement budget (`eng.max_steps`, default
50M) bounds execution, and `max_array_words` (default 50M, settable on the `Engine` /
`make_engine`) bounds array/`COMMON` allocation — including DATA repetition counts and
EQUIVALENCE extension, not just a bare `DIMENSION`. `INCLUDE` resolves only within its base
directory (the CLI uses the source file's own directory; the library default is the current
directory), and its `'FILE/SWITCH'` target is split on `/`, so it cannot escape via an
absolute or `..` path. These bound resource use; they are not a security sandbox — file
access via `OPEN` is unrestricted, so still confine genuinely untrusted source at the OS
level.

The interactive monitor additionally offers a `!` shell escape and `@file` command scripts
(not reachable from a running FORTRAN program); these run with your shell's privileges, so
treat a command script as trusted input and don't wire the monitor to an untrusted source.

## License

MIT © Nicholas J. Kisseberth. See [LICENSE](LICENSE).

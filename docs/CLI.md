# Command-line tools

Installing `forterp` puts three commands on your `PATH`. They are thin dialect front-ends
over one engine — like `g77`/`gfortran` over gcc:

| Command | Dialect | Use |
|---------|---------|-----|
| `forterp` | `--std` selects (default `f66`) | the general driver |
| `pyf66` | strict ANSI FORTRAN-66 | rejects DEC extensions |
| `pyfortran10` | DEC FORTRAN-10 (the superset) | octal, `IMPLICIT`, `'…'`, random-access I/O, … |

Before installing, the same commands are available as `python -m forterp …`.

## Running a program

```sh
pyfortran10 prog.for          # run prog.for's main PROGRAM
forterp --std fortran10 prog.for
```

The program's terminal output (`TYPE`, list-directed `PRINT *`, unit 5) and its
line-printer output (units 3/6) go to **stdout**; `READ`/`ACCEPT` read from **stdin**. A
normal end or `STOP` exits 0.

Instead of a file you can pass the program inline with `-c` or read it from **stdin** with `-`:

```sh
pyfortran10 -c '      PRINT *, 2+2'$'\n''      END'   # program as a string
cat prog.for | forterp --std fortran10 -              # program from stdin
```

A `#!` shebang works with `-x` (which skips the source's first line), so a `.for` file can be
made executable: `#!/usr/bin/env -S pyfortran10 -x`.

### Linking several files

Pass multiple source files and they are linked by unit name, the way a compiler links
`f77 main.f lib.f` — a driver and a separately-held library run as one program:

```sh
forterp main.for lib.for      # main.for's PROGRAM calls SUBROUTINEs defined in lib.for
```

`INCLUDE` targets resolve against the first source file's directory.

## Options

| Option | Meaning |
|--------|---------|
| `--std f66\|fortran10` | language dialect (**`forterp` only**; default `f66`). `pyf66`/`pyfortran10` are pinned. |
| `--target native\|pdp10\|vax` | machine value model (default `native`). `pdp10` = the faithful 36-bit DEC machine; `vax` is provisional. |
| `--program NAME` | which `PROGRAM`/`SUBROUTINE` unit to run as the main (default: the first). |
| `--check` | parse and list every diagnostic **without running** — a compile-check. `pyf66 --check prog.for` is a strict-ANSI-F66 conformance linter. |
| `--recover-shifted-cols` | recover statement text reindented past column 72 (off by default — a faithful FORTRAN-10 compiler drops cols 73+); for a deck nudged a column or two right. |
| `--no-wrap` | disable the FORTRAN-10 terminal free-CR-LF wrap at column 80 (TOPS-10 `.TONFC`); no effect under strict F66, which never wraps. |
| `-c CMD` | run the FORTRAN program passed as a string (instead of a file). |
| `-` (as a file) | read the program from **stdin**. |
| `-x` | skip the source's first line (e.g. a `#!` shebang), so a `.for` file can be a runnable script. |
| `-i` | after running, drop into the interactive command processor — inspect `SHOW /BLOCK/`, `IMMEDIATE`, continue (cf. `python -i`). |
| `-q`, `--quiet` | suppress the interactive startup banner. |
| `-u` | force unbuffered stdout/stderr. |
| `--version`, `-V` | print `<prog> <version>` and exit; `-VV` adds the dialect/target/host build line. |
| `--help`, `-h`, `-?` | usage and exit. |

## Exit codes

| Code | When |
|------|------|
| `0` | ran to completion, or an explicit `STOP`; `--check` with no diagnostics |
| `1` | a parse error, a bad numeric field / unrepresentable binary float, a runtime fault (undefined unit/label, step-budget exceeded, oversized allocation, deep recursion, a file error), or `--check` with diagnostics |
| `2` | a usage error (unreadable file, `--check` with no file, a bad option) |

Runtime faults are reported as a single `?…` line on stderr — never a Python traceback.

## Interactive command processor

Launched with **no file**, each command drops into an interactive command processor — a small,
FORTRAN-focused descendant of the TOPS-10 `.` prompt. It works on whole source files (F66
has no incremental-execution model), except for `IMMEDIATE` mode. The command set is the
same for all three commands; only the starting dialect differs, and `SET STD` flips it.

```text
f66> RUN prog.for             # compile + run a file        (alias EXECUTE)
f66> CHECK prog.for           # parse + list diagnostics, no run  (alias COMPILE)
f66> LOAD prog.for            # parse a file into the session
f10> START                    # run the loaded program; RESET drops it
f10> SET STD fortran10        # switch dialect / TARGET / PROGRAM between runs
f10> SET TARGET pdp10
f10> SHOW /OUT/               # inspect a COMMON block after a run; SHOW = settings
f10> !ls                      # run a host shell command
f10> @script.mon              # run commands from a file
f10> HELP                     # the command list
f10> EXIT                     # quit                          (alias QUIT)
```

### Debugging

The command processor carries a per-statement debugger/profiler (off by default — a plain `RUN`
pays nothing):

```text
f66> BREAK 7                  # breakpoint at line 7 (no arg = list); UNBREAK to remove
f66> STEP                     # the next RUN stops at the first statement
f66> RUN prog.for             # at a (dbg) prompt: step / next / cont, where, p <expr>
f66> TRACE on                 # echo each statement as it runs
f66> PROFILE on               # per-line execution counts; PROFILE (no arg) shows the report
f66> COVERAGE                 # which lines the last run reached
```

At the `(dbg)` prompt, typing a name inspects it (the engine's own evaluator); a bare
command word wins over a same-named variable, so use `p <expr>` / `=<expr>` to force
inspection.

### `IMMEDIATE` (a REPL)

```text
f66> IMMEDIATE                # alias REPL — interactive FORTRAN
*> I = 6 * 7                  # statements run as you type
*> TYPE *, I                  # 42
*> 2 + 3 * 4                  # a bare expression is evaluated and printed -> 14
```

A `DO` loop is collected across lines and run as a block; declarations accumulate in a
persistent session. `COMMON`/`EQUIVALENCE`/`NAMELIST` are out of scope for immediate mode —
put them in a file and `LOAD` it.

> The command processor's `!` shell escape and `@file` scripts run with your shell's privileges and
> are **not** reachable from a running FORTRAN program. Treat a command script as trusted
> input; don't wire the command processor to an untrusted source.

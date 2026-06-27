# Command-line tools

Installing `forterp` puts three commands on your `PATH`. They are thin dialect front-ends
over one engine — like `g77`/`gfortran` over gcc:

| Command | Dialect | Use |
|---------|---------|-----|
| `forterp` | `--std` selects (default `f66`) | the general driver |
| `pyf66` | strict ANSI FORTRAN-66 | rejects DEC extensions |
| `pyf77` | ANSI FORTRAN 77 | `CHARACTER`, block `IF`, list-directed I/O, `OPEN`/`CLOSE`/`INQUIRE` |
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
| `--std f66\|f77\|fortran10` | language dialect (**`forterp` only**; default `f66`). `pyf66`/`pyf77`/`pyfortran10` are pinned. |
| `--target native\|pdp10\|lp64le\|vax` | machine value model (default `native`). `pdp10` = the faithful 36-bit DEC machine; `lp64le` = a 64-bit little-endian IEEE machine (matches gfortran on x86_64 — useful with `--word-memory`); `vax` is provisional. |
| `--program NAME` | which `PROGRAM`/`SUBROUTINE` unit to run as the main (default: the first). |
| `--check` | parse and list every diagnostic **without running** — a compile-check. `pyf66 --check prog.for` is a strict-ANSI-F66 conformance linter. |
| `--recover-shifted-cols` | recover statement text reindented past column 72 (off by default — a faithful FORTRAN-10 compiler drops cols 73+); for a deck nudged a column or two right. |
| `--no-wrap` | disable the FORTRAN-10 terminal free-CR-LF wrap at column 80 (TOPS-10 `.TONFC`); no effect under strict F66, which never wraps. |
| `--word-memory` | store `COMMON`/`EQUIVALENCE` in word-addressable memory so cross-type punning is bit-faithful (a `REAL` read as `INTEGER` yields the genuine machine word). Needs a target with a memory model — `pdp10` (KL10 words, validated vs a real KL10), `lp64le` (IEEE bytes, matches gfortran), or `vax` (LE ints + middle-endian F/D floats, **best-effort/unvalidated**); off by default (typed cells). Costs ~2× on `COMMON` access — see the [FORTRAN 66 manual, Appendix C](../fortran66/C-forterp-extensions.md). |
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

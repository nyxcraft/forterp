# The forterp manual

`forterp` is a FORTRAN-66 / DEC FORTRAN-10 interpreter written in pure Python. This manual is the
guide to **the interpreter itself** — how to run it, drive it from Python, extend it, and how it
works inside. For the **languages** it implements, see the two reference manuals:

- the [FORTRAN 77 reference manual](../fortran77/README.md) — forterp's default dialect (X3.9-1978);
- the [FORTRAN 66 reference manual](../fortran66/README.md) — the strict `F66` dialect (X3.9-1966
  plus the DEC FORTRAN-10 extensions).

## The two axes

Everything in forterp is pluggable along two orthogonal axes — pick any pairing:

- the **dialect** (the front-end language): `F77` (the default, X3.9-1978), `F66` (strict ANSI
  X3.9-1966), `FORTRAN10` (the DEC superset);
- the **target** (the machine value model): `NATIVE` (a portable 64-bit host, the default), `PDP10`
  (faithful 36-bit DEC-10), `LP64LE` (64-bit little-endian IEEE, gfortran-aligned), `VAX`
  (provisional).

See [Targets & dialects](05-targets-dialects.md) for the axes in depth, including faithful
cross-type **type punning** (`word_memory`).

## Contents

**Guide**

1. [Getting started](01-getting-started.md) — what forterp is, the public surface, a quick run
2. [Command-line tools](02-cli.md) — running programs, linking files, options, exit codes
3. [The interactive processor](03-interactive.md) — `RUN`/`LOAD`, the debugger/profiler, `IMMEDIATE`

**The Python API**

4. [Running & embedding](04-running-embedding.md) — `run_source`/`parse_source`, the prebuilt
   interpreters and the `Interpreter` class, the I/O hooks
5. [Targets & dialects](05-targets-dialects.md) — the two axes, the F77 knobs, faithful type punning
6. [Host routines](06-host-routines.md) — custom builtins, the `@fcall`/`@uuo` decorators, the
   `Monitor` facade, the standard UUOs, pluggable `OPEN` devices
7. [Instrumentation & errors](07-instrumentation-errors.md) — the OOB census, the error types

**Internals**

8. [Architecture](08-architecture.md) — the one decision everything follows from; the pipeline
9. [The memory model](09-memory-model.md) — COMMON/EQUIVALENCE, static locals, the word-addressable
   punning model
10. [Control flow & I/O](10-control-io.md) — the control model; I/O and FORMAT
11. [Seams & intrinsics](11-seams-intrinsics.md) — the four seams; intrinsics vs library builtins;
    host-routine marshalling
12. [Internals reference](12-internals-reference.md) — the module map; engine runtime state
13. [Testing](13-testing.md) — the conformance suites (FCVS) and the harness
14. [Maintainer recipes](14-maintaining.md) — how to change things

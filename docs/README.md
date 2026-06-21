# forterp documentation

- **[FORTRAN66.md](FORTRAN66.md)** — a language reference for the
  FORTRAN dialect `forterp` implements (standard FORTRAN-66 plus the DEC FORTRAN-10
  extensions), written for users of this interpreter.
- **[DESIGN.md](DESIGN.md)** — the interpreter's architecture: the pipeline (source →
  lexer → parser → engine), the machine value model, memory/control models, and the four
  seams that make it standalone. For someone modifying forterp.
- **[CHANGELOG.md](../CHANGELOG.md)** — dated history of the standalone interpreter.

Runnable material lives outside `docs/`:

- **[`examples/`](../examples/)** — short Python scripts showing how to drive forterp as a
  library (run source, capture output, pick a dialect/target, read results from `COMMON`).
- **[`demos/`](../demos/)** — genuine 1970s FORTRAN to run through the interpreter:
  verbatim netlib libraries with drivers, DECsystem-10 tape sources, and a 1971 Game of Life.

These docs are also published as a site via GitHub Pages — the build machinery lives in
`gh-pages/` (a small `markdown-it-py` static-site generator) and is deployed by
`.github/workflows/pages.yml`; no built output is committed.

## Authoritative standards

`forterp` targets two specifications. The reference above summarizes them as implemented;
the primary sources are:

- **ANSI X3.9-1966, "FORTRAN"** — the FORTRAN 66 standard (the first standardized
  FORTRAN). This is the base language. The standard is archived by the ISO/IEC JTC1/SC22/WG5 Fortran committee.
- **DECsystem-10 FORTRAN-10 Language Manual (V5)** — the DEC dialect `forterp` actually
  reproduces (the 36-bit word model, SIXBIT/A5 packing, octal/Hollerith literals,
  `IAND`/`IOR`/shift intrinsics, FOROTS binary I/O, tab-format source). This is the
  document the interpreter was validated against.

## Conformance

The interpreter is exercised against the **FCVS** (FORTRAN Compiler Validation System)
audit corpus — see `tests/fcvs/` — which checks conformance to the FORTRAN-66 standard.
Run `pytest` to execute it.

## Security & trust model

forterp is an **interpreter, not a sandbox**: a program runs with the invoking process's
privileges and its `OPEN`/`READ`/`WRITE` reach the real filesystem (absolute or `..` paths
escape `save_root`). There is no network, `eval`, or subprocess reachable from FORTRAN, and
execution and allocation are bounded (`eng.max_steps`, `eng.max_array_words`) — but do not
run untrusted source expecting containment; confine it at the OS level instead. See the
**Security & trust model** section of the top-level [README](../README.md#security--trust-model).

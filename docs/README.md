# forterp documentation

- **[DESIGN.md](DESIGN.md)** — the interpreter's architecture: the pipeline (source →
  lexer → parser → engine), the machine value model, memory/control models, and the four
  seams that make it standalone. For someone modifying forterp.
- **[CLI.md](CLI.md)** — the command-line tools (`forterp` / `pyf66` / `pyfortran10`):
  options, exit codes, multi-file linking, and the interactive command processor.
- **[API.md](API.md)** — the programmer's reference for the `forterp.*` Python API:
  running and parsing, the prebuilt interpreters, the target/dialect axes, embedding the
  engine, the expert namespaces, custom host builtins, and the OOB census.
- **[FORTRAN66.md](FORTRAN66.md)** — a language reference for the base
  dialect `forterp` implements (standard FORTRAN-66 plus the DEC FORTRAN-10 extensions),
  written for users of this interpreter.
- **[FORTRAN 77 reference manual](fortran77/README.md)** — the complete FORTRAN 77 language
  (ANSI X3.9-1978), example-driven and organized on the standard: data types, arrays,
  expressions, control flow, I/O and `FORMAT`, procedures, and the intrinsic library, with a
  *forterp notes* box per chapter. This is the `forterp.F77` dialect (`--std f77`); see
  [API.md](API.md#the-two-axes-target-and-dialect) to select it and for the dialect knobs.
- **[CHANGELOG.md](../CHANGELOG.md)** — dated history of the standalone interpreter.

Runnable material lives outside `docs/`:

- **[`examples/`](../examples/)** — short Python scripts showing how to drive forterp as a
  library (run source, capture output, pick a dialect/target, read results from `COMMON`).
- **[`demos/`](../demos/)** — genuine 1970s FORTRAN to run through the interpreter:
  verbatim netlib libraries with drivers, DECsystem-10 tape sources, and a 1971 Game of Life.

These docs are also published as a site via GitHub Pages — the build machinery lives in
`gh-pages/` (a small `markdown-it-py` static-site generator); the built site is committed
under `gh-pages/public/` (kept in sync by the `.githooks` pre-commit hook) and deployed by
`.github/workflows/pages.yml`.

## Authoritative standards

`forterp` targets three specifications. The references above summarize them as implemented;
the primary sources are:

- **ANSI X3.9-1966, "FORTRAN"** — the FORTRAN 66 standard (the first standardized
  FORTRAN). This is the base language. The standard is archived by the ISO/IEC
  JTC1/SC22/WG5 Fortran committee (<https://wg5-fortran.org/ARCHIVE/Fortran66.pdf>).
- **ANSI X3.9-1978, "FORTRAN"** — the FORTRAN 77 standard, layered on the F66 base by the
  `F77` dialect (the `CHARACTER` type, the block `IF`, list-directed I/O, `INQUIRE`).
- **DECsystem-10 FORTRAN-10 Language Manual (V5)** — the DEC dialect `forterp` actually
  reproduces (the 36-bit word model, SIXBIT/A5 packing, octal/Hollerith literals,
  `IAND`/`IOR`/shift intrinsics, FOROTS binary I/O, tab-format source). This is the
  document the interpreter was validated against.

## Conformance

The interpreter is exercised against the **FCVS** (FORTRAN Compiler Validation System) audit
corpus — one set of 192 routines in `tests/fcvs/`, pristine from the public-domain NIST suite,
with their canonical `.DAT` input decks. FORTRAN-66 is checked against the F66-valid subset, and
FORTRAN-77 against the whole corpus. All 192 parse, run every declared sub-test, and self-check
with zero failures. gfortran golden outputs under `tests/fcvs_golden/` independently validate the
print-only routines (no gfortran needed at test time): with the canonical decks gfortran runs the
whole corpus and forterp byte-matches 191 of 192 — the lone exception (FM111) is a documented
gfortran outlier where forterp matches the routine's own CORRECT line. Run `pytest` to execute
them; see [DESIGN.md §9 (Testing)](DESIGN.md#9-testing) for the full breakdown.

## Security & trust model

forterp is an **interpreter, not a sandbox**: a program runs with the invoking process's
privileges and its `OPEN`/`READ`/`WRITE` reach the real filesystem (absolute or `..` paths
escape `save_root`). There is no network, `eval`, or subprocess reachable from FORTRAN, and
execution and allocation are bounded (`eng.max_steps`, `eng.max_array_words`) — but do not
run untrusted source expecting containment; confine it at the OS level instead. See the
**Security & trust model** section of the top-level [README](../README.md#security--trust-model).

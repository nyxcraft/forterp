# forterp documentation

- **[The forterp manual](forterp/README.md)** — the guide to the interpreter itself, as a
  chaptered manual: running it ([command-line tools](forterp/02-cli.md), the
  [interactive processor](forterp/03-interactive.md)), driving it from Python
  ([running & embedding](forterp/04-running-embedding.md), the
  [target/dialect axes](forterp/05-targets-dialects.md), [host routines](forterp/06-host-routines.md)),
  and how it works inside ([architecture](forterp/08-architecture.md), the
  [memory model](forterp/09-memory-model.md) and type punning, [seams](forterp/11-seams-intrinsics.md),
  [testing](forterp/13-testing.md)).
- **[FORTRAN 66 reference manual](fortran66/README.md)** — the complete FORTRAN 66 language
  (USA Standard X3.9-1966) plus the DEC FORTRAN-10 extensions, example-driven and organized on
  the standard: program form, data types, expressions, statements, procedures, and the intrinsic
  library, with a *forterp notes* box per chapter. This is the strict `forterp.F66` dialect (`--std f66`), the base language.
- **[FORTRAN 77 reference manual](fortran77/README.md)** — the complete FORTRAN 77 language
  (ANSI X3.9-1978), example-driven and organized on the standard: data types, arrays,
  expressions, control flow, I/O and `FORMAT`, procedures, and the intrinsic library, with a
  *forterp notes* box per chapter. This is forterp's **default** dialect (`forterp.F77`); see
  [the forterp manual](forterp/05-targets-dialects.md#the-two-axes-target-and-dialect) to select it and for the dialect knobs.
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
them; see [the forterp manual §13 (Testing)](forterp/13-testing.md) for the full breakdown.

## Security & trust model

forterp is an **interpreter, not a sandbox**: a program runs with the invoking process's
privileges and its `OPEN`/`READ`/`WRITE` reach the real filesystem (absolute or `..` paths
escape `save_root`). There is no network, `eval`, or subprocess reachable from FORTRAN, and
execution and allocation are bounded (`eng.max_steps`, `eng.max_array_words`) — but do not
run untrusted source expecting containment; confine it at the OS level instead. See the
**Security & trust model** section of the top-level [README](../README.md#security--trust-model).

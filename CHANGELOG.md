# Changelog

## 2026-06-16 — And so it begins...

- **15:29** — Initial FORTRAN-10 / F66 interpreter: lexer, parser, AST, tree-walking engine, the FORMAT runtime, the `forlib` library, diagnostics.
- **16:07** — F66 §3.1.6 blanks-insignificance, via a tokenizer parse-retry.
- **18:49** — `RAN`/`SETRAN`, COMPLEX formatted input, NAMELIST and random-access I/O, `%FTNLID` warnings.
- **18:51** — FOROTS binary-record codec (LSCW framing + DEC-10 float), `MODE='BINARY'`.
- **23:12** — Front-end: DEC TAB-format source, the bare main program, integer-vs-`.EQ.` lexing.

## 2026-06-17 — hardening for the next program

- **22:49** — `COMMON` sizing, dummy procedures, continuation comments, lowercase `nH` Hollerith.

## 2026-06-18 — pluggable seams, then standalone

- **08:58** — A pluggable `OPEN` device registry.
- **09:23** — Extracted the machine value model behind a pluggable `Target`.
- **09:43** — Parameterized the front-end dialect (`Dialect`).
- **11:23** — A `fortran10` layer atop the `f66` core; moved FOROTS binary I/O into it.
- **13:44** — **Split out to a standalone repo** — a `src/` package with a clean public API and the FCVS corpus.
- **14:09** — Routed every wrap/pack/truthy site through `Target` (INT/LSH, the logical algebra, the char codec).
- **14:47** — Added the `NATIVE` 64-bit target and made it the default; `PDP10` the opt-in machine.
- **15:19** — A provisional, unvalidated `VAX` target.
- **15:39** — Curated the FCVS corpus to F66-only (dropped the 140 F77/`CHARACTER` routines).
- **16:25** — Adopted `ruff` lint + `ruff format`.
- **23:59** — Renamed `f66` → `forterp`; made `F66` the default dialect.

## 2026-06-19 — CLI, monitor, REPL, debugger, conformance

- **00:00** — Three console front-ends: `pyf66`, `pyfortran10`, `forterp --std`.
- **00:48** — Gated the DEC I/O surface, intrinsics, and random-access I/O under F66; added the V5 math/rotate intrinsics.
- **01:11** — `--check`: parse and list diagnostics without running.
- **10:16** — An interactive command monitor (a TOPS-10 `.`-prompt descendant).
- **10:20** — An immediate-mode REPL, then refactored onto two reusable primitives.
- **11:03** — Factored target/dialect config into shared registries + `engine_kwargs`.
- **12:31** — An off-by-default per-statement tracer hook; on it, a debugger + profiler.
- **14:24** — Formatted-input conformance; fixed the random-access write clobber; CLI error hygiene.
- **21:10** — Exposed the embedding API; added the prebuilt `fortran10` / `f66` interpreters.
- **21:47** — Gated every non-F66 feature behind a `Dialect` flag; dual-run F66 tests under both dialects.
- **22:11** — Illegal `EQUIVALENCE` shapes now raise; documented the multi-word storage boundary.
- **23:06** — list-directed/NAMELIST bad fields raise like formatted; `forbin` rejects unrepresentable floats.

## 2026-06-20 — real-machine defaults, host marshalling, docs site

- **00:00** — The `fortran10` preset drops cols 73+ by default; shifted-column recovery is opt-in.
- **17:03** — `hostlib`: a declarative marshalling layer for host builtins.
- **23:25** — A GitHub Pages docs site: a `markdown-it-py` static-site generator (`gh-pages/`), Actions deploy.

## 2026-06-21 — genuine-source demos, and the fixes they flushed out

- **16:16** — `demos/`: genuine 1970s FORTRAN run as-is — netlib EISPACK/LINPACK/FFT/RKF45 with drivers, DECUS-tape sources, and Paul Boltwood's 1971 Game of Life.
- **16:16** — `examples/`: short Python scripts driving forterp as a library.
- **16:16** — Multi-file linking: several source files linked by unit name, like `f77 main.f lib.f`.
- **16:16** — Dialect gaps closed (gated; F66 still rejects them): the optional comma before an I/O list, two-word `END FILE`, `DATA` as an array name.
- **16:16** — `READ`/`ACCEPT` EOF fix: terminal input past end-of-stream branches to `END=` instead of looping.
- **16:16** — Sequence-association fix: an array element passed where the dummy is an array is re-viewed as a based array (LINPACK/RKF45 work-vector passing).

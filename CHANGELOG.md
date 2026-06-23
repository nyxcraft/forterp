# Changelog

## 2026-06-23 — a string arg mode

- **real FOROTS binary files (opt-in)** — `forbin` gains the on-disk half of the FORTRAN binary format: `pack_core_dump`/`unpack_core_dump` (36-bit words ↔ bytes, the standard 5-byte left-justified interchange form) and `encode_sequential`/`decode_sequential` (LSCW framing with the CONTINUE word at each 128-word disk-block boundary a record crosses), plus `encode_binary_file`/`decode_binary_file` over them. Validated against the V5 manual's D-7/D-8 worked example byte-for-byte (record 2's START count `0o32` to the boundary, then CONTINUE `0o114`). A new `Engine(dec_files=True)` makes unformatted sequential OPEN/CLOSE read and write these real files (type-aware via the existing `_bin_words`/`_assign_words`) instead of the portable JSON word-list, with a read-time sniff so legacy JSON and text data still load. Off by default — the portable on-disk form and float precision are unchanged for everyone (498 existing tests green); a host that wants files a PDP-10 could read opts in.
- **DOCS** — Documented the host-routine layer end to end. The API guide's "Custom host routines" section now covers both decorators (`@fcall`/`@uuo`), every arg mode (`IN`/`INT`/`FLOAT`/`STR`/`OUT`/`INOUT`/`ARRAY`), the `raw=True` escape hatch + its toolkit (`eng.eval`/`eng.arg_ref`/`eng.commons`/`eng.arrayview` + `OutRef`), the injectable `HostServices` model, and the `uuolib` monitor UUOs. DESIGN gains §7a — a worked walk-through of how the decorator/mode marshalling is implemented (decorator-returning-decorator, modes-as-instances-not-annotations, the generated wrapper, function attributes for discovery) — plus `uuolib`/`hostlib` rows in the module map.
- **02:17** — `hostlib` gains a `STR` arg mode: declare `args=(STR,)` and the body receives a Python `str`, with the quoted-literal-vs-packed-word resolution (a `StrLit`'s text verbatim, or a packed word decoded through the target's char codec) handled by the marshalling layer instead of repeated `eng.eval`/`tgt.unpack` in each body. The reusable shape behind filename/string args (OUTSTR, OPEN's `FILE=`, a save-detect).

## 2026-06-22 — host services for the embedder

- **16:21** — `uuolib`: the standard TOPS-10 monitor UUOs a FORTRAN-10 program expects to exist — `OUTSTR`, `OUTCHR`, `MSTIME`, `SLEEP`, `GETTAB` — installed (like the DEC library) only under the FORTRAN-10 dialect, on the engine's host seam (`emit`/`clock`). So a program that `CALL`s `OUTSTR` just runs, rather than each program bundling its own glue; a host that wants a richer or terminal-aware variant registers it afterward and overrides the baseline (the same never-shadow-a-defined-routine rule as `STDLIB`).
- **14:53** — `pyfortran10` now defaults `--target pdp10` (and `pyf66` stays `native`), matching the prebuilt `forterp.fortran10` / `forterp.f66` interpreters. The CLI front-end had set the FORTRAN-10 *dialect* but left the *value model* at `native`, so real DEC programs (36-bit words, packed ASCII, `.TRUE.`=-1) silently misbehaved on the 64-bit machine. Pass `--target native` for the DEC language on the portable machine; the general `forterp` driver is unchanged.
- **14:43** — `OPEN` decodes a packed *numeric* `FILE=`/`NAME=` spec as a SIXBIT/ASCII filename (the same way it already decodes `DEVICE=`), rather than `str()`-ing the raw word. A FORTRAN-10 numeric file spec *is* a packed name, so `OPEN(...,FILE=<packed word>,...)` now resolves to its real name and opens under the working directory — e.g. `OPEN(UNIT=1,DEVICE='GAM',FILE=IFILE)` reads `X.A` from the current dir with no custom device handler needed.
- **13:17** — CLI: `--recover-shifted-cols` exposes the shifted-column source recovery (off by default — a faithful FORTRAN-10 compiler drops cols 73+), so a deck reindented past col 72 runs without an embedding wrapper. A dropped-in `*.py` may now also define a `register(eng)` hook (called after the engine is built) to do setup the auto-discovered builtins can't — register an OPEN device, prime COMMON, inject a host-services facade; `run_source` gained the matching `setup=fn(eng)`. Together these let a whole game run on the bare CLI from its `*.py` + `*.FOR` alone.
- **12:33** — `hostlib` gains the host-routine *services* half: a baseline `HostServices` facade (`tty`/`files`/`clock`, over the engine's host seam only) and an `@uuo` decorator that injects it as the body's first arg — the counterpart to `@fcall` (a new alias of `@builtin`) for routines that talk to the host rather than compute. The facade is injectable (`eng.host_services`, threaded through `make_engine`/`build_engine`): set a richer subclass and `@uuo` routines receive it instead of the baseline, so a fuller monitor layers on without forterp depending on it. `@builtin`/`@fcall`/`@uuo` also gain `alias=`/`origin=`, and `builtins_in` discovers aliases.

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

## 2026-06-21 — genuine-source demos, then the release-readiness sweep

- **16:16** — `demos/`: genuine 1970s FORTRAN run as-is — netlib EISPACK/LINPACK/FFT/RKF45 with drivers, DECUS-tape sources, and Paul Boltwood's 1971 Game of Life.
- **16:16** — `examples/`: short Python scripts driving forterp as a library.
- **16:16** — Multi-file linking: several source files linked by unit name, like `f77 main.f lib.f`.
- **16:16** — Dialect gaps closed (gated; F66 still rejects them): the optional comma before an I/O list, two-word `END FILE`, `DATA` as an array name.
- **16:16** — `READ`/`ACCEPT` EOF fix: terminal input past end-of-stream branches to `END=` instead of looping.
- **16:16** — Sequence-association fix: an array element passed where the dummy is an array is re-viewed as a based array (LINPACK/RKF45 work-vector passing).
- **16:18** — Readability pass: clearer names, smaller focused dispatchers.
- **16:40** — Error-handling pass: clean `?`-diagnostics in place of raw tracebacks.
- **17:15** — Trimmed the evaluator hot path (~1.5× on tight loops).
- **18:14** — Capped a single array/`COMMON` allocation; wrote down the interpreter-not-a-sandbox trust model.
- **18:26** — Correctness vs `gfortran` (differential testing): per-record carriage control, list-directed grammar, three-digit exponents.
- **18:52** — Extended the dual-run harness to compare terminal output; pinned the public-API contracts.
- **20:00** — Packaging & CI: PyPI/distribution readiness — `build` + `twine`, a 3.9–3.13 test matrix.
- **20:13** — Committed the built docs site, kept in sync automatically by a pre-commit hook.
- **20:51** — Hardened the resource limits, `INCLUDE` resolution, and duplicate-unit detection.
- **20:58** — Tag-triggered PyPI release via OIDC Trusted Publishing, gated on tests/lint/format and `tag == __version__`.
- **21:42** — Docs hygiene: folded the origin history into this changelog; removed the HISTORY/HANDOFF/third-party files; recorded FCVS as public domain; trimmed the overuse of "faithful".
- **22:41** — ruff maintained at commit time (a pre-commit hook), with import-sort and dead-`noqa` rules.
- **23:06** — CLI `--version`; moved the engine builders into `forterp.runtime`.
- **23:23** — Slimmed the package root to exactly `__all__` — dropped the back-compat aliases.
- **23:33** — `forterp.debug.oob_census()`: a public OOB-access census, so consumers no longer poke engine internals.
- **23:47** — New docs: a CLI reference and a `forterp.*` API programmer's guide.
- **23:51** — Docs-site polish: a "Docs" breadcrumb, interpreter-design vocabulary on the home-page pipeline, a high-contrast beta stamp.
- **23:58** — CLI loads `.py` host-routine modules beside FORTRAN source: a `*.py` argument is imported and its `@builtin` routines are discovered (`hostlib.builtins_in`) and registered — drop them in, no registry/`__init__`.

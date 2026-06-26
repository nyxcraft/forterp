# Changelog

## 2026-06-26 — FCVS: canonical decks, the whole corpus byte-matches gfortran

- **00:24** — Two-word storage-associated COMPLEX (the FCVS COMPLEX cluster); a field/X edit stays within its record on multi-record input.
- **00:40** — Cleared FM909 (COMPLEX internal WRITE + Gw.dEe trailing blanks + nX advance), FM715 (CHARACTER functions), FM509 (a substring sequence-associated onto an array dummy).
- **09:34** — Validate the gfortran-unreliable routines by their own self-check, not exclusion; an output implied-DO snapshots each value at its trip.
- **10:09** — Merged `fcvs77/` into one `tests/fcvs/` corpus (F66 runs the 52-routine subset, F77 runs all 192); added the full gfortran `-std=legacy` differential over all 192 (`test_fcvs_golden.py`).
- **11:19** — Cleared FM010 / FM906 / FM903 / FM404 / FM901 / FM111 (keyword-prefixed assignment vs GO TO/CALL; list-directed D-exponent + COMPLEX `(re,im)`; `Iw.0` of zero is all-blank; card-unit widthless-A + multi-record `/`; A-input into a substring uses the window length; I/O-list implied-DO leaves its control var at the terminal value + E-of-zero).
- **12:22** — Documented each GF_CANNOT_RUN routine's exact cause; FM001's by-design FORCE-FAIL ("FORCE FAIL CODE TO BE EXECUTED") is now counted as a negative-test pass, so the corpus' counted-error total is a genuine 0.
- **13:06** — Real input accepts FORTRAN's letterless signed exponent (`0.987+1` = 0.987×10¹) and reads a no-digit-mantissa field (`.`, `+.E00`) as zero.
- **13:58** — Vendored the canonical NIST `.DAT` input decks (`tests/fcvs/*.DAT`, from `gklimowicz/FCVS`; our `.FOR` are byte-identical), and `_card_deck` reads a sibling `.DAT` first — replacing the lossy `CARD nn` reconstruction. Fixed what the correct decks exposed: blanks are insignificant in a FORMAT (`3 I4` → `3I4`, `F5 .2` → `F5.2`) and E/D output renormalises when a round bumps the mantissa to 1.0. gfortran now runs all 192.
- **14:05** — A scale factor has no effect on `G` in its F-form range (clears FM900); E/D rounds the mantissa once (no double-round) and the `nP` scale persists across a reverted format on input (clears FM110). The whole corpus byte-matches gfortran **191 of 192**; the lone `KNOWN_GF_DIFF` is FM111, where gfortran is the outlier (it overflows `F2.1` of a value rounding to zero) and forterp matches the routine's own printed CORRECT line.
- **14:28** — Docs: recorded the conformance drive across the guides + CHANGELOG; see [docs/FORTRAN77.md §8](docs/FORTRAN77.md).

## 2026-06-25 — FCVS-77 conformance punch-list (per-routine to byte-match)

- **14:05** — F77 input niceties: blanks before a numeric exponent (`1545 E7` → `1545E7`), zero-trip DO + the F77 post-loop index value, L-format accepts an optional leading point, widthless A uses the io-list item's length (output + input).
- **15:30** — Four FCVS one-offs (intrinsic-as-actual-arg, statement-function result type, INQUIRE EXIST); direct-access formatted I/O — multi-record writes + CLOSE/reopen persistence.
- **16:17** — DO fixes: a zero-trip inner DO sharing a terminal label with an enclosing DO; convert DO parameters to the DO variable's type before the trip count.
- **16:50** — Edit-descriptor conformance: widthless-A input declared length, E/F (neg-zero, leading-zero drop, Ew.dEe), and FM912 — Iw.m, SP/SS, TL/TR, the `:` terminator, and substring I/O targets.
- **18:00** — Advance to a new line before a terminal READ/ACCEPT; width'd numeric input defaults to BLANK=NULL on FORTRAN-10/F77.
- **19:13** — Real list-directed input (X3.9-1978 13.6) — clears FM923; model the ENDFILE record so BACKSPACE doesn't clobber data — clears FM411.
- **20:01** — COMMON declarations for one block concatenate — clears FM302 (F77 FCVS errors to 0).
- **20:15** — Golden harness hardening: enforce FCVS's own completeness accounting (no early termination), guard that every require-INSPECTION routine stays golden-validated, align the golden harness with the conformance harness (FM256).
- **21:21** — `carriage_control` option (file vs printer output) + a tighter golden compare.
- **21:46** — Per-routine matches: DATA PARAMETER repeat + CHARACTER PARAMETER value (FM500), a source label preserved on END IF (FM255/260), assigned-FORMAT label in `WRITE(u,intvar)` (FM252), statement functions — zero args + dummy shadowing (FM311).
- **22:35** — WRITE to a CHARACTER-array internal file (records = elements); F editing drops the optional leading zero to fit a narrow field (FM101/103/108).
- **23:25** — FORTRAN-shaped list-directed output (T/F logicals, CHARACTER text, concatenation); defer the first FOROTS advance-before record's leading newline; GO TO a labeled END IF.
- **23:50** — Unformatted COMPLEX I/O + CHARACTER-array internal READ + slash on input; split the correct gfortran-oracle divergences out of the bug punch-list.

## 2026-06-24 — FORTRAN 77 support (the `f77` branch)

- **15:20** — F77 dialect (`forterp.F77`/`f77`; the `character_type`/`block_if`/`save_stmt`/`intrinsic_stmt`/`list_directed_io`/`eqv_operators`/`slash_dim_bound` knobs) + block IF / DO WHILE / SAVE / INTRINSIC and generic intrinsics.
- **15:42** — CHARACTER scalars: decls, blank-pad/truncate assign, `//`, comparison, LEN; the CHAR/ICHAR/INDEX/LGE..LLT intrinsics; and substrings `S(i:j)` (read + lvalue).
- **16:06** — CHARACTER I/O: A-format, internal files (READ/WRITE to a CHARACTER variable), and INQUIRE (by FILE / by UNIT).
- **16:36** — Restored the 140 F77/CHARACTER FCVS routines (`tests/fcvs77/`, gfortran-verified pristine) + the conformance baseline.
- **16:43** — F77 front-end fill-ins: IMPLICIT CHARACTER\*len, optional DO-label comma, LOGICAL/COMPLEX PARAMETER, widthless A, list-directed I/O, keyword I/O control lists (`READ(UNIT=u,FMT=f)`), OPEN positional + keyword specs, `.EQV./.NEQV.`, blank COMMON `//`, `CHARACTER*(param)`, F77 array-bound `:`, and blanks within a dotted operator.
- **19:15** — Assumed-size declarators `A(...,*)` — the F77 FCVS corpus parses with 0 gaps.
- **19:28** — Sequential files: an unconnected unit auto-connects as an in-memory scratch; F77 formatted-text files round-trip `/`, `X`, and read-side FORMAT reversion → F77 FCVS to 0 errors.
- **20:13** — Fixed the runner's masked-failure bug (it ignored the FM2xx+ "TESTS FAILED" summary verb — 111 failures were hidden).
- **20:17** — Added gfortran golden outputs + the differential output validation (no gfortran needed at test time).
- **20:28** — INQUIRE connection specifiers (ACCESS/FORM/SEQUENTIAL/DIRECT/FORMATTED/UNFORMATTED).

## 2026-06-24 — the monitor rename, override docs, and PyPI release wiring

- **09:58** — Dropped the `@builtin` decorator alias — `@fcall`/`@uuo` are the two authoring decorators; "builtin" stays the registry noun (`register_builtins`/`builtins_in`/`BUILTINS`). Synced the guides + CHANGELOG to the host-layer work.
- **10:23** — Reformatted this changelog as reverse-chronological day blocks (newest first), terse timed one-liners.
- **10:44** — Renamed the interactive shell `Monitor` → `CommandProcessor` (`forterp.command`) and dropped the REPL's `MONITOR` reserved word — freeing "monitor" for the executive facade.
- **10:59** — Renamed the `@uuo` facade `Host` → `Monitor` (`monitor(eng)`, `eng.monitor`, the `monitor=` builder kwarg) — `mon` now abbreviates its actual type.
- **11:09** — API guide: how to override the `Monitor` facade with your own (subclass + inject via `monitor=` or `eng.monitor`; the bundled `uuolib` UUOs read the engine seam directly, not the facade).
- **11:33** — `_load_builtins` no longer leaks `sys.path`/`sys.modules`; the `STR` arg mode strips a packed word's padding so it equals the literal text.
- **11:38** — Documented the `hostlib.host_ppn`/`host_user` identity helpers alongside `mon.identity`.
- **11:56** — PyPI release wiring: publish through the `forterp-pypi` environment, with a manual approval gate (the `release` environment + a required reviewer) fronting the tag-triggered publish.
- **11:57** — Released **0.1.0** to PyPI (`pip install forterp`).
- **14:02** — The interactive command processor opens with an interpreter-style banner (version, dialect, target, host) and gains `COPYRIGHT` / `CREDITS` / `LICENSE` commands.
- **14:02** — `^C` at the interactive prompt re-prompts instead of dumping a traceback (the command processor and the REPL); `^C` during a program run halts cleanly (`?Interrupted`, rc 130).

## 2026-06-23 — host services, terminal modes, and real binary files

- **02:17** — `hostlib` `STR` arg mode: `args=(STR,)` gives the body a Python `str` (a quoted literal verbatim, or a packed word decoded via the target codec), lifting the StrLit-vs-packed resolution out of each body.
- **04:05** — Real FOROTS binary files (opt-in `Engine(dec_files=True)`): on-disk word↔byte packing + LSCW framing (`forbin`), validated against the V5 D-7/D-8 example byte-for-byte; plus end-to-end host-routine docs (API `@fcall`/`@uuo` + arg modes + `raw`, DESIGN §7a).
- **09:56** — Terminal echo-control seam (`Engine(set_echo=fn)` + `mon.tty.echo`); renamed the host-services facade `HostServices`/`host_services` → `Host`/`host`.
- **12:24** — `run_source` installs a default terminal echo (`runtime.default_terminal_echo` flips the tty's termios `ECHO`, restored after); added the autowrap seam (`set_autowrap` + `mon.tty.autowrap`, `TRMOP.` `.TONFC`).
- **17:50** — Host identity (`mon.identity` — uid/gid/login/PPN); `GETTAB` models the job tables (`.GTPPN` → guest `[0,0]`, `.GTJTC` → 0), with an `eng.gettab` registry and `UnmodeledMonitorTable` for the rest.
- **21:14** — Review fixes: `OUTSTR` uses the target's `chars_per_word`; restored the `OPEN` read's `with`; a host `builtins=` table no longer shadows a program-defined unit; a stdlib-shadowing `.py` arg gives a clean `?`-diagnostic.
- **21:52** — Two-word DOUBLE PRECISION binary I/O (the KL10 doubleword, lossless where the single rounded); `_bin_words`/`_assign_words` code per declared type, per element; a config-mismatched binary file fails loud (`OSError`) instead of a garbage text read.
- **23:29** — FORTRAN-10 free CR-LF: `emit()` wraps terminal output at the carriage width host-side (`Engine(tty_width=80, tty_autowrap=True)`, deferred margin); strict F66 never wraps; CLI `--no-wrap`.

## 2026-06-22 — host services for the embedder

- **12:33** — `hostlib` host-services half: a baseline `HostServices` facade (`tty`/`files`/`clock`, over the engine's host seam) + an `@uuo` decorator that injects it — the counterpart to `@fcall` for routines that talk to the host; injectable via `eng.host_services`. `@builtin`/`@fcall`/`@uuo` gain `alias=`/`origin=`.
- **13:17** — CLI `--recover-shifted-cols` (opt-in shifted-column recovery); a dropped-in `*.py` may define a `register(eng)` hook, and `run_source` gains `setup=fn(eng)`.
- **14:43** — `OPEN` decodes a packed numeric `FILE=`/`NAME=` as a SIXBIT/ASCII filename (as it already does `DEVICE=`), not `str()` of the raw word.
- **14:53** — `pyfortran10` defaults `--target pdp10` (and `pyf66` stays `native`), matching the prebuilt interpreters.
- **16:21** — `uuolib`: the standard TOPS-10 monitor UUOs (`OUTSTR`/`OUTCHR`/`MSTIME`/`SLEEP`/`GETTAB`), installed under the FORTRAN-10 dialect on the engine's host seam.

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

## 2026-06-20 — real-machine defaults, host marshalling, docs site

- **00:00** — The `fortran10` preset drops cols 73+ by default; shifted-column recovery is opt-in.
- **17:03** — `hostlib`: a declarative marshalling layer for host builtins.
- **23:25** — A GitHub Pages docs site: a `markdown-it-py` static-site generator (`gh-pages/`), Actions deploy.

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

## 2026-06-17 — hardening for the next program

- **22:49** — `COMMON` sizing, dummy procedures, continuation comments, lowercase `nH` Hollerith.

## 2026-06-16 — and so it begins...

- **15:29** — Initial FORTRAN-10 / F66 interpreter: lexer, parser, AST, tree-walking engine, the FORMAT runtime, the `forlib` library, diagnostics.
- **16:07** — F66 §3.1.6 blanks-insignificance, via a tokenizer parse-retry.
- **18:49** — `RAN`/`SETRAN`, COMPLEX formatted input, NAMELIST and random-access I/O, `%FTNLID` warnings.
- **18:51** — FOROTS binary-record codec (LSCW framing + DEC-10 float), `MODE='BINARY'`.
- **23:12** — Front-end: DEC TAB-format source, the bare main program, integer-vs-`.EQ.` lexing.

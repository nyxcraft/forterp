# Changelog

In order, oldest-first. It opens with the **pre-extraction** lineage — the interpreter's
life inside the `pdp10-empire` monorepo before `forterp` was split into its own repository
(2026-06-19) — then follows the standalone `forterp` repository. Bullets use local commit
times (US Eastern); pre-extraction bullets additionally cite their `pdp10-empire` commit.

## Pre-extraction — in `pdp10-empire`, before the 2026-06-19 split

`forterp` began on 2026-06-16 as a FORTRAN-10 interpreter inside the `pdp10-empire` monorepo,
written to run real 1970s DEC FORTRAN — Walter Bright's 1978 *Empire* and UT Austin's 1979
*DECWAR* — **unmodified**. That goal set the north star the project still follows:
**faithfulness over polish**, reproducing PDP-10 / FORTRAN-10 behavior and its quirks rather
than cleaning them up. It also forced the load-bearing design decision — a real machine value
model (36-bit two's-complement words, 5-character packed ASCII, `.TRUE.` = −1) — because a
naive interpreter would run the games subtly *wrong*.

The monorepo grew in layers — a language core (`f66`), a TOPS-10 operating environment (the
interactive monitor), and the games on top — and the language core never imported the layers
above it. That discipline is what let `f66` be lifted out cleanly: over three days the few
game-ward couplings were severed (a pluggable `OPEN` device registry, a pluggable `Target`
value model, a parameterized `Dialect`, and FOROTS binary I/O moved into a `fortran10`
layer), at which point the interpreter was provably standalone and was split into its own
repository. A configurable FORTRAN-66 interpreter is reusable well beyond those games, while
the PDP-10 target specifically remains load-bearing for running them faithfully.

Below are the interpreter-core milestones from that era; the hashes reference `pdp10-empire`,
not this repo. (The TOPS-10 monitor, the DECWAR multiplayer port, and the instrumented
terminal / god-view from this period stayed behind in the monorepo and are not part of
`forterp`.)

### 2026-06-16

- **15:29** — Initial FORTRAN-10 / F66 interpreter — fixed-form lexer and parser, AST, tree-walking engine, the `FORMAT` runtime, the intrinsic/runtime library (`forlib`), and diagnostics. (`dfaeda7`)
- **16:07** — Honor F66 §3.1.6 — blanks are insignificant within tokens, via a tokenizer parse-retry. (`268deb8`)
- **18:49** — `RAN`/`SETRAN` intrinsics; `COMPLEX` formatted input; `NAMELIST` I/O; random-access (direct) I/O; `%FTNLID`-style listing warnings. (`7a3a7a3`)
- **18:51** — FOROTS binary-record codec — LSCW framing + DEC-10 floating point — `MODE='BINARY'`. (`cbb06e8`)
- **23:12** — Front-end: DEC TAB-format source lines, the bare (unnamed) main program, and integer-vs-`.EQ.` lexing. (`07c2c5f`)

### 2026-06-17

- **22:49** — `COMMON`-block sizing, dummy procedures, continuation-line comments, and lowercase `nH` Hollerith. (`4ca49c0`)

### 2026-06-18

- **08:58** — A pluggable `OPEN` device registry — decouples file/device I/O from the host application. (`55c91fb`)
- **09:23** — Extracted the machine value model behind a pluggable `Target` (36-bit word semantics). (`5abce63`)
- **09:43** — Parameterized the source dialect (`Dialect`) on the front-end. (`9bf7b93`)
- **11:23** — Introduced a `fortran10` layer atop the `f66` core, and relocated FOROTS binary I/O into it. (`92f9113`)

### 2026-06-19

- **23:26** — **Split out into the standalone `forterp` repository** — by then restructured under `sixbit/f66/` and named *SIXBIT FORTRAN 66*; `pdp10-empire` became a downstream consumer. (Later renamed `pyf66` → `forterp`; the standalone repo's own history continues below, from its 2026-06-18 initial commit.) (`2be5df5`)

## 2026-06-18 — standalone, and a pluggable machine

- **13:44** — Initial commit: the FORTRAN-66 interpreter, lifted out of the original monorepo into its own `src/` package with a clean public API and the FCVS conformance corpus.
- **14:09–14:30** — Routed the value model through a pluggable `Target`, three steps at a time: the `INT`-family / `LSH` intrinsics, the logical algebra, then the character codec.
- **14:47** — Added the `NATIVE` 64-bit target and **made it the default** — `PDP10` becomes the opt-in faithful machine.
- **15:19** — A provisional, *unvalidated* `VAX` target plus the seam knobs it needs (little-endian, low-bit truth).
- **15:39** — Curated the FCVS corpus to F66-only — removed the 140 F77 / `CHARACTER` routines.
- **16:25–16:38** — Adopted `ruff` lint + `ruff format` (Black-standard) across the tree.
- **23:59** — Renamed the package `f66` → **`forterp`** and made `F66` the default dialect (futureproofing the name for a multi-dialect interpreter).

## 2026-06-19 — CLI, monitor, REPL, debugger — and the conformance + review work

- **00:00** — Three console front-ends: `pyf66`, `pyfortran10`, and `forterp --std` — thin dialect presets over one engine, like `g77`/`gfortran` over gcc.
- **00:48–01:06** — Gated the DEC I/O surface, the DEC intrinsics, and random-access I/O under F66; added the V5 math / rotate intrinsics.
- **01:11** — `--check`: parse and list every diagnostic without running — a strict-ANSI-F66 conformance linter.
- **10:16** — An interactive **command monitor** — a small, FORTRAN-focused descendant of the TOPS-10 `.` prompt (`RUN`/`LOAD`/`SET`/`SHOW`/…).
- **10:20–10:52** — An immediate-mode **REPL** (statements run as you type; `DO` blocks collected across lines), then refactored onto two reusable engine/parser primitives.
- **11:03** — Factored target/dialect config into shared registries + `engine_kwargs` (one source of truth).
- **12:31** — An **off-by-default per-statement tracer hook** + frame stack — and on it, an interactive **debugger + statement profiler** in the monitor. A plain run pays nothing.
- **14:24–16:08** — Formatted-input conformance: bad-field errors, short-record blank-extension, the BZ-into-exponent behavior pinned and documented; the random-access `WRITE(u'0)` clobber fixed; CLI error hygiene.
- **21:10–21:42** — Exposed the embedding API as public surface; added the prebuilt `forterp.fortran10` / `forterp.f66` interpreters (the easy path).
- **21:47** — **Gated every non-F66 feature behind a `Dialect` flag** (18 knobs) — so F66 genuinely *rejects* non-F66 constructs; the test harness now dual-runs F66-compliant programs under both dialects and asserts they agree.
- **22:11** — R4: illegal `EQUIVALENCE` shapes (backward COMMON extension, cross-COMMON, contradictory) now raise instead of silently mis-laying; the multi-word `COMPLEX`/`DOUBLE` storage boundary documented.
- **22:36** — `test_interpreter.py` pins the prebuilt-interpreter API contract.
- **23:06–23:41** — R3: list-directed + NAMELIST bad fields now raise like formatted; `forbin` raises a coherent error on unrepresentable floats (no more silent exponent wrap); the REPL's reserved prompt words documented.

## 2026-06-20 — faithful defaults, host marshalling

- **00:00** — The `fortran10` preset is **faithful on columns by default** (cols 73+ dropped, like real FORTRAN-10); shifted-column recovery is opt-in via `source_options`, for a driver that needs it.
- **17:03** — `hostlib`: a declarative marshalling layer for host builtins.

## 2026-06-21 — a documentation site, genuine-source demos, and the fixes they flushed out

- **GitHub Pages site** — a small `markdown-it-py` static-site generator (`gh-pages/`) publishing the docs and changelog, DEC-maroon themed with content-hash cache-busting; deployed by `.github/workflows/pages.yml`.
- **`demos/`** — a corpus of genuine 1970s FORTRAN run as-is: verbatim netlib numerical libraries (**EISPACK**, **LINPACK**, **FFT**, **RKF45**), each with a small `EXAMPLEn.FOR` driver; DECsystem-10 sources recovered from DECUS tapes (WKDAY, NORMAL, ASTRO, WGMM11, CHARTR); and Paul Boltwood's 1971 Game of Life. EISPACK is byte-for-byte netlib; NORMAL had its SOS line-sequence numbers stripped as transport residue; the 1971 Life had one OCR'd list-terminator constant corrected against the page scan.
- **`examples/`** — short Python scripts showing how to drive forterp as a library: run + capture output, dialect selection, the pluggable target, FORTRAN-as-compute-kernel via `COMMON`, and parse-only inspection.
- **Multi-file linking** — the CLI now accepts several source files and links them by unit name, like `f77 main.f lib.f`, so a driver and a separately-held library run as one program.
- **Dialect gaps closed**, each flushed out by real period source and correctly gated (F66 still rejects them): the optional comma before an I/O list (`WRITE(u,f),list`), the two-word `END FILE` spelling, and `DATA` usable as an ordinary array name.
- **`READ`/`ACCEPT` EOF fix** — terminal input past end-of-stream now branches to `END=` (or stops cleanly) instead of looping forever; it had recognized only an in-band CONTROL-Z, never an empty `readline()`.
- **Sequence-association fix** — an array element passed where the dummy is an array (`CALL SUB(X(I), …)`) is now re-viewed as an array based at that element rather than crashing; this is exactly how LINPACK and RKF45 pass the start of a work vector.

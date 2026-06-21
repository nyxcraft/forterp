# Changelog

The life of the **standalone** `forterp` repository, in order. The pre-standalone origin —
how a FORTRAN interpreter built to run the 1978 games *DECWAR* and *Empire* became a
separable, configurable product — is told in the project history. Times are
local commit times (US Eastern).

## 2026-06-18 — standalone, and a pluggable machine

- **13:44** — Initial commit: the FORTRAN-66 interpreter, lifted out of `pdp10-empire` into its own `src/` package with a clean public API and the FCVS conformance corpus.
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

# forterp demos

Small, single-file FORTRAN programs for forterp: runnable demonstrations plus
genuine period sources that serve as historical dialect-coverage targets. The
runnable demonstrations are plain ANSI **FORTRAN 66** unless noted. After
`pip install -e .` (from the repo root), run one with:

```sh
python -m forterp EXAMPLE.FOR                  # strict ANSI FORTRAN 66 (the default)
python -m forterp --std fortran10 EXAMPLE.FOR  # the DEC FORTRAN-10 superset
python -m forterp MAIN.FOR LIB.FOR             # several files link together by unit name
```

(equivalently, the installed `pyf66 EXAMPLE.FOR` / `pyfortran10 EXAMPLE.FOR` commands).

## Math & science — strict ANSI FORTRAN 66

| File | What it does |
|------|--------------|
| [`EISPACK.FOR`](EISPACK.FOR) | **Genuine, unmodified 1976 EISPACK** eigensystem library (`RS → TRED2 → TQL2 → PYTHAG`) — no main program; driven by `EXAMPLE1.FOR`. |
| [`EXAMPLE1.FOR`](EXAMPLE1.FOR) | Driver for `EISPACK.FOR`: eigenvalues of a 4×4 symmetric tridiagonal matrix. Run the two together (see below). |

`EISPACK.FOR` is real period source run **as-is** — the routines are verbatim public-domain
EISPACK (Argonne National Laboratory, 1976) from netlib, with no main program of its own.
`EXAMPLE1.FOR` is an original driver; link the two the way a compiler links `main.f lib.f`:

```sh
python -m forterp EXAMPLE1.FOR EISPACK.FOR
```

## Period numerical libraries

These are compact library extracts paired with new `EXAMPLEn.FOR` drivers. The
archival routines themselves are unchanged. Two of them (`LINPACK`, `RKF45`) drove a
real interpreter fix — sequence association of an array-element actual with an array
dummy argument — and all three now run under forterp and match `gfortran -std=legacy`.

| Library and driver | Date | forterp status | What it exercises |
|--------------------|------|----------------|-------------------|
| [`LINPACK.FOR`](LINPACK.FOR) + [`EXAMPLE2.FOR`](EXAMPLE2.FOR) | 1978 | **Runs** | `DGEFA`/`DGESL` Gaussian elimination and the four original Level-1 BLAS dependencies. Solves a 3×3 system to the exact `(1,-2,-2)`. |
| [`FFT.FOR`](FFT.FOR) + [`EXAMPLE3.FOR`](EXAMPLE3.FOR) | 1968 | **Runs under FORTRAN-10** | R. C. Singleton's mixed-radix complex FFT. Transforms an eight-point impulse and performs the inverse transform. |
| [`RKF45.FOR`](RKF45.FOR) + [`EXAMPLE4.FOR`](EXAMPLE4.FOR) | 1975 era | **Runs** | Watts and Shampine's adaptive Runge-Kutta-Fehlberg integrator. Solves `y'=-y` and matches `exp(-t)` to ~1e-9. |

Run or reproduce them from this directory:

```sh
python -m forterp --check EXAMPLE2.FOR LINPACK.FOR
python -m forterp EXAMPLE2.FOR LINPACK.FOR
python -m forterp --std fortran10 EXAMPLE3.FOR FFT.FOR
python -m forterp --check EXAMPLE4.FOR RKF45.FOR
python -m forterp EXAMPLE4.FOR RKF45.FOR
```

`LINPACK.FOR` and `RKF45.FOR` each pass an array element as the starting address of a
work vector to a routine whose dummy is declared an array — FORTRAN sequence
association. forterp had bound that dummy to a scalar `CellRef` and then crashed
calling `.loc()` on it; it now re-views the cell's storage at its offset as the array
base, so both run (`LINPACK` solves to `(1,-2,-2)`; `RKF45` matches `exp(-t)` to
~1e-9). `FFT.FOR` needs `--std fortran10` only for its failure-path `PRINT`
statement, which strict F66 rejects.

`LINPACK.FOR` combines the verbatim Netlib `DGEFA` and `DGESL` sources (both marked
August 14, 1978) with [contemporaneous, labeled-loop transcriptions](https://github.com/virtualcell/vcell-fvsolver/tree/a85ef2bde809dd62808c9d2e99f28e8ed0ccd00e/blas)
of `DAXPY`, `DDOT`, `DSCAL`, and `IDAMAX` (each marked March 11, 1978). The Netlib
Singleton FFT is the September 1968 source with its archive's documented 1995
temporary-storage limit correction. `RKF45.FOR` cites Sandia report SAND75-0182
in its own header.

## Genuine DECsystem-10 sources

These files are unmodified program text recovered from DECUS PDP-10 tapes. Only
non-source transport residue was removed: archival NUL, DEL, and CR bytes, and (on
`NORMAL.FOR`) the SOS editor's leading line-sequence numbers — `00100`-style metadata
the compiler never saw, rendered as literal text when the tape was flattened to ASCII.
The FORTRAN itself is untouched. They are preserved as dialect-coverage targets.

| File | Date | Dialect | What it does |
|------|------|---------|--------------|
| [`WKDAY.FOR`](WKDAY.FOR) | 1978 | FORTRAN-10 | Interactive twentieth-century weekday calculator; self-contained. |
| [`NORMAL.FOR`](NORMAL.FOR) | 1977 | FORTRAN-10 | Normalizes a sample of test scores; self-contained. |
| [`ASTRO.FOR`](ASTRO.FOR) | 1974/75 | F40 / FORTRAN IV | Computes planetary positions, ephemerides, and astrological charts; optional line-printer output calls `OFILE`. |
| [`WGMM11.FOR`](WGMM11.FOR) | 1976 | F40 V27A | Two-terminal experimental wargame; all application routines are in one file, with TOPS-10 terminal and file I/O. |
| [`CHARTR.FOR`](CHARTR.FOR) | 1973 | FORTRAN IV | Generates flowcharts from FORTRAN source; all application routines are in one file and DEC library routines provide file I/O. |

Source: [Trailing Edge DECUS PDP-10 archive](https://pdp-10.trailing-edge.com/),
cross-referenced against the February 1978
[DECUS program catalog](https://bitsavers.org/pdf/dec/decus/programCatalogs/DECUS_Catalog_PDP-10_Apr78.pdf).

## Fun

| File | Dialect | What it does |
|------|---------|--------------|
| [`LIFE.FOR`](LIFE.FOR) | FORTRAN IV G | John Conway's Game of Life (1970) — a genuine June 1971 implementation by Paul Boltwood; a glider walks an 80×80 grid. |

`LIFE.FOR` implements John Conway's Game of Life — the cellular automaton he
devised in 1970 — and is transcribed from the source listing on page 18 of
[*Lifeline*, Volume 2](https://conwaylife.com/wiki/Lifeline_Volume_2), published
in June 1971. Paul Boltwood of Ottawa wrote the IBM FORTRAN IV G program, and
editor Robert T. Wainwright slightly modified its card input and output display.
It keeps an 80-by-80 universe as linked lists of live and candidate cells rather
than scanning the entire array. The
[original page scan](https://conwaylife.com/wiki/File:Lifeline_vol_2_p18.jpg)
is the authority; the wiki's OCR transcript contains numerous substitutions and
missing statement labels, corrected here against the scan. One such correction —
a `NEXGEN` list-terminator test the transcript rendered as `-9999` where the scan
reads `9999` (matching its sibling loop) — otherwise crashes the program, which is
how both forterp and gfortran flagged it before the scan confirmed the reading.

### Running LIFE

It reads punch-card input: a control card (cycles, print-interval, and start row,
in `FORMAT(3I5)`), then one 80-column pattern card per row (any non-blank is a live
cell), ended by EOF. To walk a glider down the grid, printing every 4th of 16
generations:

```sh
printf '   16    4   10\n     O\n      O\n    OOO\n' \
  | python -m forterp --std fortran10 LIFE.FOR
```

## On the dialect

The math/science programs are deliberately **strict ANSI FORTRAN 66** — fixed-form
columns 7–72, Hollerith (`nH`) text in `FORMAT`s, one-trip `DO` loops, and the F66
subscript / `DO`-bound forms — so they run under the default `f66` dialect and double
as a conformance demo. `LIFE.FOR` uses DEC FORTRAN-10 features (IMPLICIT typing,
quoted-string literals, alternate-return CALLs), so it needs `--std fortran10`.

## Where to find period FORTRAN source

Genuine 1970s FORTRAN to run as-is (licensing for each is the reader's call — much of this
era predates formal open licensing and was freely exchanged):

**Scientific (public domain, standard FORTRAN — runs well):**
- [netlib EISPACK](https://netlib.org/eispack/) — eigensystems (1976; used by `EISPACK.FOR`)
- [netlib LINPACK](https://netlib.org/linpack/) — linear algebra (1978 routines used by `LINPACK.FOR`)
- [Singleton FFT](https://netlib.org/go/fft.f) — mixed-radix FFT (1968; used by `FFT.FOR`)
- [netlib RKF45](https://netlib.org/ode/rkf45.f) — adaptive ODE integration (1975 era; used by `RKF45.FOR`)
- [netlib FFTPACK](https://netlib.org/fftpack/) — later FFT library (the archived release is 1985)
- [netlib root](https://netlib.org/) — the canonical archive of public-domain numerical FORTRAN

**Games (mixed dialects — check each before assuming it's standard FORTRAN):**
- [kristopherjohnson/advent](https://github.com/kristopherjohnson/advent) — Crowther & Woods *Adventure*, original PDP-10 FORTRAN (parses + initializes under forterp)
- [IF Archive — games/source](https://www.ifarchive.org/indexes/if-archive/games/source/) — *Adventure*/*Dungeon* variants
- [fortran-gaming/toronto-fortran-games](https://github.com/fortran-gaming/toronto-fortran-games) — MIT, but a Toronto *structured-FORTRAN preprocessor* dialect (`[ ] :`), so **not** runnable as standard FORTRAN
- [bitsavers TOPS-10 software](https://bitsavers.org/bits/DEC/pdp10/) — period DEC tapes/listings (often scans, not clean text)

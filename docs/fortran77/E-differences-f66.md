# Appendix E. Differences from FORTRAN 66

FORTRAN 77 is mostly a superset of FORTRAN 66, but not entirely: a number of changes mean a program
that conformed to the 1966 standard can behave **differently** — or stop being valid — under the
1978 standard. The standard itself catalogues these in its *Criteria, Conflicts, and Portability*
appendix *(X3.9-1978 Appendix A)*; this chapter restates that list in plain terms and, because
forterp implements **both** dialects, notes what forterp does with each.

This is the bridge between the two manuals. If you maintain old code, read it alongside the
[FORTRAN 66 reference manual](../fortran66/README.md) — the same source can run under both `F66` and
`F77`, and what follows is exactly what changes when you switch.

> Throughout, **forterp** notes use: *enforced* = forterp applies the F77 rule on the `F77` dialect;
> *gated* = the behavior differs by dialect (or a knob); *lenient* = forterp still accepts the old
> form even though strict F77 forbids it (an accept-more extension that cannot break a conforming
> program).

## The headline change: the zero-trip `DO`

The single most consequential difference. In FORTRAN 66 a `DO` loop is **one-trip** — its range
always runs at least once. In FORTRAN 77 the iteration count is computed up front as
`MAX(INT((m2 - m1 + m3) / m3), 0)`, so a loop whose limit is already passed runs **zero** times
*(§11.10.4)*.

```fortran
      K = 0
      DO 1 I = 1, 0
      K = K + 1
1     CONTINUE
C     -> F77: K = 0 (loop skipped).  F66: K = 1 (one trip).
```

**forterp: gated.** Under `F77` the loop is zero-trip; under `F66`/`FORTRAN10` it is one-trip. The
`zero_trip_do` dialect knob flips either default. This genuinely changes results, so always know
which dialect you are running.

## Conflicts catalogued by the standard

The 1978 standard lists these as known conflicts with 1966 *(Appendix A)*. Grouped by area:

### Source form

| # | Change in FORTRAN 77 | forterp |
|---|----------------------|---------|
| 1 | An all-blank line (cols 1–72) is a **comment**; in F66 it could be the initial line of a statement. | enforced |
| 2 | Columns 1–5 of a **continuation** line must be blank. | enforced |
| 8 | A labeled `END` is disallowed (it could clash with an F66 initial line). | enforced |

### Arrays and storage

| # | Change in FORTRAN 77 | forterp |
|---|----------------------|---------|
| 4 | Each subscript must be **within its declared bound** — `A(11,1)` is invalid for `A(10,5)`. F66 allowed it if the *total* offset stayed within the array. | lenient by default (out-of-bounds read → `0`); `bounds_check` makes it a trap |
| 5 | Only an array **declared** one-dimensional may use a one-dimensional subscript in `EQUIVALENCE`. | enforced |
| 6 | A name may not be given an explicit type **more than once**. | enforced |
| 24 | An executable program may contain at most **one unnamed** `BLOCK DATA`. | enforced (the `BDU` diagnostic) |

### Hollerith and text

| # | Change in FORTRAN 77 | forterp |
|---|----------------------|---------|
| 3 | **Hollerith constants and Hollerith data are removed.** F66 allowed `nH` constants in `DATA`/`CALL`, non-character list items with `A` editing, and non-character arrays as formats. (The `H` *edit descriptor* survives — it is not a Hollerith constant.) | lenient — forterp still accepts Hollerith under `F77`; use `CHARACTER` for new code |
| 14 | Reading **into** an `H` edit descriptor is prohibited. | enforced |

### Control flow

| # | Change in FORTRAN 77 | forterp |
|---|----------------------|---------|
| 7 | The **extended range** of a `DO` is gone: you may not transfer *into* a loop's range from outside. | follows F77 |

### Input / output

| # | Change in FORTRAN 77 | forterp |
|---|----------------------|---------|
| 9 | No record may be written **after an endfile** record in a sequential file. | follows F77 |
| 10 | A sequential file may not mix **formatted and unformatted** records. | follows F77 |
| 11 | **Negative** unit identifiers are prohibited. | follows F77 |
| 12 | Parentheses around more than one I/O-list item must mark an **implied `DO`** (redundant parens are removed). | follows F77 |
| 13 | An entity associated with an input-list item is **defined at the same time** as the list item (F66 delayed it to end-of-statement). | follows F77 |

### Formatted output

| # | Change in FORTRAN 77 | forterp |
|---|----------------------|---------|
| 15 | The scale factor for `E`/`D`/`G` output is restricted to reasonable values. | follows F77 |
| 16 | A numeric output field must not be a **negative zero** (F66 required it for negative internal values). | follows F77 |
| 17–18 | `I` and `F` output must not produce **unnecessary leading zeros**. | follows F77 |
| 19 | A `+` or `-` is **required** before the exponent in `E`/`D` output (F66 allowed a blank for `+`). | follows F77 |

### Procedures and intrinsics

| # | Change in FORTRAN 77 | forterp |
|---|----------------------|---------|
| 20 | An intrinsic used as an **actual argument** must appear in an `INTRINSIC` statement, not `EXTERNAL`. (The F77 intrinsic class absorbs F66's "basic external functions".) | follows F77 |
| 21 | A conflicting type-statement no longer removes a name from the **intrinsic class**. | follows F77 |
| 22 | **29 new intrinsic names** were added and may clash with your subprogram names: `ACOS`, `ANINT`, `ASIN`, `CHAR`, `COSH`, `ICHAR`, `INDEX`, `LEN`, `LGE`/`LGT`/`LLE`/`LLT`, `LOG`, `LOG10`, `MAX`, `MIN`, `NINT`, `SINH`, `TAN`, and the `D…` variants. | provided |
| 23 | The **argument/result types and ranges** of the intrinsics are now specified (they were not in F66). | follows F77 |

## Items that inhibit portability *(Appendix A3)*

Even within FORTRAN 77, the standard flags things that vary between processors:

- **Collating sequence is not fully specified**, so character relational expressions can differ
  between processors. Use the `LGE`, `LGT`, `LLE`, `LLT` intrinsics for portable character
  comparison.
- **Character data, `H`/apostrophe edit descriptors, and comment lines** may contain characters one
  processor accepts and another rejects.
- **File names, unit numbers, and unit capabilities** are processor-dependent.

On forterp these resolve to the [target](D-forterp-extensions.md): the `NATIVE` and `PDP10` value
models differ in word size and character packing, which is where character comparisons and any
Hollerith arithmetic can diverge.

## See also

- The [FORTRAN 66 reference manual](../fortran66/README.md) — the older dialect in full.
- [Appendix D](D-forterp-extensions.md) — forterp's own extensions, divergences, and dialect knobs.

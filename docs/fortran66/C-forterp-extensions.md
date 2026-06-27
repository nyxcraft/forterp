# Appendix C. DEC FORTRAN-10 extensions & forterp divergences

The standard fixes a *floor*, not a ceiling ([Chapter 1](01-purpose-scope.md)). This appendix
collects everything forterp does **beyond or differently from** a strict reading of X3.9-1966: the
DEC FORTRAN-10 extensions you can opt into, and the handful of places forterp deliberately interprets
a program its own way for faithfulness to real FORTRAN-10 V5.

## The two axes

forterp separates the things X3.9-1966 leaves open into two independent choices:

- the **dialect** — the language the front end accepts. `F66` (the default) is strict ANSI;
  `FORTRAN10` adds the DEC superset below; `F77` is the later standard
  ([its own manual](../fortran77/README.md)).
- the **target** — the value model. `NATIVE` (the default) uses the host's 64-bit integers and
  floats; `PDP10` reproduces the genuine 36-bit DEC-10 representation.

The two are orthogonal — you can run strict `F66` on the faithful `PDP10` target, or the DEC dialect
on `NATIVE`. Selecting them is covered in the [Python API guide](../API.md) and [CLI.md](../CLI.md).

## DEC FORTRAN-10 extensions (the `FORTRAN10` dialect)

Strict `F66` **rejects** all of the following; the `FORTRAN10` dialect accepts them. They cannot
change the meaning of a program that stays within the standard, so they are pure additions.

**Literals and source form**
- octal constants outside `STOP`/`PAUSE`; **apostrophe** string constants `'ABCD'` (stored packed,
  Hollerith-style — there is still no `CHARACTER` type; that is `F77` only);
- `!` end-of-line comments and apostrophe-quoted text inside `FORMAT`;
- tab-format source; `;` to put several statements on one line.

**Statements**
- `IMPLICIT`, `PARAMETER`, `ENTRY`, `ENCODE`/`DECODE`;
- `PRINT`, unit-less `READ`, `ACCEPT`, `TYPE`; list-directed `*` I/O; random-access I/O;
- explicit array lower bounds `A(lo:hi)`; `*n` byte-size type specifiers (`INTEGER*4`);
  alternate-return `CALL` arguments.

**Operators**
- symbolic relationals `==` `#` `<` `>` `<=` `>=`; the extended logicals `.XOR.` `.EQV.` `.NEQV.`;
  `^` as an alternate power operator (`**` is the ANSI form);
- extra intrinsics such as the `LSH` shift, and additional `O`/`R`/`T`/`$` `FORMAT` descriptors.

**Relaxed F66 constraints**
- general integer expressions as array subscripts (lifting the §5.1.3.3 restriction —
  [Chapter 5](05-identification.md)) and as `DO` parameters;
- `COMPLEX` ↔ numeric assignment (beyond the Table 1 combinations).

## forterp's deliberate divergences

These hold on every dialect; they are choices of the interpreter, made to match how FORTRAN-10 V5
actually behaved. Most are in areas the standard leaves **undefined** — but a few can affect the
result of an otherwise-conforming program, so they are worth knowing.

### The value model (can affect results)

- **`REAL` is the host double on `NATIVE`.** There is no distinct single precision, so a program
  that depends on single-precision *rounding* sees double-precision results. The `PDP10` target
  restores the true 36-bit single / two-word double split.
- **`COMPLEX` and `DOUBLE PRECISION` both occupy two storage cells**, matching the count the
  standard assigns them *(§7.2.1.3.1.1: a double or complex datum is two storage units; an integer,
  real, or logical datum is one)*. So `COMMON`-block member offsets and `EQUIVALENCE` counting are
  word-accurate even when a block mixes these types with single-width members. The two cells differ
  in what they hold:
  - **`COMPLEX` splits faithfully** — the real part in the first cell, the imaginary in the second —
    so an overlay reads each part: `C=(3.0,4.0)` over `R(2)` gives `R(1)=3.0, R(2)=4.0`.
  - **`DOUBLE PRECISION` does not split on `NATIVE`**, where a double is a single 64-bit host float
    with no meaningful second word. The value lives in the first cell and the second is a permanent
    **zero shadow**: `D=1.5D0` with `EQUIVALENCE(D,R)` gives `R(1)=1.5, R(2)=0.0`. The *counting*
    is correct (a following `COMMON` member sits at the right word); only the second-word *content*
    is a placeholder. Faithful two-word `DOUBLE` splitting belongs to the `PDP10` target, where the
    two 36-bit words are physical.

### Non-fatal behavior in undefined areas

- **Arithmetic.** Integer/real divide-by-zero yields `0` and continues; library domain errors
  (`SQRT`/`ALOG` of a negative) print a warning and continue, as V5 did. On `NATIVE` these follow
  host IEEE rules (infinities, NaNs); on `PDP10` they follow FOROTS recovery. The divide-by-zero→`0`
  value is a stand-in, not a standard-specified result.
- **Out-of-bounds arrays.** An out-of-bounds **read** yields `0`; an out-of-bounds **write** to a
  local array is dropped. (Within a flat `COMMON` block an out-of-range index still lands on a
  neighbor word.) The standard leaves this undefined.
- **Illegal storage association is rejected**, not silently mis-laid: the three `EQUIVALENCE` shapes
  the standard *prohibits* (extending a `COMMON` block backward, tying two `COMMON` blocks together,
  or a self-contradictory group) raise a build-time error rather than picking an arbitrary layout.

### Formatted input by column (can affect results)

Under `F66`, every numeric/logical field is read **by column width**, with blanks counted as zeros.
The practical consequence: numeric input must be **right-justified**. A record shorter than an
explicit-width field is blank-extended, and those blanks become trailing zeros — `(I5)` on `42`
reads `42000`, not `42`; `(E10.3)` on `1.5E2` overflows the exponent. (Under `FORTRAN10`, a widthless
descriptor reads one free-form, space/comma/tab-delimited token instead; list-directed `READ(u,*)`
is whitespace-delimited on any dialect.)

### One-trip `DO`

The FORTRAN 66 `DO` is **one-trip** — its range always runs at least once
([Chapter 7](07-statements.md)) — and forterp reproduces that under `F66`/`FORTRAN10`. The `F77`
dialect uses the zero-trip test. This genuinely changes results, so it is dialect-selected.

## The `F66` dialect knobs

Most of the above is bundled into the dialect presets, but individual behaviors can be tuned. The
knobs most relevant to F66 (set on a `Dialect`; see the [API guide](../API.md) for the full list and
the F77 knob table):

| Knob | Effect |
|------|--------|
| `zero_trip_do` | use the F77 zero-trip `DO` test instead of one-trip |
| `recursion` | permit correct recursion (off by default — re-entry is otherwise rejected) |
| `bounds_check` | trap out-of-bounds array access instead of the non-fatal read→0 / dropped write |
| `unlimited_rank` | lift the array-rank cap (forterp already allows 7 vs the standard's 3) |
| `carriage_control` | treat the output unit as a printer (carriage control) vs a terminal |

For a side-by-side of how the *next* standard changed the language — the one-trip vs zero-trip `DO`,
the removal of Hollerith constants, tighter subscript and I/O rules — see
[Differences from FORTRAN 66](../fortran77/E-differences-f66.md) in the FORTRAN 77 manual.

For anything not covered here, **ANSI X3.9-1966** is authoritative for the base language and the
**DECsystem-10 FORTRAN-10 Language Manual (V5)** for the extensions.

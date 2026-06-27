# Appendix D — forterp extensions & strict gates

This manual describes standard FORTRAN 77. This appendix collects, in one place, everything
particular to **forterp** at the edges of the standard — what it accepts beyond F77, what it
enforces more strictly, and the knobs that change either. The guiding rule throughout: none of
these can change the result of a *conforming* program; they only decide what happens at the
boundaries a conforming program never reaches.

The governing principle is the standard's own *(§1.4)*: a processor may allow forms the standard
prohibits, **provided doing so cannot change a conforming program's meaning**.

## Committed extensions (on by default, won't reject your program)

These are deliberately supported beyond strict F77:

| Extension | Behavior |
|---|---|
| **Unchecked array access** | an out-of-bounds subscript traverses the `COMMON`/`EQUIVALENCE` storage sequence (the vintage over-/under-indexing tricks reach the neighbouring variable), reading 0 only past the whole block. Turn `bounds_check` on to make it an error. ([Ch 5](05-arrays-substrings.md)) |
| **Non-fatal arithmetic** | divide-by-zero, `0**0`, a negative base to a real power yield a value rather than trapping — IEEE on `NATIVE`, FORTRAN-10 recovery on `PDP10`. ([Ch 6](06-expressions.md)) |
| **`DOUBLE PRECISION` × `COMPLEX`** | accepted and computed as double-complex (the standard marks it "Prohibited"; gfortran also accepts). ([Ch 6](06-expressions.md)) |
| **Mixed character/numeric `COMMON`** | a common block may hold both kinds. ([Ch 8](08-specification.md)) |
| **Longer names** | a name over six characters is accepted (first six significant), not rejected. ([Ch 2](02-language-elements.md)) |
| **DEC column-1 comment markers** | `! $ / D` in column 1 mark comments, in addition to `C`/`*`. ([Ch 3](03-source-form.md)) |

## Enforced rules (hard error — forterp rejects what the standard forbids)

These are cases the standard prohibits where ignoring it would silently corrupt results, so
forterp reports an error instead of guessing:

| Rule | Why enforced |
|---|---|
| **Recursion** ([Ch 15](15-procedures.md)) | static locals can't represent it → would be silently wrong. *Opt in* with the `recursion` knob to permit it correctly. |
| **Complex ordering** `C1 .LT. C2` ([Ch 6](06-expressions.md)) | no ordering of complex values; a nonsense comparison. |
| **char⟷numeric `EQUIVALENCE`** ([Ch 8](08-specification.md)) | its only use is byte type-punning, which the value model can't do faithfully. |
| **Assignment to a `PARAMETER`** ([Ch 8](08-specification.md)) | a constant is not a variable; the assignment would otherwise vanish silently. |
| **Empty character constant `''`** ([Ch 4](04-data-types.md)) | meaningless in F77 (a Fortran-90 feature). |
| **More than one *unnamed* `BLOCK DATA`** ([Ch 16](16-block-data.md)) | the two would collide and lose one's initialization. |
| **Array rank > 7** ([Ch 5](05-arrays-substrings.md)) | the standard's seven-dimension maximum. *Lift* with `unlimited_rank`. |
| **Statement order** ([Ch 3](03-source-form.md)) | specifications must precede executables — enforced under the `F77` dialect (lenient under `F66`/`FORTRAN10`). |

## Tunable knobs

| Knob | Default | Effect when changed |
|---|---|---|
| `bounds_check` | off | array subscripts and substrings outside their bounds become hard errors (the `-fcheck=bounds` analog) |
| `recursion` | off | recursion is permitted and made correct (per-call local storage) |
| `unlimited_rank` | off | lifts the seven-dimension array cap |
| `carriage_control` | per dialect | force standard output to be a line printer (on) or a terminal (off); F77 defaults to terminal, F66/FORTRAN-10 to line printer ([Ch 13](13-format.md)) |

(These are engine flags; the dialect sets sensible defaults. See the
[Python API guide](../API.md#the-f77-dialect-knobs) for the full knob list and how to set them.)

## The one true divergence

Everything above is conformant. The **value model** is the single behavior that can change a
*conforming* program's result, and is therefore a genuine divergence, not an extension:

- On the default **`NATIVE`** target, `REAL` and `DOUBLE PRECISION` are both the host's 64-bit
  float — so double precision is not *more* precise than real (the standard requires it to be), and
  `DOUBLE PRECISION` occupies one value slot rather than two numeric units (observable only under
  partial storage association).
- The faithful **`PDP10`** target reproduces the genuine 36-bit single / two-word double model.

Choose the `PDP10` target when precise reproduction of the DEC-10 value model matters.

## Unspecified behavior (don't rely on it)

Where the standard makes something *undefined* and forterp does **not** commit to a particular
result, the result is unspecified and may change between versions:

- the value read from an **uninitialized** variable, and definition status generally
  ([Ch 17](17-association.md));
- an **out-of-range substring** with `bounds_check` off ([Ch 5](05-arrays-substrings.md));
- whether a **non-`SAVE` local** persists across calls ([Ch 8](08-specification.md)).

Write to the standard — initialize before use, `SAVE` what must persist, stay in bounds — and none
of this matters.

## Not in FORTRAN 77

The `F77` dialect is the 1978 standard — not a superset of later Fortran, and not the DEC
FORTRAN-10 extension set. These common additions are **not** part of F77 and are rejected (use the
`FORTRAN10` dialect for the DEC ones):

- **DEC / FORTRAN-10 extensions:** `DO WHILE … END DO`; the `.XOR.` operator and the symbolic
  relationals `==` `<` `>`; the `A(lo/hi)` array-bound form (under F77 a `/` in a bound is ordinary
  division, so `A(6/3:9)` is `A(2:9)`); octal `"…` literals; tab-format source; the trailing-`!`
  inline comment; `TYPE`/`ACCEPT`/`ENCODE`/`DECODE` and random-access I/O; free-form numeric input.
  All of these are available under `forterp.FORTRAN10`.
- **Fortran 90 and later:** free-form source, `IMPLICIT NONE`, the `CHARACTER(LEN=…)` declaration
  form, modules, dynamic allocation, derived types, array sections. Out of scope — F77 source is
  fixed-form ([Chapter 3](03-source-form.md)).

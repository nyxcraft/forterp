# 4. Data types & constants

FORTRAN 77 has six data types *(§4)*: **integer, real, double precision, complex, logical,** and
**character**. This chapter shows how to write a literal value (a *constant*) of each type, and
how a name takes on a type. Declaring variables of these types is [Chapter 8](08-specification.md);
this chapter is about the values themselves.

## How a name gets its type

A variable's type is fixed once, in one of three ways *(§4.1.2)*, in order of authority:

1. an explicit **type-statement** — `REAL X`, `CHARACTER*8 NAME`;
2. an **`IMPLICIT`** rule — `IMPLICIT INTEGER (A-H)`;
3. otherwise the **implicit default**: a name beginning with `I, J, K, L, M, N` is **integer**;
   any other initial letter is **real**.

```fortran
      REAL    MASS          ! explicit: MASS is real despite starting with M
      I = 3                 ! implicit: I is integer (I-N)
      X = 2.5               ! implicit: X is real
```

## Integer constants

A whole number, optionally signed: `0`, `42`, `-7`, `+100` *(§4.3)*. No decimal point, no
exponent. The magnitude is limited by the machine's integer size.

## Real constants

A single-precision floating-point number *(§4.4)*. It needs **either** a decimal point **or** an
exponent (or both). All of these are valid reals:

```fortran
      3.14          .5            5.            5E3
      5.0E3         -2.5          1.0E-10       +0.0
```

- `.5` (no integer part) and `5.` (no fractional part) are both fine; you cannot omit *both*.
- `E` introduces a base-10 exponent: `5E3` is 5000.0, `1.0E-10` is 10⁻¹⁰.

```fortran
      N(1) = 5.        ! 5.0
      N(2) = .5        ! 0.5
      N(3) = 5E3       ! 5000.0
```

## Double-precision constants

Like a real constant but with a **`D`** exponent instead of `E`, which makes it double precision
*(§4.5)*. Double precision carries more significant digits than real.

```fortran
      DOUBLE PRECISION PI
      PI = 3.141592653589793D0
      X  = 2.0D0           ! 2.0, double precision
```

A `D` exponent is what distinguishes `2.0D0` (double) from `2.0E0` (single).

## Complex constants

A pair `(real_part, imaginary_part)`, each part an optionally-signed real or integer constant
*(§4.6)*. It occupies two storage units (real then imaginary).

```fortran
      COMPLEX Z
      Z = (1.0, 2.0)       ! 1 + 2i
      Z = (3.0, -4.0)      ! 3 - 4i
```

## Logical constants

Exactly two: **`.TRUE.`** and **`.FALSE.`** *(§4.7)* — note the surrounding dots.

```fortran
      LOGICAL FLAG
      FLAG = .TRUE.
```

## Character constants

A string of characters between apostrophes *(§4.8)*. The string must be **non-empty**. Blanks
inside are significant (they are part of the value). To put an apostrophe *in* the string, write
two apostrophes:

```fortran
      'HELLO'              ! 5 characters
      'O''CLOCK'           ! 7 characters: O'CLOCK   (the '' is one apostrophe)
      'A B'                ! 3 characters: A, blank, B
```

The length of a character constant is the number of characters it represents (each `''` counts as
one). The full `CHARACTER` story — declaration, padding, concatenation, substrings — is in
[Chapter 5](05-arrays-substrings.md) and the [forterp F77 guide](../FORTRAN77.md).

## Signed zero

Zero is neither positive nor negative: `-0.0` has the same value as `0.0`, and they compare equal
*(§4.1.3)*.

```fortran
      X = -0.0
      IF (X .EQ. 0.0) ...      ! true
```

## Named constants

You can give a constant a name with the `PARAMETER` statement, then use the name wherever a
constant is allowed:

```fortran
      REAL PI
      PARAMETER (PI = 3.14159)
      AREA = PI * R * R
```

`PARAMETER` is a specification statement; its full rules (the constant expression, ordering,
typing) are in [Chapter 8](08-specification.md). A `PARAMETER` name is a *constant*, not a
variable — you cannot assign to it.

---

> **forterp notes.** Two points about the value model:
>
> - On forterp's default **`NATIVE`** target, both `REAL` and `DOUBLE PRECISION` are the host's
>   64-bit float, so double precision is not *more* precise than real (the standard requires it to
>   be). This only matters for a program that depends on the precision *difference*; the faithful
>   **`PDP10`** target reproduces the genuine 36-bit single / two-word double split. (This is the
>   one documented divergence that can affect a conforming program — see
>   [Appendix D](D-forterp-extensions.md).)
> - The standard requires a character constant to be **non-empty**; forterp rejects the empty
>   constant `''` on every dialect (a zero-length string is meaningless in F77 and is a Fortran-90
>   feature). A doubled apostrophe inside a string (`'O''CLOCK'`) is unaffected — that is an
>   embedded apostrophe, not an empty string.
>
> The **Hollerith** constant (`5HHELLO`) of older FORTRAN was replaced by `CHARACTER` in F77 and
> is not part of the F77 dialect; it remains available under `F66`/`FORTRAN10`.

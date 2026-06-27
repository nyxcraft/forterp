# 4. Data types

FORTRAN 66 defines **six data types** *(§4)*:

**integer, real, double precision, complex, logical,** and **Hollerith.**

Note what is *not* on that list: there is **no `CHARACTER` type**. In FORTRAN 66, text is handled
as **Hollerith** data — a string of characters carried inside a variable of one of the other types.
The `CHARACTER` type arrived with FORTRAN 77; if you want it, use the
[FORTRAN 77 reference manual](../fortran77/README.md). This chapter shows how to write a constant of
each type, and how a name acquires a type.

## How a name gets its type

A symbolic name representing a variable, array, or function has **one** data type throughout a
program unit *(§4.1)*. The type is fixed in one of these ways:

1. an explicit **type-statement** — `REAL`, `INTEGER`, `DOUBLE PRECISION`, `COMPLEX`, `LOGICAL`
   (Chapter [7](07-statements.md));
2. otherwise the **implicit default** *(§5.3)*: a name beginning with **`I, J, K, L, M, N`** is
   **integer**; a name beginning with any other letter is **real**.

```fortran
      REAL    MASS
C     -> explicit: MASS is real despite starting with M
      I = 3
C     -> implicit: I is integer (I-N)
      X = 2.5
C     -> implicit: X is real
```

There is **no** way to declare a name to be of Hollerith type *(§4.1)*. Hollerith data lives
"under the guise" of one of the other types — most often integer or real — and you simply have to
know that a given variable is holding characters rather than a number.

## The numeric types

### Integer

An integer datum is an **exact** representation of an integer value — positive, negative, or zero
*(§4.2.1)*. An integer constant is a string of digits, optionally signed, with no decimal point:

```fortran
      I = 0
      J = 42
      K = -7
```

### Real

A real datum is a **processor approximation** to a real number *(§4.2.2)*. A real constant has a
decimal point, and may carry a decimal exponent written with `E`:

```fortran
      A = 3.14
      B = -0.5
      C = 6.022E23
C     -> 6.022 x 10**23
```

### Double precision

A double precision datum is an approximation whose precision is **greater than** that of real
*(§4.2.3)*. A double precision constant uses a `D` exponent in place of `E`:

```fortran
      DOUBLE PRECISION D
      D = 1.5D0
      D = 3.141592653589793D0
```

### Complex

A complex datum is an **ordered pair of reals** — the real part and the imaginary part *(§4.2.4)*.
A complex constant is that pair, parenthesized and comma-separated:

```fortran
      COMPLEX C
      C = (1.0, 2.0)
C     -> 1 + 2i; arithmetic follows the usual complex rules:
C     -> (1.0,2.0) + (3.0,4.0) = (4.0,6.0)
```

## The logical type

A logical datum is one of the two truth values **true** or **false** *(§4.2.5)*. The constants are
written `.TRUE.` and `.FALSE.`:

```fortran
      LOGICAL FLAG
      FLAG = .TRUE.
```

## The Hollerith type

A Hollerith datum is a **string of characters** *(§4.2.6)*; any character the processor can
represent is allowed, and the **blank is significant**. A Hollerith constant is written as a count,
the letter `H`, then exactly that many characters:

```fortran
      INTEGER WORD
      WORD = 4HABCD
C     -> the four characters A B C D, packed into WORD
```

Because Hollerith has no type of its own, you store it in a variable of another type (here an
integer) and treat that variable as a holder of characters. Hollerith is most often seen supplying
literal text to a `FORMAT` statement and in `DATA` statements — see
[Chapter 7](07-statements.md).

> **forterp notes.**
>
> - **No `CHARACTER` type, and no apostrophe strings, under `F66`.** A character constant written
>   with apostrophes (`'ABCD'`) is a *FORTRAN-10 extension*; under strict `F66` it is rejected, and
>   you must use Hollerith. The three dialects line up like this:
>
>   | | `F66` | `FORTRAN10` | `F77` |
>   |---|---|---|---|
>   | Hollerith `4HABCD` | yes | yes | yes |
>   | apostrophe `'ABCD'` | — | yes (stored packed, Hollerith-style) | yes (true `CHARACTER`) |
>   | `CHARACTER` type | — | — | yes |
>
> - **Precision and the value model.** The standard fixes only that double precision is *more*
>   precise than real, never by how much. On forterp's default **`NATIVE`** target, `REAL` and
>   `DOUBLE PRECISION` are both the host's 64-bit float, so double precision is not actually more
>   precise; the faithful **`PDP10`** target reproduces the genuine 36-bit single / two-word double
>   split. This only matters to a program that depends on the precision *difference* — see
>   [Appendix C](C-forterp-extensions.md).
> - **How Hollerith is packed** also depends on the target: `NATIVE` packs characters into a 64-bit
>   word, `PDP10` into a 36-bit word, five 7-bit ASCII characters per word, exactly as DEC-10 did.

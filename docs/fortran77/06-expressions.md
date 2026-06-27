# 6. Expressions & operators

An **expression** computes a value from constants, variables, function references, and operators.
FORTRAN 77 has four families of expression — arithmetic, character, relational, and logical — with
a clear precedence order between and within them *(§6)*.

## Arithmetic expressions

The arithmetic operators, from highest precedence to lowest *(§6.1)*:

| Operator | Meaning | Precedence |
|---|---|---|
| `**` | exponentiation | highest |
| `*` `/` | multiply, divide | middle |
| `+` `-` | add, subtract (and unary `+`/`-`) | lowest |

```fortran
      A + B * C        ! = A + (B*C)      -- * before +
      -A ** 2          ! = -(A**2)        -- ** before unary minus
      2 ** 3 ** 2      ! = 2**(3**2) = 512  -- ** is RIGHT-associative
```

Two points trip people up:

- **`**` is right-associative**, so `2**3**2` is `2**(3**2)` = `2**9` = 512, not `(2**3)**2` = 64.
- **Unary minus binds looser than `**`**, so `-3**2` is `-(3**2)` = −9, not `(-3)**2` = 9.

You may not write two operators adjacently — `A**-B` is illegal; parenthesize it as `A**(-B)`.

### Integer division truncates toward zero

When both operands are integers, `/` gives an **integer** result, truncated toward zero (the
fractional part is discarded) *(§6.1.5)*:

```fortran
      7 / 2            ! = 3   (not 3.5)
      (-8) / 3         ! = -2  (toward zero, not -3)
```

A negative integer power follows from this: `2**(-3)` is `1/(2**3)` = `1/8`, which truncates to
**0**. (So `2**(-1)` is 0 — that is the defined result, not a bug.)

### Mixed types are converted

When an operator combines two different numeric types, the value of the "lower" type is converted
up before the operation, and the result is the "higher" type *(§6.1.4)*: integer → real → double,
and complex with real/double. So `2 + 3.0` is real `5.0`; `1.0D0 * 2` is double. The one exception
is a real/double/complex base raised to an **integer** power — the exponent stays an integer
(`X**2`, not `X**2.0`), which is both faster and avoids a domain error on a negative base.

## Character expressions

The only character operator is **`//`**, concatenation *(§6.2)*:

```fortran
      CHARACTER*6 R
      R = 'AB' // 'CD'         ! R = 'ABCD  '  (then padded to R's length 6)
```

## Relational expressions

A relational operator compares two values and yields a **logical** result *(§6.3)*:

| Operator | Meaning |
|---|---|
| `.LT.` | less than |
| `.LE.` | less than or equal |
| `.EQ.` | equal |
| `.NE.` | not equal |
| `.GT.` | greater than |
| `.GE.` | greater than or equal |

You may compare two arithmetic values *or* two character values (not one of each). Character
comparison pads the shorter operand with blanks on the right, then compares left to right using the
collating sequence ([Appendix C](C-precedence-ascii.md)), so `'HI'` and `'HI   '` compare
**equal** *(§6.3.5)*. A **complex** value may be compared only with `.EQ.` / `.NE.` — there is no
ordering of complex numbers.

```fortran
      IF (N .GE. 0) ...
      IF (NAME .EQ. 'DONE') ...
```

## Logical expressions

The logical operators, highest to lowest precedence *(§6.4)*:

| Operator | Meaning | Precedence |
|---|---|---|
| `.NOT.` | negation | highest |
| `.AND.` | conjunction | |
| `.OR.` | disjunction | |
| `.EQV.` `.NEQV.` | equivalence / non-equivalence | lowest |

```fortran
      .NOT. A .AND. B          ! = (.NOT. A) .AND. B
      A .OR. B .AND. C         ! = A .OR. (B .AND. C)   -- AND before OR
```

## The whole precedence ladder

Across families, the order is **arithmetic > character > relational > logical** *(§6.5)*. That is
why a comparison like this needs no parentheses:

```fortran
      IF (2 + 3 .GT. 4) ...        ! arithmetic first: (2+3) .GT. 4  -> .TRUE.
      IF ('AB' // 'C' .EQ. 'ABC') ...   ! concat first: ('AB'//'C') .EQ. 'ABC'  -> .TRUE.
```

When in doubt, parenthesize — and note that a parenthesized subexpression is evaluated as a unit:
the compiler will not regroup `A*(B*C)` into `(A*B)*C` *(§6.6)*.

---

> **forterp notes.** A few behaviors at the edges of the standard:
> - **Complex ordering** (`C1 .LT. C2`) is a hard error on every dialect — complex values have no
>   order, so it is a nonsense comparison (gfortran rejects it too).
> - **`DOUBLE PRECISION` combined with `COMPLEX`** in arithmetic is "Prohibited" by the standard
>   (F77 had no double-complex type), but forterp accepts it and computes the double-complex result
>   — identical to gfortran in every mode. A useful extension; a conforming program never forms it.
> - **Undefined arithmetic** (divide-by-zero, `0**0`, a negative base to a real power) does not
>   trap — it yields a value. On the `NATIVE` target that value is IEEE (`Inf`/`NaN`, matching
>   gfortran); on `PDP10` it is the FORTRAN-10 recovery value. The operation is undefined, so any
>   result conforms; a conforming program never reaches it. (A *nonzero* base to a negative integer
>   power, e.g. `2**(-1)` = 0, is **defined** and computed correctly — not in this category.)

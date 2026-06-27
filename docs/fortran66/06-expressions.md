# 6. Expressions

An **expression** combines data with operators to produce a value *(§6)*. FORTRAN 66 has three
kinds: **arithmetic** (a numeric value), **relational** (a truth value from comparing two numbers),
and **logical** (a truth value combined with logical operators). This chapter gives their formation
and evaluation rules.

## Arithmetic expressions

An arithmetic expression produces a value of type integer, real, double precision, or complex
*(§6.1)*. The arithmetic operators are:

| Operator | Meaning |
|----------|---------|
| `+` | addition (and unary plus) |
| `-` | subtraction (and unary minus) |
| `*` | multiplication |
| `/` | division |
| `**` | exponentiation |

```fortran
      X = A + B*C - D/E
C     -> * and / bind tighter than + and -
```

### Exponentiation binds right and tightest

`**` has higher precedence than `*` and `/`, and a chain of exponentiations groups **right to
left**:

```fortran
      COMMON /O/ N(1)
      N(1) = 2**3**2
C     -> 2**(3**2) = 2**9 = 512, not (2**3)**2 = 64
```

The standard defines `**` for only a few operand combinations *(§6.1)*:

- a primary of **any** type may be raised to an **integer** primary — the result has the base's
  type. This is why `(-2.0)**3` is the well-defined `-8.0`;
- a **real or double precision** primary may be raised to a **real or double precision** primary —
  the result is real if both are real, otherwise double precision.

No other combinations are defined. In particular a **negative** value may not be raised to a real or
double precision exponent (it would need a complex result), and a zero may not be raised to a zero
exponent *(§6.4)*.

### Mixed-mode arithmetic

In strict FORTRAN 66 the operands of an arithmetic operator must generally be of the **same type**;
the only cross-type combinations the standard admits are a **real** element with a **double
precision** element (giving double precision) or with a **complex** element (giving complex)
*(§6.1)*. Notably, integer and real were *not* meant to be mixed in one expression.

```fortran
      DOUBLE PRECISION D, R
      D = 1.0D0
      R = D + 0.5
C     -> real 0.5 combined with double precision -> double precision
```

## Relational expressions

A relational expression compares two arithmetic expressions and yields **true** or **false**
*(§6.2)*. The relational operators are:

| Operator | Meaning | Operator | Meaning |
|----------|---------|----------|---------|
| `.LT.` | less than | `.GE.` | greater than or equal |
| `.LE.` | less than or equal | `.GT.` | greater than |
| `.EQ.` | equal | `.NE.` | not equal |

The standard allows the two operands to be real/double precision, or both integer; a real operand
compared with a double precision one is handled as if a double precision zero were added to the real
*(§6.2)*.

```fortran
      LOGICAL BIG
      BIG = X .GT. 100.0
```

## Logical expressions

A logical expression is built from logical values and the logical operators *(§6.3)*:

| Operator | Meaning |
|----------|---------|
| `.NOT.` | logical negation |
| `.AND.` | logical conjunction |
| `.OR.` | logical disjunction |

Their precedence, highest first, is **`.NOT.` then `.AND.` then `.OR.`**:

```fortran
      COMMON /O/ L(1)
      LOGICAL L
      L(1) = .FALSE. .OR. .TRUE. .AND. .FALSE.
C     -> .FALSE. .OR. (.TRUE. .AND. .FALSE.) = .FALSE.
```

Relational expressions may appear as operands of logical operators (arithmetic binds tightest, then
relational, then logical), so `A+B .GT. C .AND. FLAG` means `((A+B) .GT. C) .AND. FLAG`.

## Evaluation rules

A few rules govern *how* an expression is evaluated *(§6.4)*:

- Only as much of an expression need be evaluated as is required to establish its value.
- A processor may reorder operations using the associative and commutative laws — **except** that
  the integrity of parentheses is always preserved. So `(A+B)+C` and `A+(B+C)` may differ, and you
  use parentheses when order matters.
- The value of an **integer** factor or term is the nearest integer whose magnitude does not exceed
  the true mathematical value — i.e. **division truncates toward zero**. The associative and
  commutative laws do *not* apply to integer terms containing division, which proceed left to right.

```fortran
      COMMON /O/ N(2)
      N(1) = 7/2
C     -> 3 (truncated toward zero, not rounded)
      N(2) = (-7)/2
C     -> -3
```

> **forterp notes.**
>
> - forterp **permits mixed integer/real arithmetic and relationals** on every dialect — `2.0 + 3`
>   evaluates to `5.0`, and `2 .LT. 3.0` is true — converting to the wider type as later FORTRANs
>   do. Strict FORTRAN 66 did not sanction this mixing, but allowing it cannot change the meaning of
>   a program that avoids it, so forterp accepts it as a convenience.
> - Exponentiation is right-associative (`2**3**2` is `512`) and integer division truncates toward
>   zero, matching the standard.
> - On the default **`NATIVE`** target, overflow and operations like `0.0/0.0` follow host IEEE
>   rules (infinities and NaNs); the faithful **`PDP10`** target reproduces the FOROTS recovery
>   behavior instead. See [Appendix C](C-forterp-extensions.md).

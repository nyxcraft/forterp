# 8. Procedures & subprograms

A **procedure** is a reusable piece of computation. FORTRAN 66 has four kinds *(§8)*: **statement
functions**, **intrinsic functions**, **external functions**, and **external subroutines**. The
first three are *functions* — they return a value into an expression; the last is invoked by `CALL`.
External functions and subroutines, plus the `BLOCK DATA` unit, are written as separate
**subprograms**.

## Statement functions

A **statement function** is a one-line function defined inside the program unit that uses it
*(§8.1)*. Its definition looks like an assignment: `f(a1,…,an) = e`. The arguments are *dummy*
names; the expression `e` may use those dummies, constants, variables, intrinsic functions,
previously defined statement functions, and external functions.

```fortran
      COMMON /O/ R(1)
      REAL R
      SQ(X) = X*X
      R(1) = SQ(3.0) + SQ(4.0)
C     -> 9.0 + 16.0 = 25.0
```

Statement function definitions must come **after** the specification statements and **before** the
first executable statement *(§8.1.1)*.

## Intrinsic functions

The **intrinsic functions** are built in and listed in the standard's **Table 3** *(§8.2)* — the
full table is reproduced in [Appendix A](A-intrinsics.md). They cover absolute value, truncation,
remaindering, choosing the largest/smallest, type conversion, and the complex-number helpers:

```fortran
      COMMON /O/ R(5)
      REAL R
      R(1) = ABS(-3.0)
C     -> 3.0
      R(2) = MOD(7, 3)
C     -> 1   (remainder)
      R(3) = MAX0(2, 9, 5)
C     -> 9
      R(4) = FLOAT(4)
C     -> 4.0  (integer -> real)
      R(5) = AINT(3.9)
C     -> 3.0  (truncate, result still real)
```

Each intrinsic has a fixed argument type and result type (Table 3); pick the spelling that matches
your data — `ABS` for real, `IABS` for integer, `DABS` for double precision.

## External functions

An **external function** is a separate subprogram headed by a `FUNCTION` statement *(§8.3)*:

```fortran
      FUNCTION CUBE(X)
      CUBE = X*X*X
      RETURN
      END
```

Inside the subprogram, the function name (`CUBE`) is used as a variable; its value at the `RETURN`
becomes the function's result *(§8.3.1)*. A function subprogram must contain at least one `RETURN`.
You reference it like any function:

```fortran
      COMMON /O/ R(1)
      REAL R
      R(1) = CUBE(2.0)
C     -> 8.0
```

The optional type prefix on the `FUNCTION` statement (`INTEGER FUNCTION …`, `DOUBLE PRECISION
FUNCTION …`) sets the result type explicitly; otherwise it follows the implicit naming rule.

### Basic external functions

The standard also requires a set of **basic external functions** — the mathematical library — listed
in **Table 4** *(§8.3.3)*: `EXP`, `ALOG`, `ALOG10`, `SIN`, `COS`, `TANH`, `SQRT`, `ATAN`, `ATAN2`,
and their double precision (`D…`) and complex (`C…`) variants. They are referenced exactly like any
external function:

```fortran
      COMMON /O/ R(2)
      REAL R
      R(1) = SQRT(16.0)
C     -> 4.0
      R(2) = EXP(0.0)
C     -> 1.0
```

## External subroutines

An **external subroutine** is a subprogram headed by a `SUBROUTINE` statement and invoked by `CALL`
*(§8.4)*. Unlike a function, it returns nothing directly; it communicates through its arguments and
through common:

```fortran
      SUBROUTINE DBL(A, B)
      B = 2.0*A
      RETURN
      END
```

```fortran
      COMMON /O/ R(1)
      REAL R
      CALL DBL(5.0, Y)
      R(1) = Y
C     -> 10.0
```

A subroutine must contain at least one `RETURN`. A Hollerith constant may be passed as an actual
argument even though it has no type of its own — the one exception to the rule that actual and dummy
argument types must agree *(§8.4.2)*.

## Block data subprograms

A **block data subprogram** exists solely to give initial values to variables in **labeled common**
*(§8.5)*. It begins with `BLOCK DATA`, contains only `DIMENSION`, `COMMON`, `EQUIVALENCE`, type, and
`DATA` statements, and has no executable statements:

```fortran
      BLOCK DATA
      COMMON /C/ A, B
      DATA A, B /1.5, 2.5/
      END
```

Now `A` and `B` in common block `/C/` start out as `1.5` and `2.5` everywhere they appear. This is
the *only* way to initialize labeled common *(§7.2.2)*.

> **forterp notes.**
>
> - forterp supplies the full Table 3 intrinsic set and Table 4 mathematical library, and adds a
>   number of **DEC FORTRAN-10 intrinsics** beyond the standard (collected in
>   [Appendix C](C-forterp-extensions.md)). The standard set is the portable one.
> - **Recursion is prohibited** by the standard: a procedure subprogram may not be referenced a
>   second time before a `RETURN` from the first has intervened *(§10.2.1)* — so a subprogram must
>   not, directly or indirectly, reference itself. forterp rejects re-entry by default rather than
>   give a silently wrong answer; declare a procedure with the F90 `RECURSIVE` keyword (or flip the
>   `recursion` knob globally) to permit correct recursion. See [Appendix C](C-forterp-extensions.md).
> - An external function or subroutine may live in a **separate source file**; forterp links the
>   units of a program together (see [CLI.md](../CLI.md)).

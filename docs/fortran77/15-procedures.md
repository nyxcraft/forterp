# 15. Functions & subroutines

Procedures let you name a piece of computation and reuse it. FORTRAN 77 has four kinds *(§15)*:
**intrinsic functions** (built in), **statement functions** (one-line, local), **external
functions** (full subprograms that return a value), and **subroutines** (full subprograms invoked
with `CALL`). This is the largest chapter; take it a section at a time.

## Intrinsic functions

The library built into the language — `SQRT`, `SIN`, `ABS`, `MOD`, `MAX`, `LEN`, and dozens more.
You just use them:

```fortran
      Y = SQRT(X)
      M = MAX(A, B, C)
      L = LEN(NAME)
```

Most are **generic**: `ABS` works on integer, real, double, or complex and returns the matching
type. The complete list, with argument and result types, is [Appendix A](A-intrinsics.md). To pass
an intrinsic *as an argument* to another procedure, name it in an `INTRINSIC` statement
([Chapter 8](08-specification.md)).

## Statement functions

A **statement function** is a one-line function defined inside a program unit, after the
specifications and before the executables *(§15.4)*. It is local to that unit and handy for a short
formula used several times:

```fortran
      REAL SQ
      SQ(X) = X * X                 ! definition (a specification-area statement)
      ...
      AREA = SQ(SIDE)               ! use it like any function
```

The dummy arguments (`X`) are local to the definition; the body is a single expression that may
use other variables of the unit and earlier statement functions.

## External functions

An **external function** is a complete subprogram that computes and returns a value
*(§15.5)*:

```fortran
      INTEGER FUNCTION ISQ (K)
      ISQ = K * K                   ! assign the result to the function's own name
      RETURN
      END
```

- The header is `[type] FUNCTION name (dummies)`. The type may be on the header (above) or
  declared separately in the function.
- Inside the function, the **function name acts as a variable** — you assign the result to it
  before returning.
- Call it by using its name in an expression: `N = ISQ(6)`.

A `CHARACTER` function declares its result length; `CHARACTER*(*)` lets the caller's context fix it:

```fortran
      CHARACTER*4 FUNCTION UP (S)
      CHARACTER*(*) S
      UP = S
      RETURN
      END
```

## Subroutines and CALL

A **subroutine** is a subprogram invoked with `CALL`; it returns nothing directly but acts through
its arguments and `COMMON` *(§15.6)*:

```fortran
      SUBROUTINE ADD1 (M)
      M = M + 1                     ! changes the caller's variable (see arguments)
      RETURN
      END

C     in the caller:
      CALL ADD1 (COUNT)             ! COUNT is incremented
```

## Arguments

Arguments connect a caller's data to a procedure's **dummy arguments**, by position *(§15.9)*:

- Association is effectively **by reference** — the dummy names the actual argument's storage, so
  assigning to a dummy changes the caller's variable (that is how `ADD1` above works, and how a
  subroutine "returns" results).
- The number of arguments must match, and the types must agree (apart from a subroutine name or an
  alternate-return specifier).
- You may pass a constant or expression for an *input* argument — but then the procedure must not
  try to redefine it.
- A `CHARACTER` dummy may be shorter than the actual; `CHARACTER*(*)` takes the actual's length.
- An array dummy may be **adjustable** or **assumed-size** ([Chapter 5](05-arrays-substrings.md)).
- A **dummy procedure** lets you pass a function or subroutine as an argument (declare the actual
  `EXTERNAL` or `INTRINSIC`, [Chapter 8](08-specification.md)):

  ```fortran
        EXTERNAL MYF
        CALL INTEGRATE (MYF, 0.0, 1.0)
  ```

## RETURN

`RETURN` returns control to the caller *(§15.8)*. Reaching `END` does the same. An **alternate
return** lets a subroutine choose among labels the caller supplies:

```fortran
      CALL PARSE (LINE, *900)       ! *900 is an alternate-return label
      ...
  900 CONTINUE                      ! reached if PARSE does RETURN 1

      SUBROUTINE PARSE (S, *)       ! * is the alternate-return dummy
      IF (bad) RETURN 1             ! returns to the caller's first * label
      RETURN
      END
```

## ENTRY

`ENTRY` defines additional entry points in a function or subroutine, sharing its body and locals
*(§15.7)*:

```fortran
      FUNCTION TWICE (K)
      TWICE = K * 2
      RETURN
      ENTRY THRICE (K)              ! a second way in, same unit
      THRICE = K * 3
      RETURN
      END
```

`TWICE(5)` is 10, `THRICE(5)` is 15.

## A note on recursion

Standard FORTRAN 77 **prohibits recursion** — a subprogram must not call itself, directly or
indirectly *(§15.5.2)*. This is rooted in the static-storage model of the era (a single set of
local variables per procedure, with nowhere to keep a second activation's values). If you are
coming from a modern language, this is a real restriction: there is no recursive `FACTORIAL` in
conforming F77.

---

> **forterp notes.**
> - **Recursion is rejected** by default on every dialect (a re-entry of a still-active procedure
>   is a hard error) — forterp's static locals can't represent it, so it errors rather than
>   returning a silently wrong answer. The opt-in **`recursion`** dialect knob *enables* it and
>   makes it correct (each call gets its own locals); see [Appendix D](D-forterp-extensions.md).
> - **`EXTERNAL` is required** to pass a procedure as an argument (a bare name is read as a
>   variable). All four procedure kinds, alternate return, `ENTRY`, `CHARACTER*(*)` results, and
>   adjustable/assumed-size array dummies are supported.
> - All **85** standard intrinsic functions are present with their specified semantics
>   ([Appendix A](A-intrinsics.md)).

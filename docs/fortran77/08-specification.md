# 8. Specification statements

Specification statements describe your data before the program runs: what type each name is, how
arrays are shaped, what storage is shared, and what is constant. They are nonexecutable and come
before the executable statements *(§8)*.

## Type statements

A type statement declares the type (and, for `CHARACTER`, the length) of names:

```fortran
      INTEGER          I, J, COUNT
      REAL             X, Y, V(10)
      DOUBLE PRECISION D
      COMPLEX          Z
      LOGICAL          FLAG
      CHARACTER*8      NAME
```

A type statement may also give an array its shape (`V(10)` above), so you often don't need a
separate `DIMENSION`. For `CHARACTER`, the length is part of the type:

```fortran
      CHARACTER         C            ! length 1 (the default)
      CHARACTER*8       NAME         ! length 8
      CHARACTER         TAG*3, MSG*40   ! per-name *len overrides the statement length
      CHARACTER*(*)     ARG          ! assumed length: a dummy takes the actual's length
      CHARACTER*(LMAX)  BUF          ! a parenthesised integer-constant expression
```

## IMPLICIT

`IMPLICIT` changes the default type for whole ranges of initial letters *(§8.5)*. It must precede
the other specification statements (a `PARAMETER` may come before it).

```fortran
      IMPLICIT INTEGER (A-H, O-Z)    ! everything not I-N is integer too
      IMPLICIT REAL*8 (D)            ! names starting with D are double precision
      IMPLICIT NONE                  ! [F90] -- NOT part of F77
```

Without any `IMPLICIT`, the built-in default applies: `I`–`N` ⇒ integer, else real
([Chapter 4](04-data-types.md)). An explicit type statement always overrides `IMPLICIT`.

## DIMENSION

`DIMENSION` declares array shapes when you don't want to put them on the type statement
([Chapter 5](05-arrays-substrings.md)):

```fortran
      DIMENSION A(10), M(3,4), T(0:5)
```

## COMMON — sharing storage across program units

A `COMMON` block is a named region of storage that several program units can all see. Each unit
lists the variables it maps onto the block, in order; the mapping is by **position**, not by name
*(§8.3)*.

```fortran
      PROGRAM MAIN
      COMMON /STATE/ COUNT, TOTAL
      COUNT = 0
      CALL TICK
      ...
      END

      SUBROUTINE TICK
      COMMON /STATE/ COUNT, TOTAL     ! same block: COUNT and TOTAL are shared
      COUNT = COUNT + 1
      RETURN
      END
```

- A **named** block is `/name/ list`. A **blank** (unnamed) common is `// list` or just `COMMON
  list`.
- Different units may use different variable *names* for the same block — only the position and
  type/size matter. Lay them out identically to avoid confusion.
- A `BLOCK DATA` subprogram is the only place a named common block may be given initial values
  ([Chapter 16](16-block-data.md)).

## EQUIVALENCE — two names, one storage

`EQUIVALENCE` makes two or more names in the *same* unit refer to the same storage *(§8.2)*. It is
used to overlay data (e.g. view an array two ways) or to save memory.

```fortran
      REAL    A(4)
      INTEGER B(4)
      EQUIVALENCE (A, B)        ! A and B share the same 4 storage units
```

Equivalencing is by storage, with no type conversion: reading `A(1)` and `B(1)` interprets the
same bits as a real and as an integer respectively. It can also extend a common block (forward
only). Character entities may be equivalenced only with other character entities.

## PARAMETER — named constants

`PARAMETER` gives a name to a constant value computed from a constant expression *(§8.6)*. The
name is a *constant*, usable anywhere a literal is — and not assignable.

```fortran
      INTEGER   MAX
      REAL      PI
      PARAMETER (MAX = 100, PI = 3.14159)
      PARAMETER (TWOPI = 2.0 * PI)        ! constant expressions are allowed
      REAL  BUF(MAX)
```

Give a name a non-default type *before* its `PARAMETER` (the `INTEGER MAX` above). A `PARAMETER`
name may appear in a `DATA` statement and in expressions, but not inside a `FORMAT`.

## EXTERNAL and INTRINSIC

To pass a procedure *as an argument*, you must declare its name so the compiler knows it is a
procedure and not a variable *(§8.7–8.8)*:

- **`EXTERNAL`** names your own (or a library) external procedures.
- **`INTRINSIC`** names a built-in function you intend to pass on.

```fortran
      EXTERNAL  MYFUNC
      INTRINSIC SIN
      CALL INTEGRATE (MYFUNC, 0.0, 1.0)
      CALL TABULATE  (SIN,    0.0, 3.14)
```

An `EXTERNAL` name also overrides a like-named intrinsic, letting you supply your own `SIN`, say.

## SAVE

`SAVE` asks that a local variable keep its value between calls to a subprogram (without it, a
non-`SAVE` local is undefined after `RETURN`) *(§8.9)*:

```fortran
      SUBROUTINE COUNTER (SLOT)
      SAVE NCALLS
      NCALLS = NCALLS + 1            ! retained across calls because of SAVE
      ...
      END
```

`SAVE name` saves one entity, `SAVE /block/` a whole common block, and a bare `SAVE` saves
everything in the unit. In a main program `SAVE` has no effect (the main program is never exited
and re-entered).

---

> **forterp notes.**
> - **EXTERNAL is required** to pass a procedure as an argument (a bare undeclared name is taken as
>   a variable, and the call fails when the dummy is used) — exactly as the standard mandates.
> - **EQUIVALENCE** detects a contradictory grouping, and rejects mixing a `CHARACTER` entity with
>   a non-character one (its only use is byte type-punning, which forterp's value model can't do
>   faithfully). A **mixed character/numeric `COMMON` block** is, by contrast, accepted (harmless).
> - **`PARAMETER`:** assigning to a `PARAMETER` name is a hard error (it is a constant, not a
>   variable) rather than a silently-dropped assignment.
> - **`SAVE`:** use it where you need a local retained across calls; non-`SAVE` retention is
>   unspecified (don't rely on it). See [Appendix D](D-forterp-extensions.md).

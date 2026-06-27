# 5. Arrays & substrings

An **array** is a named block of elements of one type, addressed by one or more integer
subscripts. A **substring** is a contiguous slice of a single character value. Both are built from
the data types of [Chapter 4](04-data-types.md); this chapter is how you declare and index them.

## Declaring an array

You give an array its shape with an **array declarator** — `name(bounds)` — in a `DIMENSION`
statement, a type statement, or a `COMMON` statement *(§5.1)*. These three are equivalent ways to
declare a 10-element real array `V`:

```fortran
      DIMENSION V(10)
      REAL V(10)
      REAL V
      DIMENSION V(10)
```

Each **dimension** is written `[lower:]upper`. If you omit the lower bound it defaults to 1, so
`V(10)` runs `V(1)…V(10)`. You may give an explicit lower bound, including zero or negative:

```fortran
      REAL    A(10)            ! A(1) .. A(10)
      REAL    B(0:9)           ! B(0) .. B(9)   -- ten elements, 0-based
      INTEGER C(-3:3)          ! C(-3) .. C(3)  -- seven elements
```

An array may have **1 to 7 dimensions** *(§5.1)*. The bounds are constants (or, for a dummy
argument, expressions — see *adjustable arrays* below):

```fortran
      REAL M(3,4)              ! a 3x4 matrix: M(1,1) .. M(3,4)
      REAL T(2,2,2)            ! a 3-dimensional array
```

## Subscripts

An element is selected with one integer subscript expression per dimension *(§5.4)*. Subscripts
may be any integer expression, not just constants:

```fortran
      M(2,3)     = 1.0
      M(I, J+1)  = M(I, J) * 2.0
```

The standard requires each subscript to lie within its declared bounds. (What happens if it does
not is in the forterp notes below.)

## How arrays are laid out: column-major

Array elements occupy a single storage sequence, and FORTRAN stores them in **column-major**
order — the **first subscript varies fastest** *(§5.2.4)*. For `A(2,2)` the elements sit in
memory in this order:

```
   A(1,1)  A(2,1)  A(1,2)  A(2,2)
```

You can see it by overlaying a 1-D array on a 2-D one with `EQUIVALENCE`
([Chapter 8](08-specification.md)):

```fortran
      DIMENSION A(2,2), B(4)
      EQUIVALENCE (A, B)
      DO 1 I = 1, 4
    1   B(I) = I
C     now A(1,1)=1  A(2,1)=2  A(1,2)=3  A(2,2)=4
```

This matters whenever array storage is shared or passed as a whole: the order is columns-first,
the opposite of C's row-major. It is also why a tight loop should make the **first** subscript the
innermost one, to walk memory sequentially.

## Whole-array use

An unsubscripted array name stands for the whole array in a few contexts — in `COMMON`, `DATA`,
`EQUIVALENCE`, an I/O list, or as an actual argument:

```fortran
      REAL V(100)
      WRITE (6, *) V           ! writes all 100 elements (in storage order)
      CALL NORMALIZE(V)        ! passes the whole array
```

## Dummy arrays: assumed-size and adjustable

When an array is a **dummy argument** of a subprogram, its bounds may depend on the call rather
than being fixed *(§5.1.2)*:

- **Adjustable array** — a bound is an integer variable (itself a dummy or in `COMMON`), so the
  array's shape is whatever the caller's data requires:

  ```fortran
        SUBROUTINE SCALE (A, N)
        REAL A(N)              ! adjustable: N comes from the caller
        DO 1 I = 1, N
    1     A(I) = A(I) * 2.0
        END
  ```

- **Assumed-size array** — the last upper bound is `*`, meaning "however large the actual is."
  You can index it but cannot ask its total size:

  ```fortran
        SUBROUTINE SHOW (A)
        REAL A(*)              ! assumed size
        WRITE (6, *) A(1), A(2)
        END
  ```

## Character substrings

A **substring** selects a contiguous run of characters from a character variable or array element,
written `name(e1:e2)` — 1-based and inclusive *(§5.7)*. It can be read as a value **or** assigned
to as a target:

```fortran
      CHARACTER*5 R
      R = 'ABCDE'
      R(2:4) = 'XY'        ! R = 'AXY E'  (RHS fitted to the 3-char slice; rest untouched)
      C2 = R(2:3)          ! reads 'XY'
```

Either bound may be omitted: `R(:3)` is `R(1:3)`, `R(3:)` is `R(3:LEN(R))`, and `R(:)` is the
whole string. The substring of an array element is `W(K)(1:2)` — element `K` of array `W`, then
characters 1–2 of it. The valid range is `1 ≤ e1 ≤ e2 ≤ len`.

---

> **forterp notes.**
> - **Rank limit:** the seven-dimension maximum *is enforced* — an 8-D (or larger) declarator is a
>   hard error. The `unlimited_rank` knob lifts the cap if you really need it.
> - **Out-of-bounds access (default):** forterp does **not** trap an out-of-range subscript; it
>   reproduces the classic unchecked-storage model, so an access past an array's end walks into the
>   neighbouring variable in the same `COMMON`/`EQUIVALENCE` block (the deliberate over-indexing
>   idioms in old code work), reading 0 only past the whole block. This never affects a conforming
>   program (which stays in bounds). Turn on the **`bounds_check`** knob to make any out-of-range
>   subscript — or substring — a hard error (forterp's `-fcheck=bounds` analog).
> - **Out-of-range substring:** by default it is not trapped and the result is unspecified (don't
>   rely on it); `bounds_check` makes it an error. Lower bounds and assumed-size/adjustable dummies
>   are fully supported.

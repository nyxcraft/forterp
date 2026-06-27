# 9. The `DATA` statement

`DATA` supplies **initial values** at compile time — the value a variable or array holds before
the first executable statement runs *(§9)*. It is the way to set up constant tables, lookup
arrays, and starting values without spending executable assignments on them.

## Form

```fortran
      DATA  nlist / clist / [ , nlist / clist / ] ...
```

`nlist` is a list of variables, array elements, arrays, or substrings; `clist` is the matching
list of constants. The two lists are matched **one constant per storage element**, left to right.

```fortran
      INTEGER N
      REAL    X, Y
      DATA    N /0/, X /1.5/, Y /2.5/
```

## Repeat counts

A constant may be prefixed `r*` to repeat it `r` times — handy for filling an array:

```fortran
      REAL V(5)
      DATA V /5 * 0.0/            ! all five elements set to 0.0
      DATA V /3 * 1.0, 2 * 9.0/   ! 1.0 1.0 1.0 9.0 9.0
```

## Whole arrays and implied-DO

An **unsubscripted array name** takes one constant per element, in storage order (column-major,
[Chapter 5](05-arrays-substrings.md)):

```fortran
      INTEGER T(3)
      DATA    T /10, 20, 30/      ! T(1)=10 T(2)=20 T(3)=30
```

An **implied-DO** initializes selected elements with a loop-like list:

```fortran
      REAL A(100)
      DATA (A(I), I = 1, 100) / 100 * 0.0 /     ! zero the whole array
      DATA (A(I), I = 1, 10, 2) / 5 * 1.0 /     ! A(1),A(3),A(5),A(7),A(9) = 1.0
```

## Type rules

- A numeric constant is converted to the type of the entity it initializes (as in assignment,
  [Chapter 10](10-assignment.md)).
- A `CHARACTER` entity is initialized from a character constant: shorter is blank-padded on the
  right, longer is truncated.
- A `LOGICAL` entity takes `.TRUE.`/`.FALSE.`.

```fortran
      CHARACTER*5 TAG
      DATA        TAG /'AB'/      ! TAG = 'AB   '  (padded to 5)
```

## What may (and may not) be initialized

- **May:** local variables and arrays; named-common entities **only inside a `BLOCK DATA`**
  subprogram ([Chapter 16](16-block-data.md)).
- **May not:** blank-common entities, and dummy arguments.

A `DATA` statement may appear anywhere after the specification statements (it is not required to be
grouped with them), but it only sets the *initial* value — it is not re-executed if control passes
it again.

---

> **forterp notes.** `DATA` is implemented as specified — repeat counts, implied-DO, column-major
> array fill, and the character pad/truncate rule all behave per the standard. (A `BLOCK DATA`
> that initializes named common is [Chapter 16](16-block-data.md), where forterp also enforces the
> "at most one *unnamed* block data" rule.)

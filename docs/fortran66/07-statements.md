# 7. Statements

This is the largest part of the language: every statement FORTRAN 66 provides *(§7)*. Statements
divide into two classes — **executable** statements specify action *(§7.1)*, **nonexecutable**
statements describe data, editing, and arrangement *(§7.2)*. This chapter is organized exactly that
way; use it as a catalogue.

---

# §7.1 Executable statements

There are three groups: **assignment**, **control**, and **input/output** *(§7.1)*.

## Assignment statements

### Arithmetic assignment — `v = e`

Evaluate the arithmetic expression `e` and store it in variable or array element `v` (`v` of any
type except logical) *(§7.1.1.1)*. When the types differ, the value is converted per the standard's
**Table 1** — the important cases are:

- assigning a **real** value to an **integer** `v` **truncates** toward zero (`I = 3.9` gives `3`);
- assigning an **integer** value to a **real** `v` **floats** it (`X = 3` gives `3.0`).

```fortran
      COMMON /O/ N(1)
      N(1) = 7.9
C     -> integer N(1) = 7 (real value truncated, Table 1 "Fix")
```

### Logical assignment — `v = e`

`v` is a logical variable or array element and `e` a logical expression *(§7.1.1.2)*:

```fortran
      LOGICAL BIG
      BIG = X .GT. 100.0
```

### `ASSIGN` — `ASSIGN k TO i`

Assign the statement label `k` to the integer variable `i`, for later use by an assigned `GO TO`
*(§7.1.1.3)*. While `i` holds a label it must not be used as an ordinary integer.

## Control statements

### `GO TO`

Three forms *(§7.1.2.1)*:

```fortran
      GO TO 100
C     -> unconditional: jump to label 100

      GO TO (10,20,30), I
C     -> computed: jump to the I-th label (I=2 -> label 20)

      ASSIGN 20 TO K
      GO TO K, (10,20)
C     -> assigned: jump to the label currently in K (-> label 20)
```

### Arithmetic `IF` — `IF (e) k1,k2,k3`

A three-way branch on the sign of arithmetic expression `e`: to `k1` if `e<0`, `k2` if `e=0`, `k3`
if `e>0` *(§7.1.2.2)*:

```fortran
      COMMON /O/ N(1)
      J = -5
      IF (J) 10, 20, 30
10    N(1) = 1
C     -> J<0, so control goes to label 10
```

### Logical `IF` — `IF (e) S`

If logical expression `e` is true, execute statement `S` (any executable statement except a `DO` or
another logical `IF`); if false, `S` is skipped *(§7.1.2.3)*:

```fortran
      IF (X .LT. 0.0) X = -X
C     -> absolute value of X
```

### `DO` — `DO n i = m1, m2, m3`

A counting loop *(§7.1.2.8)*. The **range** is every statement from the one after the `DO` through
the **terminal statement** labeled `n`. The control variable `i` starts at `m1`; after the range
runs, `i` is incremented by `m3` (default 1 if omitted) and the range repeats while `i` does not
pass `m2`. `m1, m2, m3` are integer constants or variables.

```fortran
      COMMON /O/ N(1)
      K = 0
      DO 1 I = 1, 5
1     K = K + I
      N(1) = K
C     -> 1+2+3+4+5 = 15
```

> **The FORTRAN 66 `DO` is *one-trip*: the range always executes at least once**, even when
> `m1 > m2`, because the termination test happens *after* the range *(§7.1.2.8.1)*. FORTRAN 77
> later changed this to a zero-trip test. This is a real behavioral difference between the dialects
> — see the **forterp notes** at the end of the chapter.

### `CONTINUE`

Does nothing; it is most often the terminal statement of a `DO` *(§7.1.2.6)*.

### `CALL` and `RETURN`

`CALL s(a1,...,an)` (or `CALL s`) invokes subroutine `s`; `RETURN` returns control from a
subprogram to its caller *(§7.1.2.4, §7.1.2.5)*. See [Chapter 8](08-procedures.md).

### `STOP` and `PAUSE`

`STOP` (optionally `STOP n`) terminates the program; `PAUSE` (optionally `PAUSE n`) suspends it
*(§7.1.2.7)*. The `n` is an octal digit string of one to five digits.

## Input/output statements

### `READ` and `WRITE`

Formatted transfer names a format `f`; unformatted transfer omits it *(§7.1.3.2–§7.1.3.2.5)*:

```fortran
      READ  (5, 100) A, B
      WRITE (6, 100) A, B
      READ  (5) A, B
C     -> unformatted (binary) read
```

The list after the format names the variables and array elements to transfer. A **DO-implied list**
embeds a loop in the list *(§7.1.3.2.1)*:

```fortran
      DIMENSION A(3)
      WRITE (6,100) (A(I), I=1,3)
C     -> writes A(1), A(2), A(3)
```

### Auxiliary I/O — `REWIND`, `BACKSPACE`, `ENDFILE`

`REWIND u` repositions unit `u` to its start, `BACKSPACE u` backs up one record, `ENDFILE u` writes
an end-of-file mark *(§7.1.3.3)*.

---

# §7.2 Nonexecutable statements

Five kinds: **specification statements**, the **`DATA`** statement, the **`FORMAT`** statement, and
the function-defining and subprogram statements (the last two are in
[Chapter 8](08-procedures.md)) *(§7.2)*.

## Specification statements

### `DIMENSION` — declare arrays

```fortran
      DIMENSION A(10), B(2,3), C(4,4,4)
C     -> arrays of 1, 2, and 3 dimensions
```

An array declarator gives the array name and the size of each of its (one to three) dimensions
*(§7.2.1.1)*. A declarator may also appear in a type or `COMMON` statement.

### `COMMON` — shared storage

```fortran
      COMMON /BLK/ X, Y, A(10)
      COMMON I, J
C     -> /BLK/ is a named common block; I,J are in blank common
```

`COMMON` places variables and arrays in a storage block shared between program units *(§7.2.1.3)*. A
name between two slashes (`/BLK/`) names a block; entities before any block name, or with `//`, go
in **blank common**. Corresponding positions in a block must match in type across program units
*(§7.2.1.3.1)*.

### `EQUIVALENCE` — overlay storage

```fortran
      DIMENSION A(2,2), B(4)
      EQUIVALENCE (A, B)
C     -> A and B name the same storage; B(1)=A(1,1), B(2)=A(2,1), ...
```

`EQUIVALENCE` makes two or more entities in the same program unit share storage *(§7.2.1.4)*. It is
for storage sharing, not for asserting mathematical equality.

### `EXTERNAL` — pass a procedure as an argument

```fortran
      EXTERNAL SIN
      CALL APPLY(SIN, X)
C     -> SIN is passed as a procedure argument
```

`EXTERNAL` declares that a name is an external procedure, so it can be passed as an argument
*(§7.2.1.5)*.

### Type-statements — declare a name's type

```fortran
      INTEGER COUNT
      REAL    MASS, FORCE
      DOUBLE PRECISION D
      COMPLEX Z
      LOGICAL FLAG
```

A type-statement overrides or confirms the implicit typing and may also supply dimension
information *(§7.2.1.6)*. The types are `INTEGER`, `REAL`, `DOUBLE PRECISION`, `COMPLEX`, `LOGICAL`.

## The `DATA` statement — initial values

```fortran
      COMMON /O/ N(4)
      DIMENSION M(4)
      DATA M /2*7, 3, 9/
C     -> M = 7, 7, 3, 9   (2*7 means "the value 7, twice")
```

`DATA` gives variables and array elements their initial values *(§7.2.2)*. Names and constants
correspond one-to-one; the form `j*c` repeats the constant `c` exactly `j` times. A variable in
blank common may not be initialized; one in a labeled common block may be initialized only inside a
`BLOCK DATA` subprogram ([Chapter 8](08-procedures.md)).

## The `FORMAT` statement — editing for formatted I/O

A (labeled) `FORMAT` statement describes how values convert between their internal form and
characters *(§7.2.3)*. The common **field descriptors** are:

| Descriptor | Edits |
|------------|-------|
| `Iw` | integer in a field `w` wide |
| `Fw.d` | real, fixed point, `d` decimals |
| `Ew.d` | real, exponential |
| `Dw.d` | double precision |
| `Gw.d` | general (chooses F or E) |
| `Lw` | logical (`T`/`F`) |
| `Aw` | Hollerith / character data |
| `nH…` | literal text of `n` characters |
| `nX` | `n` blank columns |

A repeat count `r` before a descriptor (`3F6.2`) repeats it; a group in parentheses with a count
(`2(I3,F5.1)`) repeats the group; the separators are `,` and `/` (a `/` ends a record). A scale
factor `nP` shifts the decimal for F/E/G/D conversions.

```fortran
      I = 42
      X = 3.14
      WRITE (6,100) I, X
100   FORMAT (1X, I3, F6.2)
C     -> " 42  3.14"
```

### Carriage control for printed output

When a formatted record is sent to a printing device, its **first character is not printed** — it
controls vertical spacing *(§7.1.3.4)*:

| First char | Effect before printing |
|------------|------------------------|
| blank | advance one line |
| `0` | advance two lines (blank line before) |
| `1` | advance to the top of the next page |
| `+` | no advance (overprint) |

```fortran
      WRITE (6,100)
100   FORMAT (1H0, 5HHELLO)
C     -> "0" -> a blank line, then HELLO
```

This is why example output lines begin with `1X` or `1H ` — that blank is the carriage control that
keeps the text on its own line.

> **forterp notes.**
>
> - **One-trip `DO`.** Under `F66` (and `FORTRAN10`), a `DO` loop always executes its range at least
>   once, faithfully reproducing X3.9-1966 *(§7.1.2.8.1)* and real FORTRAN-10. The `F77` dialect
>   uses the zero-trip test instead. If you need zero-trip behavior under F66, the `zero_trip_do`
>   knob flips it; see [Appendix C](C-forterp-extensions.md).
> - **Carriage control** applies because forterp treats unit 6 as a **line printer** by default, as
>   FORTRAN-10 did. Output is collected on `engine.out` and the first column of each record is
>   consumed as the control character. (In the `F77` dialect, standard output defaults to a terminal
>   device with no carriage control — see [Appendix C](C-forterp-extensions.md).)
> - **Apostrophe text in `FORMAT`** (`100 FORMAT(' HELLO')`) is a FORTRAN-10 extension and is
>   rejected under strict `F66`; use a Hollerith `nH` field, as above.

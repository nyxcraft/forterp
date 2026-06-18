# FORTRAN-66 / DEC FORTRAN-10 language reference

A working reference for the dialect `pyf66` implements: **ANSI X3.9-1966** ("FORTRAN
66") as the base language, plus the **DEC FORTRAN-10** extensions that the interpreter
reproduces. The authoritative base document is the ANSI X3.9-1966 standard; this file summarizes it as implemented and
calls out where the DEC dialect diverges or extends.

> Notation: items marked **[DEC]** are FORTRAN-10 extensions, not part of ANSI X3.9-1966.
> Set the dialect to `STRICT_F66` to turn the front-end extensions off.

---

## 1. Source form

Fixed-form, card-image, 72 columns significant:

| Columns | Use |
|--------:|-----|
| 1       | `C` or `*` in column 1 → comment line. **[DEC]** `!` anywhere begins a trailing comment. |
| 1–5     | Statement label (1–99999), unsigned, blanks ignored. |
| 6       | Continuation: any non-blank, non-zero character → this line continues the previous statement. |
| 7–72    | Statement body. |
| 73–80   | Ignored (card sequence field). |

- Blanks are not significant except inside Hollerith/character constants — `GO TO`,
  `GOTO`, and `G O T O` are the same.
- A statement may have up to 19 continuation lines (ANSI minimum; the interpreter does
  not impose the cap).
- **[DEC] Tab format**: a leading TAB skips to column 7 (column 8 if the first character
  after the tab is a digit 1–9, which is then treated as a continuation indicator). This
  is how most DEC-10 source was actually keyed.

---

## 2. Data types and constants

| Type | Storage (PDP-10) | Constant forms |
|------|------------------|----------------|
| `INTEGER` | one 36-bit word | `123`, `-7` |
| `REAL` | one 36-bit word | `1.0`, `3.14`, `1.5E-3`, `.5` |
| `DOUBLE PRECISION` | two words | `1.0D0`, `3.14159265358979D0` |
| `COMPLEX` | two words (real, imag) | `(1.0, -2.0)` |
| `LOGICAL` | one word | `.TRUE.`, `.FALSE.` |
| Hollerith | packed, 5 chars/word | `5HHELLO`, `4HABCD` |

**[DEC] Octal constants**: `"777`, or `O"777` / `"777` in data contexts — a literal in
base 8, stored as a 36-bit value. Used heavily for bit masks.

**The 36-bit value model.** Integers are 36-bit two's-complement (`.TRUE.` is the
all-relevant-bits value −1; `.FALSE.` is 0). Characters pack 5 seven-bit ASCII per word
(or 6 SIXBIT). This representation is configurable through `f66.Target`; `f66.PDP10` is
the default.

---

## 3. Names, types, and the type rules

- Symbolic names are 1–6 letters/digits, beginning with a letter (longer names are
  truncated to 6).
- **Implicit typing**: a name beginning with `I, J, K, L, M, N` is `INTEGER`; any other
  starting letter is `REAL`, unless declared otherwise.
- **[DEC] `IMPLICIT`** overrides the I–N rule by letter range, e.g.
  `IMPLICIT INTEGER (A-Z)`.
- Explicit type statements: `INTEGER`, `REAL`, `DOUBLE PRECISION`, `COMPLEX`, `LOGICAL`,
  with optional array dimensions: `REAL A(10), B(3,4)`.

---

## 4. Expressions

**Arithmetic operators**, highest precedence first: `**` (exponentiation,
right-associative) → `*` `/` → unary/binary `+` `-`.

- Mixed-mode: integer/real combinations promote to the "higher" type; `COMPLEX` and
  `DOUBLE PRECISION` do not mix with each other in standard F66.
- Integer division truncates toward zero.
- `I ** J` with integer operands stays integer.

**Relational operators** (yield `LOGICAL`): `.LT. .LE. .EQ. .NE. .GE. .GT.`

**Logical operators**, highest first: `.NOT.` → `.AND.` → `.OR.`
**[DEC]** also `.XOR.` / `.EQV.`.

---

## 5. Statements

### Assignment
```
V = expression
L = logical-expression
ASSIGN 100 TO N            ! label-variable assignment, used with assigned GO TO
```

### Control flow
```
GO TO 100                          ! unconditional
GO TO N, (10,20,30)                ! assigned GO TO (N set by ASSIGN)
GO TO (10,20,30), I                ! computed GO TO (I selects the I-th label)
IF (e) 10, 20, 30                  ! arithmetic IF: e<0 / e==0 / e>0
IF (logical-e) statement           ! logical IF
DO 100 I = 1, N, 2                 ! DO loop
  ...
100 CONTINUE
CONTINUE
PAUSE / PAUSE n / PAUSE 'msg'
STOP  / STOP n
CALL SUB(args)
RETURN
END
```

> **DO-loop semantics (F66, not F77).** The body executes **at least once** even when the
> initial value already exceeds the limit (the "one-trip DO"). On normal exit the index
> variable retains the value it had on the last iteration — it is *not* reset. `pyf66`
> reproduces this faithfully; it is a real behavioral difference from FORTRAN-77.

> **No block IF.** FORTRAN-66 has no `IF ... THEN / ELSE / ENDIF`. Branching is done with
> arithmetic IF, logical IF (single statement), and the GO TO family.

### Specification statements
```
DIMENSION A(10), B(3,4)
COMMON /BLK/ X, Y, Z       ! and blank COMMON: COMMON X, Y
EQUIVALENCE (A(1), B(1,1)) ! storage association
DATA A,B,C /1.0, 2.0, 3*0.0/   ! compile-time initialization, with repeat counts
EXTERNAL FUNC              ! pass a subprogram name as an argument
```
Arrays are column-major and may have up to 3 dimensions (ANSI); the lower bound is 1.

### Subprograms
```
FUNCTION F(X)              ! typed by name / IMPLICIT rules
      F = ...
      RETURN
      END

SUBROUTINE S(A, B)
      ...
      END

      DOUBLE PRECISION FUNCTION D(X)   ! explicitly typed function

ENTRY E(args)              ! [DEC] secondary entry point
```
**Statement function** (single-line, defined before the first executable statement):
```
AVG(P,Q) = (P + Q) / 2.0
```
Argument passing is by reference (call-by-address), so a subprogram may modify its actual
arguments. Arrays may be passed with adjustable dimensions.

---

## 6. Input / output

### Sequential
```
READ  (u, f) list          ! formatted, unit u, FORMAT label f
WRITE (u, f) list
READ  (u) list             ! unformatted (binary record)
WRITE (u) list
READ  f, list              ! read from the standard input unit
PRINT f, list              ! write to the standard output unit
ACCEPT f, list             ! [DEC] read from the terminal
TYPE   f, list             ! [DEC] write to the terminal
```
List-directed I/O uses `*` in place of a FORMAT label: `READ (5,*) A,B,C`.

Control statements: `BACKSPACE u`, `REWIND u`, `ENDFILE u`.
An I/O statement may carry `END=label` and `ERR=label` branches.

**[DEC] Random-access**: `READ (u'r) list` / `WRITE (u'r) list` reads or writes record
number `r` directly.

**[DEC] `ENCODE` / `DECODE`** convert between an internal character buffer and a value
list under FORMAT control (the F66-era equivalent of internal-file I/O).

### FORMAT edit descriptors
```
Iw, Iw.m            integer
Fw.d                fixed real
Ew.d, Dw.d          exponential real / double
Gw.d                general real
Lw                  logical (T/F)
A, Aw               character / Hollerith
nHxxxx              Hollerith literal text
'text'              [DEC] quoted literal text
nX                  skip n columns
Tn                  tab to column n
/                   record separator (newline)
nP                  scale factor
n( ... )            group repeat
:                   format-exhaustion stop
$                   [DEC] suppress trailing newline
```
A repeat count may precede most descriptors (`3I5`, `2F8.2`). If the list is longer than
the format, control reverts to the last open group.

---

## 7. Intrinsic functions (selection)

| Category | Functions |
|----------|-----------|
| Conversion | `INT/IFIX/IDINT`, `FLOAT/REAL`, `DBLE`, `SNGL`, `CMPLX`, `AINT` |
| Truncation/round | `AMOD/MOD`, `SIGN/ISIGN/DSIGN`, `DIM/IDIM`, `NINT/IDNINT` |
| Max/min | `AMAX0/AMAX1/MAX0/MAX1/DMAX1`, `AMIN0/AMIN1/MIN0/MIN1/DMIN1` |
| Absolute | `ABS/IABS/DABS/CABS` |
| Math | `SQRT/DSQRT`, `EXP/DEXP`, `ALOG/ALOG10/DLOG/DLOG10`, `SIN/COS/TAN`, `ASIN/ACOS/ATAN/ATAN2`, `SINH/COSH/TANH` |
| Complex | `AIMAG`, `CONJG`, `REAL` |
| **[DEC]** Bit/logical | `IAND`, `IOR`, `IEOR/XOR`, `NOT`, `ISHFT`/`LSH`, `IBCLR`/`IBSET` |

---

## 8. Where DEC FORTRAN-10 diverges from ANSI X3.9-1966

The features tagged **[DEC]** above are the practical divergences `pyf66` carries by
default (octal/Hollerith literals, `!` and quoted FORMAT text, tab-format source,
`IMPLICIT`, `ENTRY`, `.XOR.`/`.EQV.`, the bit intrinsics, `ACCEPT`/`TYPE`/`PRINT`,
random-access I/O, `ENCODE`/`DECODE`). The 36-bit word size, `.TRUE.` = −1, and the
character packing are properties of the **target** (`f66.PDP10`) rather than the
language, and are likewise configurable.

For anything not covered here, the ANSI X3.9-1966 standard is authoritative for the
base language, and the DECsystem-10 FORTRAN-10 Language Manual (V5) for the extensions.

# FORTRAN-66 / DEC FORTRAN-10 language reference

A working reference for the dialect `forterp` implements: **ANSI X3.9-1966** ("FORTRAN
66") as the base language, plus the **DEC FORTRAN-10** extensions that the interpreter
reproduces. The authoritative base document is the ANSI X3.9-1966 standard; this file summarizes it as implemented and
calls out where the DEC dialect diverges or extends.

> Notation: items marked **[DEC]** are FORTRAN-10 extensions, not part of ANSI X3.9-1966.
> The default dialect is `forterp.F66` (ANSI); select `forterp.FORTRAN10` to turn these extensions
> on.

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
base 8, stored as a 36-bit value. Used heavily for bit masks. (ANSI X3.9-1966 has *no*
octal constant; its only octal use is the `STOP`/`PAUSE` code, §7.1.2.7.)

**[DEC] Apostrophe string literal**: `'HELLO'`. ANSI X3.9-1966 has no quoted-string
constant — its sole character literal is the Hollerith form `nH...` (§5.1.1.6). Under
`FORTRAN10`, `forterp` accepts `'...'` as a Hollerith-equivalent literal (in `DATA`,
expressions, and FORMAT text); `F66` rejects it.

**The value model is configurable** through `forterp.Target`. The default, `forterp.NATIVE`, is
a portable 64-bit host machine (64-bit two's-complement integers, 8-bit ASCII, `.TRUE.`=1
with boolean logicals) for running standard FORTRAN-66. The **36-bit PDP-10 model** —
integers 36-bit two's-complement (`.TRUE.` the all-bits value −1, `.FALSE.` 0), characters
packed 5 seven-bit ASCII per word, `.AND./.OR.` bit-wise on the word — is `forterp.PDP10`,
selected with `Engine(..., target=forterp.PDP10)`. The constant forms above (octal, Hollerith)
are the same in either; only the stored representation differs.

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
> variable retains the value it had on the last iteration — it is *not* reset. `forterp`
> reproduces this faithfully; it is a real behavioral difference from FORTRAN-77.
> A GO TO may also leave a DO's range and later jump back into it (the F66 §7.1.2.8.2
> "extended range"); the loop resumes its iteration when control returns.

> **No block IF.** FORTRAN-66 has no `IF ... THEN / ELSE / ENDIF`. Branching is done with
> arithmetic IF, logical IF (single statement), and the GO TO family.

> **STOP / PAUSE codes.** In F66 the optional code on `STOP n` / `PAUSE n` is an *octal*
> digit string of one to five digits (§7.1.2.7). **[DEC]** the quoted-message forms
> `STOP 'msg'` / `PAUSE 'msg'` are FORTRAN-10 extensions.

### Specification statements
```
DIMENSION A(10), B(3,4)
COMMON /BLK/ X, Y, Z       ! and blank COMMON: COMMON X, Y
EQUIVALENCE (A(1), B(1,1)) ! storage association
DATA A,B,C /1.0, 2.0, 3*0.0/   ! compile-time initialization, with repeat counts
EXTERNAL FUNC              ! pass a subprogram name as an argument
```
Arrays are column-major and may have up to 3 dimensions (ANSI); the lower bound is 1.
F66 restricts an array subscript to the forms `c*v±k`, `c*v`, `v±k`, `v`, or `k` —
integer constants `c`, `k` and an integer variable `v` (§5.1.3.3); **[DEC]** `FORTRAN10`
accepts any integer expression, but `F66` enforces these forms.

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

> **Not a sandbox.** `OPEN`/`READ`/`WRITE` access the host filesystem. Relative file
> names resolve under the engine's `save_root` (default `.`), but absolute paths and
> `..` reach outside it — `forterp` runs a program's I/O against the real filesystem and
> does not contain it. Don't run untrusted source expecting isolation. Default unit
> assignments (V5 Table 10-1): units 3/6 → line printer, unit 5 → terminal input.

### Sequential
```
READ  (u, f) list          ! formatted, unit u, FORMAT label f
WRITE (u, f) list
READ  (u) list             ! unformatted (binary record)
WRITE (u) list
READ  f, list              ! [DEC] read from the standard input unit (no unit designator)
PRINT f, list              ! [DEC] write to the standard output unit
ACCEPT f, list             ! [DEC] read from the terminal
TYPE   f, list             ! [DEC] write to the terminal
```
F66's input/output statements (§7.1.3) are `READ`/`WRITE` with a unit designator, plus
the auxiliary `BACKSPACE`/`REWIND`/`ENDFILE`; `PRINT`, the unit-less `READ`, `ACCEPT`,
and `TYPE` are FORTRAN-10 extensions.

**Run-time (array) FORMAT.** The format reference `f` may be a statement label *or* the
name of an array holding the format text as Hollerith characters (F66 §7.2.3.10),
interpreted when the I/O statement executes:
```
DIMENSION IFMT(2)
DATA IFMT /4H(I5),4H    /
WRITE (6, IFMT) N          ! format taken from IFMT at run time
```

**[DEC] List-directed I/O** uses `*` in place of a FORMAT label: `READ (5,*) A,B,C`.
ANSI X3.9-1966 has no list-directed I/O.

Control statements: `BACKSPACE u`, `REWIND u`, `ENDFILE u`.
An I/O statement may carry `END=label` and `ERR=label` branches.

**[DEC] Random-access**: `READ (u'r) list` / `WRITE (u'r) list` (or the `u#r` form) reads
or writes record number `r` directly; `DEFINE FILE` declares such a unit and `FIND`
positions it. F66 has no random-access I/O, so all of these are rejected under `F66`.

**[DEC] `ENCODE` / `DECODE`** convert between an internal character buffer and a value
list under FORMAT control (the F66-era equivalent of internal-file I/O).

### FORMAT edit descriptors
```
Iw                  integer
Fw.d                fixed real
Ew.d, Dw.d          exponential real / double precision
Gw.d                general real (selects F or E by magnitude)
Lw                  logical (T/F)
Aw                  alphanumeric / Hollerith
nHxxxx              Hollerith literal text
nX                  skip n columns
kP                  scale factor
/                   record separator (newline)
n( ... )            group repeat
'text'              [DEC] quoted literal text (F66 uses nH only)
Ow                  [DEC] octal integer
Rw                  [DEC] right-justified alphanumeric (cf. Aw left-justified)
Tw                  [DEC] tab to column w
$                   [DEC] suppress trailing newline
```
- A repeat count may precede most descriptors (`3I5`, `2F8.2`). If the I/O list is longer
  than the format, control reverts to the last open group.
- **[DEC]** A *bare* descriptor with no width (`I`, `F`, `A`, …) takes the FORTRAN-10 V5
  default width (`I15`, `F15.7`, `E15.7`, `D25.18`, `G15.7`, `A5`, `O15`, `L15`, `R5`,
  §13.2.6); F66 requires an explicit width on every descriptor.
- On input, the `D` and `E` exponent letters are interchangeable (`1.5D2` == `1.5E2`).
- The `kP` scale factor applies on **input** as well as output: a field with no exponent
  of its own is divided by `10**k` (§7.2.3.5.1).
- On input, an `nH` / `'…'` field reads its characters *from* the record and the FORMAT
  itself is updated, so a later WRITE with the same FORMAT echoes them (§7.2.3.8).

---

## 7. Intrinsic functions (selection)

The complete ANSI X3.9-1966 library — all 31 intrinsic functions (Table 3) and all 24
basic external functions (Table 4) — is implemented. A representative selection, with
FORTRAN-10 extensions marked **[DEC]**:

| Category | Functions |
|----------|-----------|
| Conversion | `INT/IFIX/IDINT`, `FLOAT`, `REAL`, `SNGL`, `DBLE`, `CMPLX`, `AINT` |
| Sign/remainder | `MOD/AMOD/DMOD`, `SIGN/ISIGN/DSIGN`, `DIM/IDIM` |
| Max/min | `MAX0/AMAX0/MAX1/AMAX1/DMAX1`, `MIN0/AMIN0/MIN1/AMIN1/DMIN1` |
| Absolute | `ABS/IABS/DABS/CABS` |
| Exp/log | `EXP/DEXP/CEXP`, `ALOG/DLOG/CLOG`, `ALOG10/DLOG10` |
| Trig | `SIN/DSIN/CSIN`, `COS/DCOS/CCOS`, `ATAN/DATAN`, `ATAN2/DATAN2`, `TANH` |
| Square root | `SQRT/DSQRT/CSQRT` |
| Complex | `AIMAG`, `CONJG`, `REAL`, `CMPLX` |
| **[DEC]** Extra elementary | `TAN/DTAN`, `ASIN/DASIN`, `ACOS/DACOS`, `SINH/DSINH`, `COSH/DCOSH`, `TANH/DTANH` |
| **[DEC]** Degree-argument | `SIND/DSIND`, `COSD/DCOSD`, `TAND/DTAND`, `ASIND`, `ACOSD`, `ATAND`, `ATAN2D` |
| **[DEC]** Round/diff/prod | `NINT`, `ANINT`, `DNINT`, `IDNINT`, `DINT`, `DDIM`, `DPROD`, `DFLOAT`, `DCMPLX` |
| **[DEC]** Bit/shift | `LSH`, `ROT` (word shift/rotate; the `.AND.`/`.OR.`/`.NOT.`/`.XOR.`/`.EQV.` *operators* are in §4) |
| **[DEC]** System | `RAN`/`SETRAN`, `DATE`, `EXIT`, `TIM2GO` (runtime builtins) |

The full FORTRAN-10 V5 double-precision and degree-argument math library is now provided.
These **[DEC]** extras (every intrinsic above the 55 standard Table 3/4 functions) are
available under `FORTRAN10`; **strict `F66` exposes only the standard library** — a call to
`DTAN`/`NINT`/`TAND`/… resolves only as an (undefined) external. To use the DEC library
under F66 without the rest of the superset, opt in with `Dialect(dec_intrinsics=True)`.
Still out of scope: the MIL-STD bit-manipulation *functions* `IAND`/`IOR`/`IEOR`/`ISHFT`
(F77, not V5 — bitwise work uses the `.AND.`/`.OR.`/`.XOR.` operators of §4, or `LSH`/`ROT`)
and OS/timing builtins like `SECNDS`/`RUNTIM`.

---

## 8. Where DEC FORTRAN-10 diverges from ANSI X3.9-1966

### Front-end dialect divergences

The features tagged **[DEC]** above are front-end **dialect** divergences: octal and
apostrophe literals, `!` comments and quoted FORMAT text, tab-format source, `IMPLICIT`,
`ENTRY`, the `.XOR.`/`.EQV.` operators, the `LSH` shift intrinsic, the `O`/`R`/`T`/`$`
FORMAT descriptors and bare-width descriptors, `PRINT`/unit-less `READ`/`ACCEPT`/`TYPE`,
list-directed `*` I/O, random-access I/O, `ENCODE`/`DECODE`, free-form (widthless)
formatted input, and the relaxation of three F66 *constraints* — general integer
expressions in array subscripts (§5.1.3.3) and `DO` parameters (§7.1.2.8), and `COMPLEX`↔
numeric assignment (Table 1). **`F66` rejects all of these; `FORTRAN10` accepts them.** The
dialect is selected independently of the target and defaults to `forterp.F66` (ANSI — these
extensions off); select `forterp.FORTRAN10` to enable the whole DEC superset.

### Target (value-model) divergences

The 36-bit word size, `.TRUE.` = −1, and the 5×7-bit character packing are properties of
the **target**, not the language — they belong to `forterp.PDP10`. The default target is
`forterp.NATIVE`, a portable 64-bit model (`.TRUE.`=1, boolean logicals). Target and dialect
are orthogonal: you can run the ANSI dialect on the PDP-10 target, or the DEC dialect on
NATIVE.

### Implementation divergences (the interpreter as built)

These hold on *every* target — they are properties of the tree-walking interpreter, not
of the dialect or the value model:

- **`REAL` is the host double.** A `REAL` datum is a Python float (host double precision);
  there is no distinct single precision. `SNGL`/`DBLE` are effectively identity, so a
  program depending on single-precision rounding sees double-precision results.
- **`COMPLEX` and `DOUBLE PRECISION` occupy one storage cell**, stored as a single host
  object rather than two machine words. Storage association that *splits* them — e.g.
  `EQUIVALENCE`-ing a `COMPLEX` onto two `REAL`s, or counting on a `DOUBLE` spanning two
  `COMMON` words — is not bit-faithful. (The "two words" in §2 describes the PDP-10 model,
  not the interpreter's cell.)
- **Non-fatal arithmetic.** Integer/real divide-by-zero yields `0` and continues rather
  than trapping; library domain errors (`SQRT`/`LOG` of a negative, `ASIN`/`ACOS` of
  |arg|>1) print the V5 warning and continue (V5 App. H — "usually reported as warnings
  and the program continues"). The div-by-zero→0 *value* is a processor-dependent
  stand-in, not a V5-specified result.
- **Out-of-bounds array access is non-fatal.** An OOB read yields `0`; an OOB write is
  dropped (for a local array) — though within a flat `COMMON` block an out-of-range index
  still lands on a real neighbor word. ANSI leaves this undefined; a real FORTRAN-10 with
  bounds-checking would trap.

> **Formatted input (F66 §7.2.3.6).** By default (`F66`) every numeric/logical field is
> read by *column*: packed digits split by width (`(I2,I3)` on `12345` → `12, 345`),
> leading blanks are insignificant, embedded/trailing blanks count as **zeros** (`(I5)` on
> `4 2␣␣` → `40200`), an `Fw.d` field with no decimal point gets the implied decimal
> (`(F5.2)` on `12345` → `123.45`), and a `kP` scale divides an exponent-free field. An
> **all-blank** field is zero (blanks-as-zero), but a field with an **illegal character**
> is a runtime input error: it routes to the READ's `ERR=` label, or — absent `ERR=` —
> halts the program, as real FORTRAN-10 does. A record shorter than an **explicit-width**
> field is **blank-extended** to the field width (and trailing blanks are zeros, so `(I5)`
> on `42` reads `42000`, not `42` — the BZ gotcha). The same rule folds trailing/extension
> blanks into a real field's **exponent**: `(E10.3)` on `1.5E2` reads `1.5E200000` (overflow)
> — so numeric input must be **right-justified**, exactly as on real FORTRAN-10. (This is the
> literal blanks-as-zero behavior; a BN-style "blanks ignored" leniency for interactive input
> is a possible future option, not the default.) **[DEC]** Under `FORTRAN10`, a
> *widthless* descriptor (`I`, `G`, …) instead reads one free-form, space/comma/**tab**-
> delimited token (reading only the columns present) — the idiom variable-length
> tab-delimited databases (e.g. ADVENT) rely on. For free-form input regardless of dialect,
> list-directed `READ(u,*)` and NAMELIST are whitespace-delimited by design.

For anything not covered here, the ANSI X3.9-1966 standard is authoritative for the
base language, and the DECsystem-10 FORTRAN-10 Language Manual (V5) for the extensions.

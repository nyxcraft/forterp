# FORTRAN 77 language reference

A working reference for the **FORTRAN 77** dialect `forterp` implements: **ANSI X3.9-1978**
layered on the FORTRAN-66 base that the interpreter already runs. The headline addition is
the **`CHARACTER` data type**; F77 also brings the block `IF` construct, list-directed and
keyword-driven I/O, internal files, `INQUIRE`, `PARAMETER`/`SAVE`/`INTRINSIC`, and the
`.EQV.`/`.NEQV.` operators. This file documents what the F77 dialect adds over
[FORTRAN-66](FORTRAN66.md) — read that first for the base language (source form, the
arithmetic/control/`COMMON` core, `FORMAT`).

> 📖 **Looking for the language itself?** This page is a guide to forterp's F77 *dialect* —
> selecting it, the `CHARACTER` type, the I/O additions, the tunable knobs. For a complete,
> example-driven reference to the **FORTRAN 77 language**, organized on the standard and
> self-contained, read the **[FORTRAN 77 reference manual](fortran77/README.md)**.

> Notation: items here are FORTRAN-77 features unless marked **[DEC]** (a FORTRAN-10
> extension that strict F77 does not include) or **[F66]** (carried over from the base).
> Select the dialect with `forterp.F77`, the prebuilt `forterp.f77`, or the CLI `--std f77`.

---

## 1. Selecting and using the F77 dialect

```python
import forterp

src = '''      PROGRAM GREET
      CHARACTER*12 WHO
      WHO = 'WORLD'
      WRITE (6, '(A,A)') 'HELLO, ', WHO
      END
'''
forterp.run_source(src, dialect=forterp.F77, printer=print)   # HELLO, WORLD
forterp.f77.run_source(src, printer=print)                    # the prebuilt interpreter
```

```sh
forterp --std f77 prog.for          # the general CLI driver, F77 dialect
```

The F77 dialect runs on the **`NATIVE`** target by default (64-bit, 8-bit ASCII), where a
character value is an ordinary Python `str`. The target and dialect axes stay orthogonal
(see [API.md](API.md)) — you *can* pair F77 with `PDP10`, but the F77 corpus is validated on
`NATIVE`. The single switch that changes the value model for characters is the dialect knob
**`character_type`** (§9): with it on, a quoted string is a `CHARACTER` constant (a `str`),
not a Hollerith word packed into an integer as it is under F66/FORTRAN-10.

---

## 2. The `CHARACTER` type

The defining feature of F77. A `CHARACTER` entity holds a fixed-length string of
characters; its length is part of its type.

### Declaration

```fortran
      CHARACTER         C          ! length 1
      CHARACTER*8       NAME       ! length 8 (the keyword *len is the default)
      CHARACTER         TAG*3, MSG*40   ! per-name length overrides the keyword length
      CHARACTER*5       WORD(10)   ! a 10-element array of CHARACTER*5
      CHARACTER*(*)     ARG        ! assumed length: a dummy takes the actual's length
      CHARACTER*(LMAX)  BUF        ! a parenthesised integer-constant expr (e.g. a PARAMETER)
```

- The length is the number of characters; the default is 1.
- `CHARACTER*(*)` is an **assumed length** dummy argument — it inherits the length of the
  actual argument passed to it.
- A parenthesised length `*(expr)` may be any integer-constant expression, including a
  `PARAMETER` name (X3.9-1978 §5.1).
- `IMPLICIT CHARACTER*n (letters)` types whole initial-letter ranges as `CHARACTER*n` —
  the standard preamble used throughout the FCVS audit suite.

### Assignment — blank-pad / truncate

Assignment fits the right-hand side to the target's declared length: a shorter value is
**blank-padded on the right**, a longer one is **truncated** (X3.9-1978 §10.4).

```fortran
      CHARACTER*5 S
      S = 'HI'        ! S = 'HI   '   (padded to 5)
      S = 'HELLO!'    ! S = 'HELLO'   (truncated to 5)
```

### Concatenation — `//`

```fortran
      CHARACTER*6 R
      R = 'AB' // 'CD'     ! R = 'ABCD  '
```

### Comparison — blank-padded

Relational comparison pads the shorter operand with blanks to the longer length, then
compares left to right, so `'HI'` and `'HI   '` compare **equal** (X3.9-1978 §6.3.5).

```fortran
      IF (S .EQ. 'HI') ...        ! true when S = 'HI   '
```

### Substrings — `name(lo:hi)`

A contiguous slice, 1-based and inclusive, usable as a value **or** an assignable target.
Either bound may be omitted (`(:)`, `(lo:)`, `(:hi)`; defaults 1 and `LEN`).

```fortran
      CHARACTER*5 R
      R = 'ABCDE'
      R(2:4) = 'XY'      ! R = 'AXY E'  (RHS fitted to the 3-char slice, rest untouched)
      C2 = R(2:3)        ! 'XY'  (read)
      W(K)(1:2) = 'ZZ'   ! array-element substring (the element of a CHARACTER array)
```

### Character intrinsics

| Function | Result |
|----------|--------|
| `LEN(s)` | declared length of `s` (an integer) |
| `CHAR(i)` | the character whose code is `i` |
| `ICHAR(c)` | the integer code of the single character `c` |
| `INDEX(s, t)` | position of the first occurrence of `t` in `s`, else 0 |
| `LGE/LGT/LLE/LLT(a, b)` | lexical `>=` / `>` / `<=` / `<` comparison (logical) |

---

## 3. Structured control flow — the block `IF`

```fortran
      IF (cond) THEN
        ...
      ELSE IF (cond2) THEN
        ...
      ELSE
        ...
      END IF              ! ENDIF (one word) is also accepted
```

Blocks nest, and an arm may jump out with a `GO TO`; the construct is lowered at parse time
to the engine's flat label+`GOTO` form, so it composes with `DO` loops and arithmetic `IF`
exactly as hand-written branches would.

> **[DEC] `DO WHILE (cond) … END DO`** is *not* part of ANSI X3.9-1978 — it is a DEC /
> Fortran-90 extension. The F77 dialect **rejects** it; use `forterp.FORTRAN10` if you need
> it. (This is the one structured construct deliberately kept off the F77 axis.)

---

## 4. Declarations and specification statements

| Statement | Notes |
|-----------|-------|
| `PARAMETER (N=expr, …)` | named constants; the value may be `INTEGER`/`REAL`/`DOUBLE`, **`LOGICAL`** (`.TRUE.`/`.FALSE.`), **`COMPLEX`** (`(re,im)`), or `CHARACTER` |
| `SAVE [a, b, …]` | accepted and honored; use it where you need a local retained across calls (non-`SAVE` retention is unspecified — see [reference manual ch. 17](fortran77/17-association.md)) |
| `INTRINSIC name, …` | accepted; declares names as intrinsic (they already resolve by name) |
| `IMPLICIT CHARACTER*n (C)` | implicit typing with a length (see §2) |

### Arrays: assumed-size and adjustable

For dummy-argument arrays, F77 allows the bounds to be determined by the call:

```fortran
      SUBROUTINE S (A, B, M, N)
      DIMENSION A(*)              ! assumed-size: last upper bound = the actual's
      DIMENSION B(M:N, 3)         ! adjustable: bounds are dummy-argument values
```

The assumed-size `*` is the last dimension's upper bound; column-major indexing never needs
it, and the dummy aliases the actual's storage. Adjustable bounds are resolved per call.

---

## 5. Expressions and operators

- **`.EQV.` / `.NEQV.`** — logical equivalence and non-equivalence (X3.9-1978 §6.6).
  (The DEC-only `.XOR.` and the symbolic `==`/`<`/`>` relationals stay off the F77 axis.)
- **Generic intrinsics** — F77's generic names dispatch on argument type: `LOG`/`LOG10`
  (F66 wrote `ALOG`/`ALOG10`), and `SQRT`/`EXP`/`SIN`/`COS`/`ABS`/… accept `REAL`, `DOUBLE`,
  or `COMPLEX` arguments, routing to the right variant automatically.
- **`DO label, var = …`** — F77 permits an optional comma after the `DO` label:
  `DO 10, I = 1, N`.

---

## 6. Input / output

F77 broadens the F66 I/O model considerably.

### List-directed I/O — `*`

```fortran
      WRITE (6, *) I, X, 'TEXT'        ! free-format, compiler-chosen layout
      READ  (5, *) I, X               ! whitespace/comma-delimited input
```

Standardized in F77 §12 (a DEC extension before that). On the F77 axis it rides its own
`list_directed_io` knob — independent of the rest of the DEC I/O bundle.

### Keyword control lists

The control list may use keyword specifiers in any order:

```fortran
      READ  (UNIT=5, FMT=100, END=900, IOSTAT=IOS) A, B
      WRITE (UNIT=6, FMT='(2I5)')                  I, J
```

`UNIT=` and `FMT=` route to the unit and format; `END=`/`ERR=`/`REC=`/`IOSTAT=` behave as in
the positional form. The positional form `READ(u, f) …` is unchanged.

### Internal files

The "unit" may be a `CHARACTER` variable, array element, or substring — I/O then transfers
to/from its text instead of a device (X3.9-1978 §12.2.2):

```fortran
      CHARACTER*16 LINE
      WRITE (LINE, '(I4,A)') N, ' ITEMS'    ! format INTO the string
      READ  (LINE(5:8), '(I4)') K           ! parse a substring of it
```

### Sequential files, scratch units, and record fidelity

- An **unconnected unit** that is written auto-connects as an in-memory sequential scratch
  file (the FORTRAN-10 `FORnn.DAT` default): `WRITE` appends records, `REWIND`/`BACKSPACE`
  reposition, and a later `READ` reads them back.
- Under F77 a **formatted** sequential file stores rendered *text* records, so the format's
  `/` (record breaks), `X`/`T`/column positioning, and **read-side `FORMAT` reversion** (the
  I/O list outlasting the format, re-scanning over fresh records) all round-trip on
  write→`REWIND`→read.

### `OPEN` / `CLOSE` / `INQUIRE`

```fortran
      OPEN  (UNIT=8, FILE='DATA', ACCESS='SEQUENTIAL', FORM='UNFORMATTED')
      INQUIRE (UNIT=8, EXIST=EX, OPENED=OP, NUMBER=N, NAME=NM,
     1         ACCESS=AC, SEQUENTIAL=SQ, DIRECT=DR,
     2         FORM=FM, FORMATTED=FT, UNFORMATTED=UF, IOSTAT=IOS)
      INQUIRE (FILE='DATA', EXIST=EX, ...)        ! or inquire by file name
```

`INQUIRE` (by `UNIT` or by `FILE`) reports `EXIST`/`OPENED`/`NUMBER`/`NAMED`/`NAME`/`IOSTAT`
and the connection properties `ACCESS`/`FORM` plus the `YES`/`NO`/`UNKNOWN` specifiers
`SEQUENTIAL`/`DIRECT`/`FORMATTED`/`UNFORMATTED` (X3.9-1978 §12.10).

### Widthless `A`

F77 §13.5.11 makes the field width optional on the `A` descriptor alone — a widthless `A`
uses the list item's declared `CHARACTER` length. (Strict F66 requires a width on every
descriptor.)

---

## 7. What the F77 dialect does *not* add

The F77 dialect is the 1978 standard, not a superset of everything later or DEC-specific:

- **`DO WHILE`** — DEC/Fortran-90, not X3.9-1978 (see §3). On `FORTRAN10`, off `F77`.
- **`.XOR.` and symbolic relationals (`==`, `<`, `>`)** — DEC operators; `F77` has only
  `.EQV.`/`.NEQV.` from the F77 logical set.
- **DEC array-bound `A(lo/hi)`** — F77 uses only `A(lo:hi)`; under F77 a `/` inside a bound
  is ordinary division (`A(6/3:9)` is `A(2:9)`).
- **Fortran-90 free-form source, `CHARACTER(LEN=…)`, modules, dynamic allocation** — out of
  scope; the source form is fixed-form card image as in [F66](FORTRAN66.md#1-source-form).

---

## 8. Conformance — FCVS-77

The interpreter is exercised against the whole **FCVS** (FORTRAN Compiler Validation System)
audit corpus — one set of **192 routines** in `tests/fcvs/`, pristine from the public-domain
NIST suite (the `.FOR` files are byte-identical to [github.com/gklimowicz/FCVS](https://github.com/gklimowicz/FCVS)).
FORTRAN-77 is valid against all of it; the F66-valid subset is also run under FORTRAN-66
(`test_fcvs_f66_conformance.py`).

Card-reader input comes from the **canonical NIST `<NAME>.DAT` decks vendored beside each
`.FOR`** (one 80-column card per line) — not from the `CARD nn` image comments in the source,
which wrap at the 72-column display boundary and so reconstruct lossily. `fcvs_runner._card_deck`
reads a sibling `.DAT` first; nine routines have one (FM110/111/403/404/900/901/903/906/923).

- **All 192 parse and run** under F77 — the front end is complete (zero parse-gaps) — and each
  runs *every* declared sub-test (no mid-run crash; the completeness check reconciles FCVS's own
  "X OF Y TESTS EXECUTED").
- The self-checking routines report **zero failures**. FM001 TEST 002 ("FORCE FAIL CODE TO BE
  EXECUTED") is a *negative* assertion — the suite testing its own fail-reporting path — so the
  runner counts that one by-design failure as a pass. Pinned in `tests/test_fcvs_f77_conformance.py`.
- The **print-and-eyeball** routines (no self-check) are validated by a **golden** diff against
  gfortran output committed under `tests/fcvs_golden/` — `test_fcvs_golden.py` compares without
  needing gfortran at test time (regenerate with `tests/fcvs_golden/regenerate.py`, which now
  feeds those `.DAT` decks). With the correct decks, **gfortran runs the entire 192-routine
  corpus** (it used to abort on three) and **forterp byte-matches 191 of 192**. Each routine sits
  in exactly one validation bucket, all enforced by `test_whole_corpus_is_accounted_for`:
  - *byte-match* against the golden (the large majority);
  - *value-token* compare for list-directed output, whose field widths/precision the standard
    leaves processor-dependent (FM905/907);
  - the routine's *own self-check* where gfortran is the unreliable oracle (FM257 PAUSE in batch,
    FM406's `-0.0`);
  - **`KNOWN_GF_DIFF`** — documented, non-matching: just **FM111**, where gfortran is the outlier
    (it overflows `F2.1` of a value that rounds to zero to `**`, keeping the sign) and forterp
    matches the routine's own printed CORRECT line (`.0`).

Driving this corpus to a clean pass surfaced and fixed a series of real edit-descriptor bugs —
the letterless signed exponent on input (`0.987+1`), a no-digit-mantissa field as zero (`.`,
`+.E00`), blank-insignificance in a FORMAT (`3 I4` = `3I4`, `F5 .2` = `F5.2`), E/D output that
rounds once (no double-round), and the `nP` scale factor's correct scope (no effect on G in
F-form; persists across a reverted format on input). See [FORTRAN66.md](FORTRAN66.md) §I/O.

This corpus is independent of the interpreter's own assumptions (it predates the project by
~40 years), so it is the primary check on F77 conformance. See also
[FORTRAN66.md](FORTRAN66.md) for the base-language `tests/fcvs/` corpus.

---

## 9. The F77 dialect knobs

`forterp.F77` is a `Dialect` (see [API.md](API.md#the-two-axes-target-and-dialect)) with these
flags on. Several were split out of the broader DEC bundles so F77 gets exactly the
standardized subset:

| Knob | Enables |
|------|---------|
| `character_type` | the `CHARACTER` data type — quoted strings become `str`, not Hollerith words |
| `block_if` | `IF … THEN` / `ELSE IF` / `ELSE` / `END IF` |
| `list_directed_io` | list-directed `*` `READ`/`WRITE` (split from the DEC `extended_io` bundle) |
| `eqv_operators` | `.EQV.` / `.NEQV.` (split from the DEC `dec_operators` bundle) |
| `parameter_stmt` | the `PARAMETER` statement |
| `implicit_stmt` | the `IMPLICIT` statement (incl. `IMPLICIT CHARACTER*n`) |
| `save_stmt`, `intrinsic_stmt` | `SAVE` / `INTRINSIC` |
| `expr_subscripts` | general integer expressions in subscripts and `DO` bounds |
| `array_lower_bounds` | `DIMENSION A(lo:hi)`, assumed-size `A(*)`, adjustable bounds |
| `alt_return` | alternate-return actual arguments (`CALL S(*99)`) |
| `mixed_complex_assign` | `COMPLEX` ↔ numeric assignment |
| `apostrophe_string` | `'…'` string constants |
| `dec_intrinsics` | the F77 generic intrinsic library (a superset of F66 Tables 3 & 4) |

Notably **off** for F77 (and on only for `FORTRAN10`): `do_while`, `dec_operators` (`.XOR.`,
`==`/`<`/`>`), `slash_dim_bound` (`A(lo/hi)`), `octal_quote`, `tab_format`, `inline_comment`
(`!`), `extended_io` (`TYPE`/`ACCEPT`/`ENCODE`/`DECODE`, random-access), `free_form_input`.

---

## 10. The FORTRAN 77 language reference

Sections 1–9 above are about forterp's F77 *dialect* — how to select it, the `CHARACTER` type, the
I/O additions, the knobs. For the **language itself**, forterp ships a complete, example-driven
reference to ANSI X3.9-1978, organized on the standard and self-contained:

### → [The FORTRAN 77 reference manual](fortran77/README.md)

Eighteen chapters following the standard's structure, every feature shown with a runnable example,
each chapter closing with a **forterp notes** box for behavior specific to this implementation.
Start at the [contents page](fortran77/README.md), or jump to a topic:

- [1. Overview & program structure](fortran77/01-overview.md) ·
  [2. Language elements](fortran77/02-language-elements.md) ·
  [3. Source form](fortran77/03-source-form.md) ·
  [4. Data types & constants](fortran77/04-data-types.md)
- [5. Arrays & substrings](fortran77/05-arrays-substrings.md) ·
  [6. Expressions](fortran77/06-expressions.md) ·
  [7. Statements](fortran77/07-statements.md) ·
  [8. Specification statements](fortran77/08-specification.md)
- [9. DATA](fortran77/09-data.md) ·
  [10. Assignment](fortran77/10-assignment.md) ·
  [11. Control](fortran77/11-control.md)
- [12. Input / output](fortran77/12-io.md) ·
  [13. FORMAT & edit descriptors](fortran77/13-format.md)
- [14. Main program](fortran77/14-main-program.md) ·
  [15. Functions & subroutines](fortran77/15-procedures.md) ·
  [16. Block data](fortran77/16-block-data.md)
- [17. Storage association & definition](fortran77/17-association.md) ·
  [18. Scopes & symbolic names](fortran77/18-scopes.md)
- Appendices: [A. Intrinsics](fortran77/A-intrinsics.md) ·
  [B. Edit descriptors](fortran77/B-edit-descriptors.md) ·
  [C. Precedence & collating](fortran77/C-precedence-ascii.md) ·
  [D. forterp extensions & strict gates](fortran77/D-forterp-extensions.md)

**forterp's behavior at the edges of the standard** — the committed extensions, the strictly
enforced rules (recursion, complex ordering, char⟷numeric `EQUIVALENCE`, assignment to a
`PARAMETER`, empty `''`, rank > 7, duplicate unnamed `BLOCK DATA`, statement order), the tunable
knobs (`bounds_check`, `recursion`, `unlimited_rank`, `carriage_control`), and the one value-model
divergence — is collected in **[Appendix D](fortran77/D-forterp-extensions.md)**. The conformance
evidence behind it all is the FCVS-77 suite ([§8](#8-conformance--fcvs-77)).

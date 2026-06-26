# FORTRAN 77 language reference

A working reference for the **FORTRAN 77** dialect `forterp` implements: **ANSI X3.9-1978**
layered on the FORTRAN-66 base that the interpreter already runs. The headline addition is
the **`CHARACTER` data type**; F77 also brings the block `IF` construct, list-directed and
keyword-driven I/O, internal files, `INQUIRE`, `PARAMETER`/`SAVE`/`INTRINSIC`, and the
`.EQV.`/`.NEQV.` operators. This file documents what the F77 dialect adds over
[FORTRAN-66](FORTRAN66.md) — read that first for the base language (source form, the
arithmetic/control/`COMMON` core, `FORMAT`).

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
| `SAVE [a, b, …]` | accepted; a no-op here — locals are already statically allocated |
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

## 10. ANSI X3.9-1978 compliance map

A condensed, section-by-section restatement of the **ANSI X3.9-1978** ("FORTRAN 77 Full
Language") standard, keyed to its section numbers, with forterp's status against each rule.
Built by reading the standard text in full (the source PDF lives in the project notes, not
the repo). Status legend: **✓** forterp conforms · **▲** intentional/​documented divergence
or extension · **✗** known gap (see [§8](#8-conformance--fcvs-77) and the test suite). This
is the full language; forterp does not implement the separate "subset FORTRAN" level.

### §1 Conformance

- **Conformance (1.4).** "must" is a requirement, "must not" a prohibition (1.5). A
  conforming *program* uses only standard forms; a conforming *processor* runs them per the
  standard interpretation and may add extensions that don't change a conforming program's
  meaning. A program must not use processor-added intrinsics; a name in `EXTERNAL` overrides
  any like-named processor intrinsic. — ✓ forterp's F77 is the full language; the DEC
  extensions live on the separate `FORTRAN10` dialect, off under `F77`.

### §2 Terms and concepts

- **Symbolic name (2.2).** 1–6 letters/digits, first a letter. — ✓
- **Statement label (2.2).** 1–5 digits, at least one nonzero. — ✓
- **No reserved words (2.2).** keyword vs name is by context. — ✓
- **Program structure (2.4).** one main program + any number of subprograms/external
  procedures; `PROGRAM` is optional; main program = no `FUNCTION`/`SUBROUTINE`/`BLOCK DATA`
  first. — ✓
- **Implicit typing (2.5).** absent a type-statement/`IMPLICIT`, `I`–`N` ⇒ integer, else
  real. — ✓
- **Storage units (2.13).** integer/real/logical = 1 numeric unit; **double precision and
  complex = 2 numeric units**; character = 1 character unit per character; numeric and
  character units are unrelated (can't associate across the two). — ▲ forterp's storage
  association uses one *value slot* per element: `COMPLEX` correctly occupies two slots
  (`ComplexPairRef`), but `DOUBLE PRECISION` occupies one slot rather than two numeric units.
  This only differs observably under `EQUIVALENCE`/`COMMON` aliasing of a double against a
  pair of reals (rare; not exercised by the FCVS corpus) — see §8/§17 notes.
- **Definition status (2.11).** entities are undefined at program start unless `DATA`-
  initialized; a reference requires a defined value; a CHARACTER entity is defined iff every
  length-one substring is. — ✓ (forterp does not trap *use* of undefined; faithful to the
  "no predictable value" latitude.)
- **Association (2.14).** `COMMON`, `EQUIVALENCE`, argument, `ENTRY`. — ✓ (details in §8/§15/§17.)

### §3 Characters, lines, execution sequence

- **Character set (3.1).** 26 letters, 10 digits, 13 specials (blank `= + - * / ( ) , . $ ' :`).
  — ✓
- **Collating sequence (3.1.5).** only a partial order is required — `A<…<Z`, `0<…<9`,
  blank below both, digits and letters not interleaved; `LGE/LGT/LLE/LLT` compare by it. — ✓
  (forterp uses ASCII, which satisfies the partial order.)
- **Fixed source form (3.2).** 72-column lines; comment = `C`/`*` in col 1 or all-blank;
  initial line has blank/`0` in col 6; a continuation line has a non-blank, non-`0` col 6 and
  blank cols 1–5; ≤19 continuation lines; statement text in cols 7–72; `END` only on an
  initial line. — ✓
- **Statement labels (3.4).** 1–5 digits, ≥1 nonzero, cols 1–5, unique per program unit,
  leading zeros/blanks insignificant; only labeled executable and `FORMAT` statements are
  referenceable. — ✓
- **Statement order (3.5).** `PROGRAM`/`FUNCTION`/`SUBROUTINE`/`BLOCK DATA` first;
  `IMPLICIT` before other specs (except `PARAMETER`); specifications before
  `DATA`/statement-functions/executables; statement functions before executables; `FORMAT`/
  `DATA`/`ENTRY` may float past the spec section; `END` last. — ✓ **enforced under F77**: a
  specification statement appearing after an executable statement is a hard error (`?FTNORD`,
  the `strict_stmt_order` knob; verified against the corpus — no conforming routine trips it).
  The finer sub-rules — `IMPLICIT` before the other specifications, and the `PARAMETER`
  type-ordering — are not yet diagnosed.
- **Execution & recursion (3.6).** execution starts at the main program's first executable;
  a procedure "must not be referenced a second time without the prior execution of a `RETURN`
  or `END`" — i.e. **no recursion**. — ✓ **enforced**: re-entry of a still-active unit (direct
  or indirect) raises `IllegalRecursion` on every dialect, rather than silently corrupting the
  static locals. The `recursion` dialect knob opts in to permitting it *correctly* (per-call
  local storage); see [§15](#15-functions-and-subroutines).

### §4 Data types and constants

- **Six types (4.1).** integer, real, double precision, complex, logical, character; one type
  per name per program unit; implicit typing `I`–`N` ⇒ integer else real (4.1.2). — ✓
- **Signed zero (4.1.3).** zero is neither positive nor negative; `-0.0` equals `0.0`. — ✓
- **Integer constant (4.3.1).** `[±]` digits, decimal. — ✓
- **Real constant (4.4).** `[±][int].[frac]` (not both parts empty), optional `E`-exponent;
  `5.`, `.5`, `5E3`, `5.0E3` all valid. — ✓
- **Double precision (4.5).** a `D`-exponent makes the constant double precision (`2.0D0`);
  precision must exceed real; two numeric storage units. — ▲ faithful under the **PDP10**
  target (36-bit single vs two-word double); under the default **NATIVE** target real and
  double precision share a 64-bit host double, so the precision is equal rather than strictly
  greater (a pluggable-value-model choice).
- **Complex constant (4.6.1).** `(re, im)` where each part is an optionally-signed real or
  integer constant; two numeric storage units (real then imaginary). — ✓
- **Logical (4.7).** `.TRUE.` / `.FALSE.` only. — ✓
- **Character constant (4.8.1).** an apostrophe, a **nonempty** string of characters, an
  apostrophe; blanks significant; a doubled `''` denotes one embedded apostrophe. — ✓ the
  nonempty requirement is **enforced on every dialect**: the empty constant `''` is a hard
  error (`?FTNECC`), since a zero-length string is meaningless in both the CHARACTER and
  Hollerith models (and is a Fortran-90 feature, not F77). The check keys on the resolved
  value, so an embedded apostrophe (`'O''CLOCK'` → `O'CLOCK`) is unaffected.

### §5 Arrays and substrings

- **Array declarator (5.1).** `a(d[,d]…)`, **1–7 dimensions**; a dimension is `[lo:]hi`
  (default `lo`=1, `hi`≥`lo`); the last `hi` may be `*` (assumed-size); variables in a bound
  ⇒ adjustable (dummy arrays only); constant/adjustable/assumed-size kinds; actual
  declarators must be constant. — ✓ lower bounds, assumed-size, and adjustable arrays are all
  supported; the seven-dimension maximum is **enforced** on every dialect (an 8-D+ declarator
  is a hard error, `?FTNRNK`), liftable with the `unlimited_rank` knob. (F66's stricter
  three-dimension limit is left lenient — an accept-more for the base dialect.)
- **Element ordering (5.2.4).** column-major — the first subscript varies fastest. — ✓
  (verified by `EQUIVALENCE`-flattening).
- **Subscripts (5.4).** one integer subscript expression per dimension; the value must lie
  within the declared bounds (a *program* requirement — a processor need not detect a
  violation). — ▲ by default forterp does not trap an out-of-bounds subscript; it reproduces
  the FORTRAN-10 unchecked-storage model **faithfully**: an out-of-bounds access traverses the
  `COMMON`/`EQUIVALENCE` storage sequence, so the deliberate over-/under-indexing tricks land in
  the neighbouring variable (read and write, both ends), reading 0 only past the whole store.
  The standard explicitly permits this non-detection. — ✓ an opt-in **`bounds_check`** knob
  (engine `bounds_check=True`) turns any subscript outside its declared `[lo,hi]` into a hard
  error (`OobError`, the gfortran `-fcheck=bounds` analog — it catches the neighbour-reaching
  case too); the store-level census `forterp.debug.oob_census()` remains available.
- **Substring (5.7).** `v(e1:e2)` / `a(s…)(e1:e2)`, `1 ≤ e1 ≤ e2 ≤ len`, omitted `e1`⇒1,
  `e2`⇒len, `v(:)`≡`v`, length `e2−e1+1`. — ✓ for in-range use. — ▲ by default an out-of-range
  window is clamped/blank-padded rather than trapped (e.g. `S(1:9)` of a `CHARACTER*4` yields the
  4 characters padded to 9); lenient. — ✓ the **`bounds_check`** knob covers substrings too:
  with it on, an `e1<1` / `e2>len` / `e1>e2` window is a hard error (`OobError`), the same gate
  as the array-subscript check (§5.4) — forterp's `-fcheck=bounds` analog spans both.

### §6 Expressions

- **Arithmetic (6.1).** operators `** / * - +`; precedence `**` > `* /` > `+ -`; `**` is
  **right-associative** (`2**3**2` = `2**(3**2)` = 512), `* /` and `+ -` left-associative;
  `-A**2` = `-(A**2)`; no two adjacent operators (`A**(-B)` not `A**-B`). — ✓ verified.
- **Result type (6.1.4, Tables 2–3).** a mixed-type operator converts the operand that
  differs from the result type; real/double/complex `** integer` leaves the integer
  unconverted; **double precision combined with complex is prohibited**; `C**C` is the
  principal value `EXP(x2·LOG(x1))`. — ✓ promotions. The Table-2/3 "Prohibited" entry for
  double-precision ⊗ complex arithmetic is accepted as an extension: forterp promotes and
  computes the double-complex result (e.g. `2D0*(1.,3.)` → `(2.,6.)`), identical to gfortran in
  every mode (incl. `-std=f95`). §1.4 permits this — a conforming program never forms it, so
  accepting it can't change any conforming program's meaning.
- **Integer division (6.1.5).** truncates toward zero — `(-8)/3` = −2, `5/2` = 2,
  `2**(-3)` = 0. — ✓ verified.
- **Math errors (6.6).** "Any arithmetic operation whose result is not mathematically defined is
  prohibited" — *examples:* dividing by zero, a **zero**-valued base to a zero/negative power, and
  a **negative** base to a real/double power. (Note a *nonzero* base to a negative integer power
  is **defined**, §6.1.5: `2**(-3)` = `1/(2**3)` = `0` — forterp computes this correctly, it is
  not a divergence.) — ✓ **non-fatal**, and now **target-aware**: these undefined ops never trap,
  and the value follows the target's `ieee_math` flag. **NATIVE** delivers IEEE results identical
  to gfortran (`1.0/0.0`→`Inf`, `0.0/0.0`→`NaN`, `0.0**(-1)`→`Inf`, `(-4.)**0.5`/`SQRT(-1)`→`NaN`);
  **PDP10** keeps FOROTS's non-fatal recovery (`0.0` on divide, a `|x|` stand-in + a LIB warning
  on a domain error). Any result conforms (the op is undefined) and a conforming program never
  reaches it. Operand short-circuiting (6.6.1) is permitted-not-required; forterp evaluates eagerly.
- **Character (6.2).** `//` concatenation, left-associative, parentheses don't change the
  value. — ✓
- **Relational (6.3).** `.LT. .LE. .EQ. .NE. .GT. .GE.`; compare two arithmetic or two
  character operands (never mixed); a complex operand only with `.EQ.`/`.NE.`; the shorter
  character operand is blank-padded on the right; `.EQ.`/`.NE.` are collating-independent. — ✓
  — ✓ an ordering comparison on a complex operand (`C1 .LT. C2` etc.) is **rejected** on every
  dialect (`RuntimeError`, §6.3.3): complex values have no ordering, so it is a nonsense
  comparison with no defined result — gfortran rejects it in all modes, and forterp now does too
  rather than returning a silent `.FALSE.`.
- **Logical (6.4).** `.NOT. .AND. .OR. .EQV. .NEQV.`, precedence `.NOT.` > `.AND.` > `.OR.` >
  `.EQV./.NEQV.`, left-associative within a level. — ✓ verified.
- **Operator-class precedence (6.5).** arithmetic > character > relational > logical. — ✓
- **Integrity of parentheses (6.6.3).** a parenthesized subexpression is evaluated as a unit
  (`A*(B*C)` is not regrouped to `(A*B)*C`). — ✓ (forterp evaluates the parse tree as written).

### §7 Statement classification

- **Statement classes (§7).** all executable and nonexecutable statements listed are
  supported. — ✓

### §8 Specification statements

- **DIMENSION / COMMON / EQUIVALENCE (8.1–8.3).** array declarators in `DIMENSION`/type/
  `COMMON`; `EQUIVALENCE` shares storage with no type conversion; named and blank (`//`)
  common; repeated common names continue the list; `EQUIVALENCE` may extend a common block
  only forward. — ✓ (forterp detects contradictory `EQUIVALENCE`). — ▲ §8.3.1 ("all entities in a
  character common block must be character") is **not** enforced — a mixed char/numeric COMMON
  block is accepted (harmless: the values are stored and read back correctly, and gfortran accepts
  it in every mode incl. `-std=f95`). — ✓ §8.2.3 ("a character entity may be equivalenced only
  with character entities") **is** enforced: a char⟷numeric `EQUIVALENCE` is a hard error on every
  dialect (`RuntimeError`). Its only use is byte type-punning, which the value-slot model can't do
  faithfully (it would silently overwrite the shared slot with one type); gfortran also rejects it
  under `-std=f95` (a "GNU Extension" otherwise).
- **Type-statements (8.4).** `INTEGER`/`REAL`/`DOUBLE PRECISION`/`COMPLEX`/`LOGICAL`/
  `CHARACTER`; `CHARACTER*len` with a statement-wide default, per-entity `*len` overrides,
  per-element length for arrays, and `*(*)` assumed length for dummies / external functions /
  named character constants. — ✓ verified (`CHARACTER*4 A, B*2, C(3)*5` → lengths 4/2/5).
- **`LEN` is the declared length (8.4/15.10).** `LEN(c)` is a compile-time property and does
  not require `c` to be defined. — ✓ **fixed in this review**: forterp had read the runtime
  value and crashed on an undefined CHARACTER variable; it now resolves the declared length
  (substring windows and assumed-length dummies included).
- **IMPLICIT (8.5).** `IMPLICIT typ(a, c-g, …)` letter ranges; precedes other specs except
  `PARAMETER`; overridable by a type-statement. — ✓
- **PARAMETER (8.6).** `PARAMETER (p = const-expr, …)`; the constant expression matches `p`'s
  type; a non-default type/length must be set before the `PARAMETER`; a `PARAMETER` name may
  be a primary or appear in `DATA` but not inside a `FORMAT`. — ✓
- **EXTERNAL / INTRINSIC (8.7–8.8).** declare a name an external/dummy procedure, or an
  intrinsic, so it can be passed as an actual argument; an `EXTERNAL` name overrides a
  like-named intrinsic. — ✓ — ▲ forterp does not *require* `EXTERNAL` merely to pass a
  procedure (lenient).
- **SAVE (8.9).** retains a local's value across `RETURN`/`END`; `/cb/` saves a whole common
  block; listless `SAVE` saves everything; a no-op in a main program. — ✓ (verified a saved
  counter persists across calls).

### §9 DATA statement

- **DATA (§9).** `DATA nlist /clist/ …`; `r*c` repeat counts; an unsubscripted array name
  takes one constant per element (column-major); implied-DO `(…, i=m1,m2[,m3])` with a
  positive trip count; numeric constants convert to the entity's type, character/logical must
  match; a character entity longer than its constant is blank-padded on the right, shorter is
  truncated. Named-common entities are initialized only in `BLOCK DATA`; blank common and
  dummy arguments cannot be initialized. — ✓ (`V/3*7./`, `(V(I),I=1,3)/…/` verified).

### §10 Assignment statements

- **Arithmetic assignment (10.1).** `v = e` converts `e` to `v`'s type (Table 4): `INT`
  truncates toward zero (`I=3.9`→3, `I=-3.9`→−3), `REAL`/`DBLE`/`CMPLX` as appropriate. — ✓
- **Logical assignment (10.2).** `v = e`, `e` logical. — ✓
- **ASSIGN (10.3).** `ASSIGN s TO i` gives integer `i` a statement-label value (the only way),
  for an assigned `GO TO` or a run-time format identifier; `s` must label an executable or
  `FORMAT` statement in the same unit. — ✓ (`ASSIGN`+assigned-`GO TO` verified).
- **Character assignment (10.4).** `v` and `e` may differ in length — `e` is blank-padded
  (`v` longer) or right-truncated (`v` shorter); assigning a substring leaves the rest
  unchanged. — ✓ (`A*2='ABCD'`→`'AB'`, `B*5='XY'`→`'XY   '`).

### §11 Control statements

- **GO TO (11.1–11.3).** unconditional, computed `GO TO (s,…)[,]i` (out-of-range `i` falls
  through as `CONTINUE`), and assigned `GO TO i[,(s,…)]`. — ✓ (computed fall-through verified).
- **Arithmetic IF (11.4).** `IF (e) s1,s2,s3` branches on `e<0`/`=0`/`>0` (`e` integer/real/
  double). — ✓
- **Logical IF (11.5).** `IF (e) st`. — ✓
- **Block IF (11.6–11.9).** `IF(e) THEN` / `ELSE IF(e) THEN` / `ELSE` / `END IF`, IF-level
  matching, no transfer into a block. — ✓ (covered by `test_f77.py`).
- **DO (11.10).** `DO s[,]i = e1,e2[,e3]`; the DO-variable may be integer, real, or double;
  **iteration count `MAX(INT((m2−m1+m3)/m3),0)` — a zero-trip loop when the count is ≤0** (the
  signature F77 change from F66's one-trip minimum); after the loop the DO-variable keeps its
  last value. — ✓ verified: zero-trip `DO K=5,1` runs 0× and leaves K=5; `DO I=1,10` leaves
  I=11; `DO I=1,10,3` runs 4× and leaves I=13. (`zero_trip_do` is on under F77; F66/FORTRAN10
  keep the one-trip rule.)
- **CONTINUE / STOP / PAUSE / END (11.11–11.14).** `STOP [n]` / `PAUSE [n]` take ≤5 digits or a
  character constant; `END` acts as `RETURN` in a subprogram and terminates in a main program.
  — ✓

### §12 Input/output statements

- **The nine statements (§12).** `READ`, `WRITE`, `PRINT`, `OPEN`, `CLOSE`, `INQUIRE`,
  `BACKSPACE`, `ENDFILE`, `REWIND`. — ✓
- **Units & files (12.2–12.5).** external units (a non-negative integer or `*`) and internal
  files (a character variable/array/element/substring); sequential and direct access;
  `[UNIT=]u`, `[FMT=]f`, `REC=rn`. An internal file is sequential-formatted only (no `*`, no
  `REC`). — ✓
- **Control list (12.8).** exactly one unit, at most one of `FMT`/`REC`/`IOSTAT`/`ERR`/`END`;
  array names expand to all elements (column-major); implied-DO lists; `READ(u) N,A(N)` reads
  `N` first. — ✓
- **`IOSTAT=` / `ERR=` / `END=` (12.6–12.7).** after the statement, `IOSTAT` is defined **0 on
  success, positive on an error, negative at end-of-file**; `ERR=s` / `END=s` branch to `s`; a
  read that meets EOF (or error) with none of these specifiers terminates the program. — ✓
  **fixed in this review**: `IOSTAT=` was previously parsed but not assigned on READ/WRITE, so
  the `IF(IOS.LT.0)`/`IF(IOS.GT.0)` idioms saw a stale 0; it is now defined per 12.7.
- **OPEN / CLOSE (12.10.1–2).** `OPEN` specifiers `UNIT`/`FILE`/`STATUS`(OLD/NEW/SCRATCH/
  UNKNOWN)/`ACCESS`(SEQUENTIAL/DIRECT)/`FORM`(FORMATTED/UNFORMATTED)/`RECL`/`BLANK`(NULL/ZERO)/
  `IOSTAT`/`ERR`; `CLOSE` `STATUS`(KEEP/DELETE). — ✓
- **INQUIRE (12.10.3).** by file or by unit: `EXIST`/`OPENED`/`NUMBER`/`NAMED`/`NAME`/`ACCESS`/
  `SEQUENTIAL`/`DIRECT`/`FORM`/`FORMATTED`/`UNFORMATTED`/`RECL`/`NEXTREC`/`BLANK`. — ✓
- **File positioning (12.10.4).** `BACKSPACE` / `ENDFILE` / `REWIND` (sequential units). — ✓
- **Carriage control on printing (12.9.5.2.3).** leading `blank`/`0`/`1`/`+` ⇒ one line / two
  lines / new page / no advance; the control character is not printed. — ✓ on the printer path
  (`carriage_control`); ▲ under the FORTRAN-10 *terminal* model consecutive single spaces are
  not doubled (a documented device-model nuance).

### §13 Format specification

- **Form (13.1–13.2).** `FORMAT` statement or a character format; `([r]ed | ned | [r](fs))…`;
  comma optional around `/`, `:`, and after `P`. Repeatable descriptors `Iw Iw.m Fw.d Ew.d
  Ew.dEe Dw.d Gw.d Gw.dEe Lw A Aw`; non-repeatable `'…' nH Tc TLc TRc nX / : S SP SS kP BN BZ`.
  — ✓
- **Format control & reversion (13.3).** one repeatable descriptor per list item (complex =
  two); on the closing `)` with items remaining, advance a record and revert to the last
  `(` group; reversion preserves the scale factor and S/SP/SS and BN/BZ state. — ✓
- **Positional & control (13.5.1–13.5.8).** `'…'`/`nH` (output only), `T`/`TL`/`TR`/`X`
  (skipped output positions blank-filled, never erased), `/`, `:`, `S`/`SP`/`SS` sign control,
  `kP` scale factor, `BN`/`BZ` blank control. — ✓ (scale-factor rules: F-output ×10ᵏ, E/D mantissa
  ×10ᵏ with exponent −k, suspended for G in F-form, input ÷ unless the field has an exponent).
- **Numeric editing (13.5.9).** input ignores leading blanks, `+` optional, all-blank ⇒ 0, a
  `.` in the field overrides `d`; output right-justified, overflow ⇒ all asterisks, no negative
  signed zero. `Iw`/`Iw.m` (`m=0` of zero ⇒ blanks); F (no leading zeros but the optional `0`
  before `.`); E/D (`[±][0].x…xd` with a **required** exponent sign; `Ew.dEe` exact exponent
  width); G (F- or E-form by magnitude); complex = two descriptors. — ✓ (these are exactly the
  edge cases driven to byte-match gfortran this session: `Iw.0`-of-zero, F leading-zero,
  single-round E/D, G-scale, `Ew.dEe`).
- **L / A editing (13.5.10–13.5.11).** `Lw` accepts optional `.`+`T`/`F` (so `.TRUE.`/`.FALSE.`
  read), outputs `w−1` blanks + `T`/`F`; widthless `A` uses the item's declared length; A-input
  takes the rightmost `len` (w≥len) or left-justifies + pads (w<len); A-output of a CHARACTER
  value right-justifies when `w>len` (leading blanks) and takes the leftmost `w` when `w≤len`.
  — ✓ verified (`A5` of `'HI'` ⇒ `'   HI'`).
- **List-directed (13.6).** values separated by blanks/comma/slash, `r*c` repeat, `r*` null,
  end-of-record acts as a blank; complex `(re,im)` and apostrophe strings may span records; a
  `/` ends input (rest null). Output: integer `Iw`, real/double `0PFw.d` or `1PEw.dEe` by
  magnitude, logical `T`/`F`, complex `(re,im)`, character without apostrophes, each record led
  by a blank. — ✓ (processor-dependent widths validated by the gfortran value-token metric).

### §14 Main program

- **Main program (§14).** an optional `PROGRAM pgm` first statement; exactly one main program;
  execution starts at its first executable; a main program contains no `BLOCK DATA`/`FUNCTION`/
  `SUBROUTINE`/`ENTRY`/`RETURN` and cannot be referenced. — ✓ (`PROGRAM` optional and named).

### §15 Functions and subroutines

- **Procedures (15.1–15.2).** intrinsic functions, statement functions, external functions,
  subroutines; a function reference is a primary in an expression; a `CALL` references a
  subroutine. — ✓ the standard's **no-recursion** rule (§15.5.2 — a subprogram must not
  reference itself directly or indirectly) is enforced: a re-entry raises `IllegalRecursion`
  rather than silently corrupting forterp's static local storage. Set the `recursion` dialect
  knob (`allow_recursion` on the engine) to permit recursion *and* make it correct — each
  activation gets its own snapshot of the unit's locals (COMMON stays shared).
- **Statement functions (15.4).** `f(d,…) = e` after the specifications; dummies scoped to the
  statement; may reference earlier statement functions. — ✓
- **External functions (15.5).** `[type] FUNCTION f(d,…)`; `CHARACTER*len` / `CHARACTER*(*)`
  functions; the function name acts as a result variable defined before `RETURN`/`END`. — ✓
- **Subroutines & CALL (15.6).** `SUBROUTINE s[([d,…])]`, `CALL s[([a,…])]`; an `*` dummy is an
  alternate-return point. — ✓
- **ENTRY (15.7).** alternate entry points in a function or subroutine. — ✓
- **RETURN (15.8).** `RETURN` / `RETURN e` (alternate return — `e` selects the e-th `*`); `END`
  acts as `RETURN`; the definition-status survivors on return are SAVEd entities, blank common,
  still-initially-defined entities, and named common shared with a referencing unit. — ✓
- **Arguments (15.9).** positional association, equal counts, type agreement (except a
  subroutine name or alternate-return specifier); character dummy length ≤ actual; adjustable
  and assumed-size dummy arrays; dummy procedures. — ✓
- **Intrinsic functions (15.10, Table 5).** — ✓ **all 85 standard specific/generic intrinsics
  are present** (the type-conversion, truncation, nearest-whole/integer, absolute-value,
  remaindering, sign-transfer, positive-difference, double-product, max/min, length, index,
  imaginary-part, conjugate, square-root, exponential, logarithm, trigonometric, hyperbolic,
  and lexical-comparison families) with the Table-5 semantics verified (`INT` toward zero,
  `NINT` round-half-away, `MOD`/`SIGN`/`DIM`, `ICHAR`/`CHAR` inverse, `INDEX` first occurrence,
  `LGE`/`LGT`/`LLE`/`LLT` on the ASCII collating sequence). `LEN`'s argument need not be defined
  (Note 11) — the fix recorded in §8.

### §16 Block data

- **Block data (§16).** `BLOCK DATA [sub]` supplies initial values for **named** common blocks
  via `DATA`, using only specification statements; only named-common entities may be
  initialized. — ✓ verified (a `BLOCK DATA` initializes a named block read by the main program).
  — ▲ the "specify all entities of an initialized block" and "≤1 unnamed block-data" rules are
  not enforced (lenient).

### §17 Association and definition

- **Storage sequence (17.1.1).** integer/real/logical = 1 numeric unit; double precision and
  complex = 2 numeric units; character = one unit per character. — ▲ forterp's storage
  association is value-slot-based: `COMPLEX` occupies two slots (`ComplexPairRef`), but `DOUBLE
  PRECISION` occupies one slot, so the *partial-association* cases that overlap a double (or a
  complex half) with a pair of reals are not bit-faithful (rare; the PDP10 word model is
  closer). Same caveat as §2.13.
- **Association (17.1.2–17.1.3).** `COMMON`, `EQUIVALENCE`, `ENTRY`, and argument association;
  total vs partial association. — ✓ (the association mechanisms themselves work; a contradictory
  `EQUIVALENCE` is detected).
- **Definition status (17.2–17.3).** the standard enumerates exactly which events define and
  undefine entities (assignment, input, `DATA`, `ASSIGN`, `RETURN`/`END`, type-mismatched
  association, skipped function side effects, input error/EOF, …). — ▲ forterp does not *track*
  definition status or trap a reference to an undefined entity; it returns whatever the storage
  holds, faithful to the standard's "no predictable value" latitude (array out-of-bounds and
  undefined access are auditable via `forterp.debug.oob_census()`).

### §18 Scopes and classes of symbolic names

- **Scope (18.1).** global entities (main program, common blocks, external functions,
  subroutines, block data) span the executable program; local entities (variable, array,
  constant, statement function, intrinsic function, dummy procedure) belong to one program unit;
  statement-function dummies and `DATA` implied-DO variables have narrower scopes. — ✓
- **Classes & disambiguation (18.2).** with no reserved words, a name's class is fixed by
  context: a common-block name may double as a local variable/array/statement-function name; an
  intrinsic name can be overridden by a dummy argument or `EXTERNAL`; a function name is also a
  result variable in its subprogram. — ✓ forterp resolves these by context (dummy/statement-
  function/`EXTERNAL`/user-unit checked before the intrinsic library), as exercised throughout
  the FCVS corpus. — ▲ the static prohibition on one name occupying two local classes is not
  strictly diagnosed (lenient), and names longer than six characters are accepted with a warning.

### Appendices A–D

- **Appendix A (F66→F77 conflicts).** the 24 incompatibilities with ANSI X3.9-1966 are exactly
  the deltas forterp's dialect axis encodes (F77 vs F66/FORTRAN10): no Hollerith constants under
  F77, all-blank line is a comment, no transfer into a `DO` range, no negative-zero output, no
  unnecessary leading zeros (I/F), a required exponent sign, the 30 added intrinsic names, ≤1
  unnamed block data. The output-format items were the edits driven to byte-match gfortran this
  session; the 30 new intrinsics are all present.
- **Appendix B (section notes).** non-normative clarifications, all consistent with forterp's
  verified behavior (`DO J=J1,J2` with `J1>J2` runs zero times; negative zero ≡ positive zero;
  column-major ordering; label blanks/leading-zeros insignificant; record-count and
  external-vs-intrinsic resolution rules).
- **Appendix C (Hollerith).** F77 deletes the Hollerith type in favor of `CHARACTER`; forterp
  keeps Hollerith on the **F66/FORTRAN10** dialects (the packed-word value model, per the
  recommended C1–C7 rules) and uses `CHARACTER` under **F77** — the dialect axis separates them.
- **Appendix D (subset overview).** the standard defines a *full* and a *subset* level; **forterp
  implements the full language**, so every subset-omitted feature (double precision, complex,
  `PARAMETER`, `ENTRY`, `BLOCK DATA`, list-directed I/O, substrings, concatenation, character
  functions, `LEN`/`CHAR`/`INDEX`, partial association, lower bounds, …) is present.

### Review summary

This map was produced by reading the **entire ANSI X3.9-1978 standard** (all 18 sections +
Appendices A–D) and checking forterp against each rule. Findings:

- **Conformance is strong.** Every section's core semantics are implemented and verified —
  expression evaluation, control flow (incl. the F77 zero-trip `DO`), the full statement set,
  the complete FORMAT edit-descriptor family, the entire I/O model, and **all 85 Table-5
  intrinsic functions** with their specified semantics.
- **Two bugs were found and fixed during the review:** `LEN` of an undefined `CHARACTER`
  variable (§8/§15.10 — must be the declared length), and the `IOSTAT=` specifier never being
  assigned on `READ`/`WRITE` (§12.7 — must be 0 / positive / negative). Both have regression
  tests.
- **A follow-up audit (`tests/test_f77_audit.py`) locks in the subtle rules.** A second,
  skeptical pass re-probed every claim against the live interpreter and added dedicated
  regression tests for the ANSI rules that previously had only incidental (FCVS) coverage:
  `**` right-associativity and `-A**2`, the real-base/integer-exponent rule, the four-tier
  operator-class precedence, real/double `DO` control variables, column-major storage via
  `EQUIVALENCE`, and `Iw.0`-of-zero blanking. No new bugs were found; the only new observation
  is the undiagnosed complex-ordering case noted in §6.3.
- **The documented `▲` divergences are deliberate and benign** — the pluggable value model
  (NATIVE `REAL`≡`DOUBLE PRECISION` precision and `DOUBLE PRECISION` as one value slot; the
  PDP10 target is faithful), non-fatal arithmetic, and untrapped out-of-bounds / undefined
  access. None can mis-run a conforming program; they are the same faithfulness-over-strictness
  choices documented in [§8](#8-conformance--fcvs-77). (Two restrictions the standard places on
  *programs* are now actively enforced under F77 — statement order §3.5 and no-recursion §15.5.2
  — rather than left lenient.)

---

## 11. Non-breaking extensions

§1.4 lets a conforming processor "allow additional forms and relationships **provided that such
additions do not … change the proper interpretation of a standard-conforming program**." The
items below are places where forterp accepts or does *more* than strict ANSI X3.9-1978 — but
because a conforming program never relies on the prohibited or undefined form, **none of them can
change a conforming program's result.** (Contrast the value model — NATIVE `REAL`≡`DOUBLE
PRECISION` precision, `DOUBLE PRECISION` as one storage slot — which *can* affect a conforming
program and is therefore a `▲` divergence in §10, not an extension.)

### On by default

- **Longer names (§2.2).** A name over six characters is accepted (significant to the first six),
  not rejected.
- **Non-fatal arithmetic (§6.6).** Divide-by-zero, `0**0`, `0**negative`, and a negative base to a
  real power do not trap — they yield a value (IEEE `Inf`/`NaN` on NATIVE, FOROTS recovery on
  PDP10). The op is prohibited, so any result conforms.
- **Unchecked array access (§5.4).** An out-of-bounds subscript traverses the `COMMON`/
  `EQUIVALENCE` storage sequence — the deliberate over-/under-indexing idioms reach the
  neighbouring variable (read *and* write) — instead of trapping; it reads 0 only past the whole
  store.
- **Out-of-range substring (§5.7).** A window outside `1 ≤ e1 ≤ e2 ≤ len` is clamped/blank-padded
  rather than trapped.
- **`DOUBLE PRECISION` ⊗ `COMPLEX` arithmetic (§6.1.4).** The Table-2/3 "Prohibited" combination is
  promoted to the double-complex result (identical to gfortran in every mode).
- **Mixed `COMMON` (§8.3.1).** A common block may hold both character and numeric entities; each is
  stored and read back correctly.

### Opt-in (off by default)

- **`recursion`** *(dialect knob)* — permit a subprogram to reference itself, with correct
  per-activation local storage (§15.5.2). Off by default, a re-entry is a hard error (the static
  store would otherwise corrupt silently).
- **`unlimited_rank`** *(dialect knob)* — lift the seven-dimension array cap (§5.1).
- **target value model** *(`NATIVE` vs `PDP10`)* — selects the result of undefined arithmetic
  (IEEE vs FOROTS) and the storage/precision model; see §10 §2.13.

### The inverse — a conformance check

- **`bounds_check`** *(dialect knob)* — turns the unchecked array/substring latitude above into
  hard errors (`OobError`, the gfortran `-fcheck=bounds` analog). Not an extension — a strictness
  gate for *testing* whether a program stays in bounds.

### Dialect supersets

The `FORTRAN10` dialect adds the full DEC FORTRAN-10 V5 superset — octal `"…` literals, `DO WHILE`,
`.XOR.` and the symbolic relationals (`==` `<` `>`), the `A(lo/hi)` bound form, tab-format source,
`TYPE`/`ACCEPT`/`ENCODE`/`DECODE` and random-access I/O — **all off under `F77`** (see
[§7](#7-what-the-f77-dialect-does-not-add) and [§9](#9-the-f77-dialect-knobs)).

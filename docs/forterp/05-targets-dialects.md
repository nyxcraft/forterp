# Targets & dialects
## The two axes: target and dialect

They are orthogonal — any pairing is valid.

**Target** — the machine value model (integer word width + overflow, the logical-truth
convention, the character codec):

- `forterp.NATIVE` — a clean 64-bit host: 64-bit two's-complement, 8-bit ASCII, `.TRUE.`=1
  with boolean logicals. **The default**, for running standard F66 portably.
- `forterp.PDP10` — the DEC FORTRAN-10 machine: 36-bit two's-complement, 5×7-bit packed
  ASCII, `.TRUE.`=−1 with bit-wise logicals. The faithful, validated opt-in.
- `forterp.LP64LE` — a 64-bit little-endian IEEE machine (32-bit `INTEGER`/`REAL`, 64-bit
  `DOUBLE`) — matches gfortran on x86_64; most useful with `word_memory` (below).
- `forterp.VAX` — a provisional, unvalidated 32-bit guess.
- `forterp.Target(word_bits=…, chars_per_word=…, bits_per_char=…, logical_true=…,
  bitwise_logic=…, little_endian=…, truth=…, mem_model=…)` — build your own.

```python
forterp.run_source(src, target=forterp.PDP10)   # 36-bit arithmetic, packed ASCII
```

**Faithful type punning** — by default `COMMON`/`EQUIVALENCE` cells hold typed values, so reading
the same storage as a different type isn't bit-faithful. Pass `word_memory=True` (PDP10/LP64LE/VAX
only; CLI `--word-memory`) to store such blocks as raw machine words/bytes and reinterpret on
access, so a `REAL` read as an `INTEGER` yields the genuine machine word — validated against a real
KL10 (PDP10) and gfortran (LP64LE). Off by default: it changes the `commons` representation to raw
words and costs ~2× per `COMMON` access. See the [FORTRAN 66 manual, Appendix C](../fortran66/C-forterp-extensions.md).

```python
forterp.run_source(src, target=forterp.PDP10, word_memory=True)  # bit-faithful punning
```

**Dialect** — the front-end language. `forterp.F66` is strict ANSI X3.9-1966 and genuinely
*rejects* non-F66 constructs; `forterp.FORTRAN10` is the DEC superset (octal, tab-format,
`!` comments, apostrophe strings, random-access I/O, free-form input, the DEC intrinsic
library); `forterp.F77` is ANSI X3.9-1978 — the `CHARACTER` type, the block `IF`,
list-directed and keyword-driven I/O, internal files, `INQUIRE`, `PARAMETER`/`SAVE`, and
`.EQV.`/`.NEQV.`. See the **[FORTRAN 77 reference manual](../fortran77/README.md)** for the
language itself, and the F77 dialect knobs just below.

**SourceOptions** — orthogonal to the dialect; it copes with imperfect *input*, not a
language variant. `forterp.SourceOptions(recover_shifted_cols=True)` keeps statement text
that spilled past column 72 in a mechanically re-indented deck. The default is no recovery
(columns 7–72, sequence field dropped).

### The F77 dialect knobs

A `Dialect` is a set of front-end flags; `forterp.F77` turns on exactly the subset ANSI
X3.9-1978 standardized (several were split out of the broader DEC bundles so F77 gets the
standardized feature without the rest of the DEC extension):

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
| `f77_intrinsics` | the ANSI F77 intrinsic additions (generic `LOG`/`MAX`/`MIN`, `TAN`/`ASIN`/…, the `D…` specifics, `NINT`/`ANINT`, `LEN`/`CHAR`/…) |
| `dec_library` | the DEC-only library: DEC intrinsics (`LSH`/`ROT`, degree trig, `DOUBLE COMPLEX` helpers) + DEC subprograms (`RAN`/`DATE`/…) + the DEC terminal CR-LF wrap |
| `uuo_library` | TOPS-10 monitor UUOs callable from FORTRAN (`OUTSTR`/`SLEEP`/`GETTAB`/…) — PDP-10-specific |
| `strict_stmt_order` | enforce "specifications before executables" (§3.5) as a hard error |
| `carriage_control` | **off** for F77 — standard output is a terminal, not a line printer |

The strict/relax knobs `recursion`, `unlimited_rank`, and `bounds_check` are off by default on
every dialect; see [reference manual Appendix D](../fortran77/D-forterp-extensions.md).

Of the three library tiers, only `f77_intrinsics` is on for F77; `dec_library` and
`uuo_library` are `FORTRAN10`-only, so strict F77 accepts neither `LSH` nor `CALL SLEEP`.

Notably **off** for F77 (on only for `FORTRAN10`): `do_while`, `dec_operators` (`.XOR.`,
`==`/`<`/`>`), `slash_dim_bound` (`A(lo/hi)`), `octal_quote`, `tab_format`, `inline_comment`
(`!`), `extended_io` (`TYPE`/`ACCEPT`/`ENCODE`/`DECODE`, random-access), `free_form_input`,
`dec_library`, `uuo_library`.

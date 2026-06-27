# Architecture

How the `forterp` interpreter is built and why it's built that way. This is the architecture
companion to the user-facing [FORTRAN 66 reference manual](../fortran66/README.md); it's for
someone modifying the interpreter, not someone writing FORTRAN.

---

## What forterp is, and the one decision everything follows from

`forterp` is a **tree-walking interpreter** for FORTRAN-66. It parses `.FOR` source to an AST
and executes the AST directly — it does not compile to bytecode or transpile to Python.

The load-bearing decision is that **the machine value model is pluggable**, owned by a
`Target` the engine routes every value through: the integer word width and overflow, the
logical-truth convention, and how characters pack into words. The core is
representation-agnostic; a `Target` makes it concrete. Two ship:

- **`NATIVE`** (the default) — a clean 64-bit host machine for running standard
  FORTRAN-66: 64-bit two's-complement integers, 8-bit ASCII packed into words, `.TRUE.`=1
  tested as *nonzero*, with *boolean* logical operators.
- **`PDP10`** — a *faithful* DEC FORTRAN-10 model, whose priority is to run 1970s PDP-10
  code the way the machine ran it, quirks included: a word is a *signed 36-bit
  two's-complement* int, character/Hollerith data packs 5×7-bit per word and reads back as
  a signed 36-bit int (so comparisons match PDP-10 `CAM` arithmetic), `.TRUE.` is −1 tested
  as *sign-negative*, and `.AND./.OR.` are *bit-wise* on the word.

In both, `REAL` is a Python `float` and `COMPLEX` a Python `complex`. Two further targets
ship:

- **`LP64LE`** — a 64-bit little-endian IEEE machine matching gfortran on x86-64. Its
  faithful type punning (with `word_memory`, §9) byte-matches gfortran, so it is the
  oracle-validated portable counterpart to `PDP10`.
- **`VAX`** — little-endian integers, middle-endian `F_floating`/`D_floating`. A
  **provisional, unvalidated** guess implemented from the published format (no VAX oracle
  yet; a probe deck is staged for when one exists).

Everything else in the design serves running real code against the chosen model without
that model leaking into places it shouldn't — see §6 on the `Target` seam.

---

## The pipeline

```
.FOR text
   │   source.py    fixed-form card reader  → logical statements   (dialect-gated)
   ▼
[Statement(label, text, line), …]
   │   lexer.py     tokenize statement text → tokens               (dialect-gated)
   ▼
[Token(kind, value), …]
   │   parser.py    recursive-descent       → AST (ast_nodes.py)
   ▼
{name: ProgramUnit}              one per PROGRAM/SUBROUTINE/FUNCTION/BLOCK DATA
   │   engine.py    _build(): COMMON layout, EQUIVALENCE, DATA, label tables, ENTRY
   ▼
Engine.run(Frame(unit, args))    tree-walking execution
```

### Source reader — `source.py`

Fixed-form is genuinely a *card* format, so this stage is its own pass, not part of the
lexer. It turns column-oriented text into a list of `Statement(label, text, line)`:

- Column 1 `C`/`*` → comment; columns 1–5 label; column 6 non-blank → continuation
  (joined onto the previous statement); 7–72 body; 73–80 sequence field dropped
  unconditionally (as both real F10/F66 compilers do).
- **DEC extensions, gated by the `Dialect`:** TAB-format lines (`_tab_split`) and trailing
  `!` inline comments (`_split_inline_comment`). `;` statement separation is handled here
  too (`_split_semicolons`).
- **Source recovery, via `SourceOptions` (NOT the dialect):** `recover_shifted_cols` keeps
  statement text that spilled past col 72 in re-indented decks (`_trim_seqfield`). It copes
  with imperfect *input*, not a dialect of the *language*, so it sits off the dialect axis;
  the default drops 73+ (matching real FORTRAN-10).
- `INCLUDE`/related directives are resolved by `expand_includes` after the scan.

### Lexer — `lexer.py`

`tokenize(text, dialect=F66)` produces `Token(kind, value)` for the statement body.
The `Dialect` gates the DEC lexical extensions — octal `"nnn` literals and the `READ(u'r)`
random-access apostrophe. Numbers (`_read_number`), strings/Hollerith (`_read_string`),
and the dotted operators `.EQ./.AND./.TRUE.` (`_match_dot`) are recognized here.

> **Blanks-insignificance (F66 §3.1.6)** is the awkward one — in F66 blanks inside tokens
> are not significant (`GO TO` == `GOTO`). Rather than complicate the lexer, the parser
> retries with blanks stripped (`_strip_blanks` / `_respace_stmt`) when a first parse
> fails. This is why some logic lives in `parser.py:fix_tokens`/`_strip_blanks`.

### Parser — `parser.py`

Hand-written recursive descent. Expressions use a precedence ladder, lowest to highest:
`p_equiv` (`.EQV./.NEQV./.XOR.`) → `p_or` → `p_and` → `p_not` → `p_rel` → `p_add` →
`p_mul` → `p_unary` → `p_pow` (right-assoc `**`) → `p_primary`. Statements are dispatched
in `parse_exec`; the specification statements (`COMMON`, `EQUIVALENCE`, `DATA`, `NAMELIST`,
`DEFINE FILE`, type decls) attach their info to the `ProgramUnit`. Symbolic names are
truncated to 6 characters here (`_name6`). The output AST nodes are the dataclasses in
`ast_nodes.py` (`Assign`, `Goto`, `Do`, `IfBranch`, `Call`, `IoStmt`, `ImpliedDo`,
`ProgramUnit`, …).

### Engine — `engine.py`

The execution core (~3,300 lines). Two halves: a one-time **`_build()`** that lays out
storage (COMMON/EQUIVALENCE/DATA, label and DO-terminal tables, ENTRY), and the
**execution** machinery (expression eval, the statement dispatcher, calls, and the
terminal/file/random/NAMELIST/internal-file I/O). Two self-contained concerns were lifted
into leaf modules to keep this one focused: the storage **reference** classes and the
faithful unchecked-OOB model live in `refs.py`, and the **intrinsic** library + the scalar
arithmetic primitives in `intrinsics.py` (see [§12 module map](12-internals-reference.md)).
The value model is never hard-coded — every value routes through `self.tgt` (§6).

---

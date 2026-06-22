# forterp — design document

How the `forterp` interpreter is built and why it's built that way. This is the architecture
companion to the user-facing [FORTRAN66.md](FORTRAN66.md); it's for
someone modifying the interpreter, not someone writing FORTRAN.

---

## 1. What forterp is, and the one decision everything follows from

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

In both, `REAL` is a Python `float` and `COMPLEX` a Python `complex`. A third target,
`VAX` (32-bit, little-endian char packing, low-order-bit truth test), is a **provisional,
unvalidated** guess — it exercises the seam's `little_endian` and `truth` knobs but has
not been checked against a real VAX FORTRAN. Everything else in the design serves running
real code against the chosen model without that model leaking into places it shouldn't —
see §6 on the `Target` seam.

---

## 2. The pipeline

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

### 2.1 Source reader — `source.py`

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

### 2.2 Lexer — `lexer.py`

`tokenize(text, dialect=F66)` produces `Token(kind, value)` for the statement body.
The `Dialect` gates the DEC lexical extensions — octal `"nnn` literals and the `READ(u'r)`
random-access apostrophe. Numbers (`_read_number`), strings/Hollerith (`_read_string`),
and the dotted operators `.EQ./.AND./.TRUE.` (`_match_dot`) are recognized here.

> **Blanks-insignificance (F66 §3.1.6)** is the awkward one — in F66 blanks inside tokens
> are not significant (`GO TO` == `GOTO`). Rather than complicate the lexer, the parser
> retries with blanks stripped (`_strip_blanks` / `_respace_stmt`) when a first parse
> fails. This is why some logic lives in `parser.py:fix_tokens`/`_strip_blanks`.

### 2.3 Parser — `parser.py`

Hand-written recursive descent. Expressions use a precedence ladder, lowest to highest:
`p_equiv` (`.EQV./.NEQV./.XOR.`) → `p_or` → `p_and` → `p_not` → `p_rel` → `p_add` →
`p_mul` → `p_unary` → `p_pow` (right-assoc `**`) → `p_primary`. Statements are dispatched
in `parse_exec`; the specification statements (`COMMON`, `EQUIVALENCE`, `DATA`, `NAMELIST`,
`DEFINE FILE`, type decls) attach their info to the `ProgramUnit`. Symbolic names are
truncated to 6 characters here (`_name6`). The output AST nodes are the dataclasses in
`ast_nodes.py` (`Assign`, `Goto`, `Do`, `IfBranch`, `Call`, `IoStmt`, `ImpliedDo`,
`ProgramUnit`, …).

### 2.4 Engine — `engine.py`

The big module (~1700 lines). Two halves: a one-time **`_build()`** that lays out storage,
and the **execution** machinery.

---

## 3. The memory model

FORTRAN-66 has no stack-allocated locals and no heap. forterp mirrors that:

- **COMMON blocks are flat word arrays** (`self.commons[block] = [...]`). Storage
  association is real: each unit's variables are mapped onto *offsets* into the block, so
  two units with different variable layouts overlay the same words. `EQUIVALENCE` is laid
  out by `_layout_equivalence`, which also extends/aliases COMMON.
- **Locals are static per unit.** FORTRAN-10 allocated locals statically, so they *persist
  across calls* — forterp keeps them in the `UnitRT`, not in the call frame. This matches
  FORTRAN-10, and programs sometimes depend on it.
- **Arguments are passed by reference.** The engine never copies a value into a callee; it
  passes a *reference cell* so the callee can write back. The reference abstraction has
  several shapes: `CellRef` (into an array/COMMON store), `DictRef` (a local), `TempRef`
  (an expression result with nowhere to write), `ProcRef` (a passed subprogram name), and
  `ArrayView` (a based view for array arguments with adjustable dimensions). `array_size`
  / `linidx` implement column-major indexing.
- **`DATA` initialization** runs at build time (`_apply_data`, `_const_eval_int`), with
  repeat counts.

Out-of-bounds access mirrors the real machine rather than guarding defensively: `OobError`/`_oob_event`
reproduce the documented 1978 behavior (e.g. an `ENEMYM` array overrun that read adjacent
PDP-10 memory) rather than raising a clean Python error.

---

## 4. The control model

FORTRAN's arbitrary `GO TO`s mean a structured AST-of-blocks is the wrong shape. Instead a
unit is a **flat statement list with a program counter**, a **label table**, and a
**DO-stack**:

- `exec_stmt(s, frame)` is a type-dispatch over the statement nodes. It returns a *control
  signal*: `None` (fall through to next statement), `Goto(label)`, `Ret(alt)`, or `Stop()`.
- `run(frame)` is the loop: fetch `code[pc]`, execute, then act on the signal. `Goto`
  resolves the label to a PC and **unwinds any DO loops the new PC has left**. `Ret`
  returns (optionally an alternate-return selector); `Stop` raises `StopExecution`.
- **DO loops are F66 semantics, deliberately.** The body runs *at least once* (one-trip),
  and on exit the index variable **keeps its last value**. `exec_do` pushes a `DoFrame`;
  `_do_bookkeep` handles the loop-back/termination when the PC reaches the terminal label.
  This differs from F77 and tests depend on it.
- Arithmetic `IF` branches on sign (`<0 / ==0 / >0`); logical truth everywhere goes through
  `self.tgt.truthy` (the target's convention — sign-negative on PDP-10, nonzero on NATIVE),
  never Python truthiness.

Subprograms: each unit has a `UnitRT` (compiled code + labels + DO-terminals + assigned-
label scan). A call builds a `Frame`, binds actuals to formals by reference (`bind_args`),
and runs. `ENTRY` points (`_entry_frame`, `self.entries`) and single-line statement
functions (`_call_stmt_func`) are supported.

---

## 5. I/O and FORMAT

- `do_io` handles `READ`/`WRITE`/`PRINT`/`TYPE`/`ACCEPT` and the file-control statements,
  walking the io-list (including `ImpliedDo`).
- **`fmt.py` is a self-contained FORMAT engine**: `parse_format` builds an item list,
  `render(items, values)` produces formatted output (the `_ifmt/_rfmt/_efmt/_gfmt/_afmt`
  edit-descriptor renderers + `_Record` for column/tab tracking + `apply_carriage` for
  carriage control), and `read_values` parses an input record under format control.
- **Unformatted (binary) I/O goes through a seam** (see §6): the engine calls
  `self._binio()` rather than importing the FOROTS codec directly.
- `ENCODE`/`DECODE` (`do_encdec`) is internal-buffer formatted I/O.
- **Default device assignments** (V5 Table 10-1): a unit used but never `OPEN`ed routes
  to a default device — units 3 and 6 to the line printer (the injected `printer`
  service), unit 5 to terminal/card input (the injected `readline`).

---

## 6. The four seams (why forterp is standalone and composable)

The whole point of the package breakup was to push the PDP-10/DEC/host specifics out of
the core through explicit seams, so `forterp` imports **no** sibling package and can be
retargeted:

| Seam | Mechanism | Default |
|------|-----------|---------|
| **Machine value model** | `Engine(target=…)`, a `Target` object; the engine routes its wrap / pack / truthy / logical sites through `self.tgt` | `NATIVE` (64-bit, 8-bit ASCII, boolean logicals) default; `PDP10` (36-bit, 5×7-bit, `.TRUE.`=−1, bit-wise) for PDP-10 fidelity |
| **Front-end dialect** | `Dialect` threaded through `scan_file`/`tokenize`/`parse_units` (and `free_form_input` to the engine) | `F66` (default, ANSI) vs `FORTRAN10` (DEC superset) |
| **OPEN devices** | `eng.register_device(name, fn)`; the core knows only TTY + ordinary files | empty (games register e.g. `GAM:`) |
| **Unformatted-I/O codec** | `eng.binio`, installed by `install_runtime`; engine calls `self._binio()` (clear error if absent) | `forterp.forbin` (FOROTS records + DEC-10 float) |

Beyond those four, the core takes **environment services** as injected callables rather
than reaching for the OS: `emit` (terminal out), `readline` / `getch` (terminal in),
`printer` (LPT spool), `now` (clock), and a seeded `rng`. Determinism is therefore an
*input* (fixed clock + seeded RNG by default), which is what makes the test suite stable.

**Composition.** `install_runtime(eng)` wires the DEC FORTRAN-10 runtime onto a bare core:
it registers `STDLIB` (the library subroutines in `forlib.py`) and sets `eng.binio`.
`make_engine` / `run_source` in `__init__.py` do core + runtime in one call.

---

## 7. Intrinsics vs. library builtins

Two distinct tables:

- **`INTRINSICS`** (in `engine.py`) — the FORTRAN intrinsic *functions* (`INT`, `SQRT`,
  `MOD`, `ABS`, `IAND`/`LSH`, the `C*` complex ops, …), evaluated inline via
  `_apply_intrinsic`. These are pure value→value lambdas.
- **`STDLIB`** (in `forlib.py`) — the library *subroutines* (`TIME`, `DATE`, `EXIT`,
  `ERRSNS`/`ERRSET`, `RAN`/`SETRAN`, sense-light ops, …), registered via
  `register_builtins`. These take `(eng, frame, arg_nodes)` so they can touch engine state
  and write back through references.

> **Target-awareness (done):** the integer-valued intrinsics follow the engine's `Target`
> — `_apply_intrinsic` re-applies `self.tgt.wrap` to `INT`/`IFIX`/`IDINT`/`NINT` results,
> and `_lsh` takes the target (shift width from `tgt.mask`). The math/`C*` intrinsics are
> pure value→value and target-neutral. The whole value model — integer wrap, the logical
> algebra, the character codec, the `O`-descriptor width, and Hollerith `PARAMETER`
> constants (packed at use via `Engine._const_value`, not at parse time) — now routes
> through the `Target`; there are no known PDP-10 pins left in the core.

---

## 8. Module map

What each module **owns** (responsibilities age better than line counts):

| Module | Owns |
|--------|------|
| `engine.py` | tree-walking execution; storage layout in `_build` (COMMON/EQUIVALENCE/DATA, label + DO-terminal tables, ENTRY); expression eval + control flow; terminal/file/random/NAMELIST/ENCODE-DECODE I/O; the inline intrinsic table; routing the value model through `self.tgt` |
| `parser.py` | recursive-descent parse → AST; statement + spec-statement dispatch; blanks-insignificance parse-retry; 6-char name truncation; `pack5` |
| `fmt.py` | the FORMAT engine: `parse_format` → items, `render` (output), `read_values` (input), carriage control |
| `source.py` | fixed-form card reader: column fields, continuation, tab-format, inline `!`, `;`-split, `INCLUDE` (`scan_file`/`scan_text`) |
| `ast_nodes.py` | the AST dataclasses + the `Expr`/`IoItem`/`FormatRef`/`Dims` contract aliases |
| `lexer.py` | tokenizer; gates the DEC lexical extensions on the `Dialect` |
| `forlib.py` | `STDLIB` — the FORTRAN-10 library subroutines (TIME/DATE/EXIT/ERRSNS/RAN/…) |
| `forbin.py` | FOROTS unformatted-record framing (LSCW) + DEC-10 float — the `binio` codec |
| `diagnostics.py` | V5 Appendix-F message rendering (`?FTNxxx` / `%FTNxxx`) |
| `target.py` | the `Target` value-model seam (`PDP10` / `NATIVE` / `VAX`) |
| `dialect.py` | the `Dialect` front-end seam (`F66` default / `FORTRAN10` superset) |
| `__init__.py` | public API + `install_runtime` / `make_engine` / `parse_source` / `run_source` |

---

## 9. Testing

Tests run through the **real pipeline** (source reader → lexer → parser → engine), never
against internal mocks — see `tests/conftest.py` (`run()`/`run_int()` compile a snippet and
hand back the `Engine` to inspect COMMON). Conformance is the **FCVS** corpus
(`tests/fcvs/`, driven by `tests/fcvs_runner.py`): each audit routine is self-checking and
prints a PASS/ERROR tally to the line printer, which the runner captures and parses. The
corpus is **curated F66**: the F77 audit routines (those using the `CHARACTER` type, absent
from F66) were removed from the original 192-file FCVS set, so every file in `tests/fcvs/`
parses and runs — a parse failure is now a regression, not "out of scope." The corpus is
run across **both seams**: the value-model axis (pinned to `PDP10`, the target the
unit suite asserts, and again under the default `NATIVE`) and the front-end-dialect axis
(under `F66`, since the audits are pure ANSI). All runs produce the identical conformance
aggregate — independent evidence both seams preserve standard behavior. 471 tests pass
standalone.

---

## 10. Engine runtime state (reference)

What an `Engine` carries while running — the things `_file_ctl`, `do_io`, `eval`, and
`call_*` operate on:

- **`self.units`** — `{name: ProgramUnit}`, the parsed AST (one per PROGRAM / SUBROUTINE /
  FUNCTION / BLOCK DATA).
- **`self.rts`** — `{name: UnitRT}`, the compiled per-unit runtime built by `_build`: the
  executable `code` list, the label→PC table, the DO-terminator label set, the
  `common_map` (name → block + offset), and **static** `local_scalars` / `local_arrays`.
  FORTRAN-10 locals persist across calls, so they live here, *not* in the frame.
- **`Frame`** — one call activation: its `UnitRT`, the actual-argument bindings (`args`:
  dummy name → reference), a program counter `pc`, and a `do_stack` of `DoFrame`s.
  `run(frame)` is the fetch-execute loop.
- **`self.commons`** — `{block: [word, ...]}`, flat per-block stores; storage association
  maps each unit's variables onto offsets here (`EQUIVALENCE` extends/aliases a block).
- **`self.io`** — `{unit: state}`; the state shape depends on its `"mode"`: `term`
  (terminal), `lpt` (line printer), `r` / `w` (sequential records `{recs, pos, path}`,
  `+ "text": True` for a formatted text file), `random` (record-indexed `{recs, pos,
  assoc}`). Unformatted records are plain value-lists; the FOROTS `binio` codec encodes
  them only when writing a real file — there is no separate "binary" mode.
- **References** (the by-reference argument abstraction): `CellRef` (a slot in an
  array/COMMON store), `DictRef` (a local scalar), `TempRef` (an expression result with
  nowhere to write back), `ProcRef` (a passed subprogram name), `ArrayView` (a based view
  over an array argument, resolving adjustable dimensions per call).

---

## 11. How to change things (maintainer recipes)

Each entry is the trail to follow. Add a test through the **real pipeline**
(`tests/`, via `conftest.run` / `run_int`), plus an FCVS-grade check for conformance.

- **Add a syntax form** — recognize the token in `lexer.py` (gate it on the `Dialect`
  if it's an extension), parse it in `parser.py` (a `parse_*` method + a branch in the
  statement dispatch), and execute it in `engine.exec_stmt`. A new node shape goes in
  `ast_nodes.py`.
- **Add a statement node** — a dataclass in `ast_nodes.py` (subclass `Stmt`), produced by
  `parser.py`, handled in `engine.exec_stmt`.
- **Add an intrinsic** — a pure value→value entry in `engine.INTRINSICS` (the lambda takes
  the arg-value list `a`). If it returns an integer that must wrap to the target word, add
  its name to `_INT_RESULT`; a width-dependent op (like `LSH`) routes through `self.tgt`
  in `_apply_intrinsic`.
- **Add a library subroutine** — a `b_NAME(eng, frame, arg_nodes)` function in `forlib.py`,
  listed in the `STDLIB` table; it may touch engine state and write back via
  `eng.arg_ref(...)`. `install_runtime` registers `STDLIB`.
- **Add a FORMAT descriptor** — extend `fmt.parse_format` (emit an `Item`), render it in
  `_render_one`, read it in `read_values`. The `target` is already threaded in for cases
  where width/packing/logical-truth matters.
- **Add a target or dialect knob** — a value-model property goes on `Target` (`target.py`)
  and must be routed through `self.tgt` in the engine, never hardcoded; a front-end option
  goes on `Dialect` (`dialect.py`), gated in `source.py` / `lexer.py` and threaded via
  `parse_units`.
- **Where tests go** — `tests/test_*.py` exercise the full pipeline; value-model behavior
  belongs in `test_native_target.py` (NATIVE vs PDP10), dialect gating in `test_dialect.py`,
  and conformance through the FCVS corpus.

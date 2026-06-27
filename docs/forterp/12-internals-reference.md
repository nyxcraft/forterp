# Internals reference
## Module map

What each module **owns** (responsibilities age better than line counts):

| Module | Owns |
|--------|------|
| `engine.py` | tree-walking execution; storage layout in `_build` (COMMON/EQUIVALENCE/DATA, label + DO-terminal tables, ENTRY); expression eval + control flow; terminal/file/random/NAMELIST/ENCODE-DECODE I/O; routing the value model through `self.tgt`. (The storage Ref classes live in `refs.py`, the intrinsic library in `intrinsics.py`.) |
| `refs.py` | storage references + the faithful unchecked-OOB model: the `CellRef`/`ComplexPairRef`/`DecDoublePairRef`/`DoubleComplexPairRef`/`WordRef`/`ArrayView`/… lvalue handles; `oob_read`/`oob_write` and their `word_memory` counterparts `wmem_read`/`wmem_write`; `linidx`/`array_size` |
| `intrinsics.py` | the intrinsic-function library — the `INTRINSICS` table split into the `_F66_INTRINSICS` / `_F77_INTRINSICS` / `_DEC_INTRINSICS` tiers — plus the `trunc_div`/`fort_mod` arithmetic primitives |
| `parser.py` | recursive-descent parse → AST; statement + spec-statement dispatch; blanks-insignificance parse-retry; 6-char name truncation; `pack5` |
| `fmt.py` | the FORMAT engine: `parse_format` → items, `render` (output), `read_values` (input), carriage control |
| `source.py` | fixed-form card reader: column fields, continuation, tab-format, inline `!`, `;`-split, `INCLUDE` (`scan_file`/`scan_text`) |
| `ast_nodes.py` | the AST dataclasses + the `Expr`/`IoItem`/`FormatRef`/`Dims` contract aliases |
| `lexer.py` | tokenizer; gates the DEC lexical extensions on the `Dialect` |
| `forlib.py` | `STDLIB` — the DEC library subroutines (TIME/DATE/EXIT/ERRSNS/RAN/…); installed when the dialect's `dec_library` is on (FORTRAN-10) |
| `uuolib.py` | `UUOLIB` — the TOPS-10 monitor UUOs (OUTSTR/OUTCHR/MSTIME/SLEEP/GETTAB); installed when the dialect's `uuo_library` is on (FORTRAN-10) — so strict F77 does *not* get them |
| `hostlib.py` | the host-routine authoring layer: the `@fcall`/`@uuo`/`@builtin` decorators + arg modes (`IN`/`INT`/`STR`/`OUT`/`ARRAY`), `OutRef`, `builtins_in`, and the baseline injectable `Monitor` facade |
| `forbin.py` | FOROTS unformatted-record framing (LSCW) + DEC-10 float (incl. the two-word DOUBLE PRECISION doubleword) — the `binio` codec |
| `wordmem.py` | word-addressable typed memory for faithful cross-type punning (`word_memory`): the `Pdp10WordMemory` / `Lp64LeByteMemory` / `VaxByteMemory` per-target codecs (see §3.1) |
| `diagnostics.py` | V5 Appendix-F message rendering (`?FTNxxx` / `%FTNxxx`) |
| `target.py` | the `Target` value-model seam (`PDP10` / `NATIVE` / `LP64LE` / `VAX`) |
| `dialect.py` | the `Dialect` front-end seam (`F77` default / `F66` strict / `FORTRAN10` superset) |
| `__init__.py` | public API + `install_runtime` / `make_engine` / `parse_source` / `run_source` |

---

## Engine runtime state (reference)

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

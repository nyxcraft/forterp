# The memory model

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

Out-of-bounds access mirrors the real machine rather than guarding defensively: an OOB read
yields `0` and an OOB write is dropped — the documented 1978 behavior (e.g. an `ENEMYM` array
overrun that read adjacent PDP-10 memory) — rather than raising a clean Python error. A tool
can *observe* this without changing it through the public census API in `forterp.debug`:
`oob_census()` (a context manager yielding the OOB reads/writes and per-site log for the
block), the standalone `set_oob_mode` / `oob_mode` / `oob_counts` / `oob_log`, or `"raise"`
mode to turn an overrun into an `OobError` for a checker or fuzzer.

### Faithful type punning — the word-addressable memory model (`wordmem.py`)

By default a `COMMON`/`EQUIVALENCE` cell holds a **typed Python value** (an `int` for `INTEGER`,
a `float` for `REAL`, a `complex` for `COMPLEX`). That's fast and clean, but it isn't *bit*-faithful
when a program **puns** storage — reads the same words as a different type (the classic `EQUIVALENCE
(X, K)` with `X` real and `K` integer, to look at a float's bits). A `REAL` cell holding a host
float can't be reinterpreted as the genuine machine word.

The opt-in **`word_memory`** mode (engine flag / `--word-memory`; off by default) fixes this for the
value-model targets. A storage-associated block becomes a **raw store** and every access goes through
a **per-type codec** keyed on the *accessing* type, so the same words read as different types
reinterpret the bits exactly as the real machine does. The codec is the target's, selected by
`Target.mem_model`, behind a tiny uniform interface — `alloc(n)`, `units(type)`, `read(store, off,
type)`, `write(store, off, type, val)` — so the engine stays representation-agnostic (it only knows
types and offsets; the codec owns the bits and the addressable unit, word vs byte):

- **`Pdp10WordMemory`** (`mem_model="pdp10"`) — a list of 36-bit words; floats via the KL10 codec in
  `forbin`. Validated bit-for-bit against a real PDP-10 (SIMH KS10, DEC FORTRAN-10).
- **`Lp64LeByteMemory`** (`mem_model="lp64le"`) — a `bytearray`; floats via Python `struct` in the
  little-endian LP64/IEEE layout. Byte-matches gfortran on x86_64.
- **`VaxByteMemory`** (`mem_model="vax"`) — a `bytearray`; LE integers and middle-endian (word-
  swapped) `F`/`D_floating`. Best-effort, **unvalidated** (no VAX oracle yet).

`COMPLEX`/`DOUBLE PRECISION`/`DOUBLE COMPLEX` occupy two/two/four storage units (`_member_words`
sizes them in the codec's unit), so block offsets stay accurate; the engine routes the
storage-associated read/write/array/argument paths through the codec (`WordRef` / `WordArrayView`)
when `word_memory` is on, and keeps the fast typed-cell path otherwise. It is off by default because
it changes the observable `commons` representation (raw words/bytes, not typed values) and costs
~2× per `COMMON` access; locals — never aliased — always stay typed and fast. The faithful single/
double splitting of `DOUBLE` is a PDP10/LP64/VAX concern; on `NATIVE` (no `mem_model`) a `DOUBLE`
stays one host float with a zero shadow. This layer is the substrate the planned macroterp bridge's
word-level memory will build on.

---

# Control flow & I/O
## The control model

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

## I/O and FORMAT

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

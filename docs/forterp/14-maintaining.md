# Maintainer recipes
## How to change things (maintainer recipes)

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

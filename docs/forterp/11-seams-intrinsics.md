# Seams & intrinsics
## The four seams (why forterp is standalone and composable)

The whole point of the package breakup was to push the PDP-10/DEC/host specifics out of
the core through explicit seams, so `forterp` imports **no** sibling package and can be
retargeted:

| Seam | Mechanism | Default |
|------|-----------|---------|
| **Machine value model** | `Engine(target=…)`, a `Target` object; the engine routes its wrap / pack / truthy / logical sites through `self.tgt` | `NATIVE` (64-bit, 8-bit ASCII, boolean logicals) default; `PDP10` (36-bit, 5×7-bit, `.TRUE.`=−1, bit-wise) for PDP-10 fidelity |
| **Front-end dialect** | `Dialect` threaded through `scan_file`/`tokenize`/`parse_units` (and `free_form_input` to the engine) | `F66` (default, ANSI) vs `F77` (ANSI X3.9-1978) vs `FORTRAN10` (DEC superset) |
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

## Intrinsics vs. library builtins

Two distinct tables:

- **`INTRINSICS`** (in `intrinsics.py`) — the FORTRAN intrinsic *functions* (`INT`, `SQRT`,
  `MOD`, `ABS`, `LSH`, the `C*` complex ops, …), evaluated inline via `_apply_intrinsic`. Pure
  value→value lambdas, gated in three tiers by the dialect: `_F66_INTRINSICS` (always
  available), `_F77_INTRINSICS` (the ANSI F77 additions — generic `LOG`/`MAX`, `TAN`/`ASIN`,
  the `D…` specifics, `LEN`/`CHAR`/…; flag `f77_intrinsics`, on for F77 and FORTRAN10), and
  `_DEC_INTRINSICS` (DEC-only — `LSH`/`ROT`, degree-trig, the `DOUBLE COMPLEX` helpers; flag
  `dec_library`, FORTRAN10 only).
- **`STDLIB`** (in `forlib.py`) — the DEC library *subroutines* (`TIME`, `DATE`, `EXIT`,
  `ERRSNS`/`ERRSET`, `RAN`/`SETRAN`, sense-light ops, …), registered via `register_builtins`
  when `dec_library` is on. The TOPS-10 monitor UUOs (`OUTSTR`/`SLEEP`/…, `UUOLIB` in
  `uuolib.py`) are a separate tier gated on `uuo_library` — so strict F77 gets neither. These
  take `(eng, frame, arg_nodes)` so they can touch engine state and write back through refs.

> **Target-awareness (done):** the integer-valued intrinsics follow the engine's `Target`
> — `_apply_intrinsic` re-applies `self.tgt.wrap` to `INT`/`IFIX`/`IDINT`/`NINT` results,
> and `_lsh` takes the target (shift width from `tgt.mask`). The math/`C*` intrinsics are
> pure value→value and target-neutral. The whole value model — integer wrap, the logical
> algebra, the character codec, the `O`-descriptor width, and Hollerith `PARAMETER`
> constants (packed at use via `Engine._const_value`, not at parse time) — now routes
> through the `Target`; there are no known PDP-10 pins left in the core.

### Host-routine marshalling (`hostlib`) — the decorator pattern

`INTRINSICS` and `STDLIB` are forterp's *own* routines. A third category is the routines the
**host** supplies: the geometry/bit-packing/pathfinding helpers and "system calls" the
programs of this era kept in hand-written assembly and `CALL`ed. `forterp.hostlib` is the
authoring layer for those. The user-facing how-to is in the [host routines](06-host-routines.md); this section is
how it is *built*, because the mechanism — a decorator that rewrites a function's calling
convention from a tuple of declared modes — is a small worked example of a few Python features
worth naming.

**The pieces of the mechanism:**

- **A decorator** is just a function that takes a function and returns a replacement.
  `@fcall("IDIST", args=(INT, INT))` is the call `fcall("IDIST", args=(INT, INT))`
  returning the real decorator `deco`, which is then applied to the body: `idist = deco(idist)`.
  So `deco` gets the clean body and returns the uniform `fn(eng, frame, arg_nodes)` callable
  the engine actually dispatches.
- **The modes are values, not type annotations.** `IN`/`INT`/`OUT`/`ARRAY`/… are *instances*
  of small `Mode` classes, passed in the `args=` tuple. Each has one method, `bind(eng, frame,
  node) -> value-or-handle`, that turns one actual-argument AST node into what the body should
  receive — `INT` does `int(eng.eval(node, frame))`, `OUT` wraps `eng.arg_ref(node, frame)` in
  an `OutRef`. New host-specific modes are new `Mode` subclasses (`STR` is one — it knows the
  target's char codec). This is deliberately *not* Python's `def f(a: int)` annotation syntax:
  a mode carries behavior (the bind step), and one parameter can need a handle rather than a
  value, which a type annotation can't express.
- **The generated wrapper** closes over the mode tuple and the body. On each call it binds
  every actual through its mode and splats the results into the body
  (`fn(*bound)`); `raw=True` skips all of this and returns the body unchanged (it *is* already
  the uniform callable). The body's return value propagates — used by the function-reference
  dispatch path, ignored by `CALL` — which is why one decorator serves both functions and
  subroutines.
- **Attributes on a function.** Functions are objects, so the wrapper carries its metadata as
  plain attributes: `builtin_name`, `builtin_aliases`, `builtin_origin`, and `fcall_fn` (the
  original documented body, kept reachable for introspection). `builtins_in(module)` discovers
  routines by reading `builtin_name` off every module global — no registration list to keep in
  sync, which is what lets a `.py` file drop in beside FORTRAN source.

`@fcall` is literally `fcall = builtin` (an alias chosen to read right next to PDP-10 source).
`@uuo` is the same shape with one addition: its wrapper injects `monitor(eng)` as the
body's first argument before the marshalled actuals (or before `(eng, frame, arg_nodes)` when
`raw=True`). That facade is the one piece of *state* the layer owns — see §6's environment
seams; it reads `eng.emit`/`eng.clock`/`eng.root` and nothing OS-level, and an embedder can
inject a richer subclass via `eng.monitor`.

The whole module is ~120 lines of marshalling and ~80 of facade. The payoff is that a host
body is the logic and nothing else, and the messy minority that needs the AST stays in the
*same* registry behind `raw=True` rather than forking a second, lower-level convention.

---

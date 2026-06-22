# forterp Python API examples

Short, runnable Python scripts showing how to use **forterp as a library** — parsing
and running FORTRAN from your own code, capturing output, feeding input, choosing a
dialect or machine value model, and reading results back.

(For example *FORTRAN programs* to run through the interpreter, see [`../demos/`](../demos/).)

After `pip install -e .` from the repo root (or with `PYTHONPATH=src`), run any of them:

```sh
python examples/run_and_capture.py
```

| Script | Shows |
|--------|-------|
| [`run_and_capture.py`](run_and_capture.py) | The minimal call: `run_source(text, printer=...)` to run a program and capture what it prints. |
| [`dialects.py`](dialects.py) | `F66` (strict ANSI, default) vs `FORTRAN10` (DEC superset); collecting diagnostics with an `on_error` callback instead of raising. |
| [`targets.py`](targets.py) | The pluggable value model — the same integer overflow on the 64-bit `NATIVE` word vs a 36-bit `PDP10` word. |
| [`fortran_as_kernel.py`](fortran_as_kernel.py) | Driving a routine as a compute kernel: feed input via `readline`, read results straight out of `eng.commons[...]`. |
| [`parse_and_inspect.py`](parse_and_inspect.py) | Parsing without running — `parse_source` returns a `{name: ProgramUnit}` dict to inspect (kinds, names) for tooling. |

## The shape of the API

```python
import forterp

# Parse + run in one call; returns the Engine so you can inspect final state.
eng = forterp.run_source(
    source_text,
    program=None,                  # which PROGRAM to run (default: the first)
    dialect=forterp.FORTRAN10,     # forterp.F66 (default) or forterp.FORTRAN10
    target=forterp.PDP10,          # forterp.NATIVE (default), PDP10, or VAX
    printer=print, emit=print,     # line-printer / terminal output callbacks
    readline=input,                # input source for READ / ACCEPT
)

eng.commons["BLK"]                 # a COMMON block as a flat list of words

# Or parse only, to drive your own tooling:
units = forterp.parse_source(source_text, dialect=forterp.F66,
                             on_error=lambda stmt, msg: ...)  # else raises ParseError
```

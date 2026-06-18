# pyf66

A **configurable FORTRAN-66 interpreter** in Python: the machine value model and the
front-end dialect are both pluggable, so one core runs FORTRAN against whatever
representation you select.

The value model is a `Target` — integer word width and overflow, the logical-truth
convention, and how characters pack into words. Two ship:

- **`NATIVE` (the default)** — a clean 64-bit host machine for running standard
  FORTRAN-66 portably: 64-bit two's-complement integers, 8-bit ASCII, `.TRUE.`=1 with
  boolean logical operators. `import f66; f66.run_source(...)` uses this.
- **`PDP10`** — the faithful DEC FORTRAN-10 model: 36-bit two's-complement words,
  5×7-bit packed character storage, `.TRUE.`=−1 with bit-wise logicals. Select with
  `Engine(..., target=f66.PDP10)`.

The PDP-10 target was extracted from an interpreter built to run the 1978 multiplayer
game *DECWAR* and Walter Bright's *Empire* unmodified, so it is exercised against real,
gnarly period code — not just toy snippets — and validated against the DEC FORTRAN-10
V5 manual and the ANSI **FCVS** conformance corpus.

## Install

```sh
pip install pyf66          # (once published)
# or, from a checkout:
pip install -e .
```

## Quick start

```python
import f66

eng = f66.run_source('''      PROGRAM HELLO
          WRITE(6,10)
     10   FORMAT(' HELLO, WORLD')
          END
''', printer=print)
```

Lower-level building blocks:

```python
units = f66.parse_source(src)         # {name: ProgramUnit}
eng   = f66.make_engine(units)        # Engine with the FORTRAN-10 runtime installed
eng.run(f66.Frame(eng.rts["MAIN"], {}))
```

## What's pluggable

- **Machine target** — `f66.Target(word_bits, chars_per_word, logical_true, bitwise_logic,
  bits_per_char)` fixes the value model. `f66.NATIVE` (64-bit, 8-bit ASCII, boolean
  logicals) is the default; `f66.PDP10` (36-bit, 5×7-bit packed, `.TRUE.`=−1, bit-wise
  logicals) is the faithful DEC target. Pass `Engine(..., target=...)`.
- **Front-end dialect** — `f66.FORTRAN10` (DEC extensions on) vs `f66.STRICT_F66`
  (ANSI). Threaded through the source reader and lexer.
- **OPEN devices** — `eng.register_device(name, handler)` plugs in special devices.
- **Unformatted I/O codec** — `f66.install_runtime(eng)` wires the FOROTS binary-record +
  DEC-10 float codec used by binary `READ`/`WRITE`.

## Supported language

Standard FORTRAN-66 (arithmetic/logical/relational expressions, the full control-flow
set, `DO` loops with F66 one-trip semantics, `COMMON`/`EQUIVALENCE` storage association,
`DATA`, subprograms + `ENTRY`, statement functions), formatted + list-directed +
unformatted I/O with the complete `FORMAT` edit-descriptor set, `ENCODE`/`DECODE`, and
the DEC FORTRAN-10 extensions (octal literals, Hollerith, `IAND`/`IOR`/shift intrinsics,
tab-format source, random-access `READ(u'r)`). See [`docs/`](docs/).

## Tests

```sh
pip install -e ".[dev]"
pytest
```

The suite is the interpreter's unit tests plus the **FCVS** (FORTRAN Compiler Validation
System) conformance corpus — the standard-conformance audits — exercised through the
real source-reader → lexer → parser → engine pipeline.

## License

MIT © Nicholas J. Kisseberth. See [LICENSE](LICENSE).

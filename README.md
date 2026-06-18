# pyf66

A faithful **FORTRAN-66 / DEC FORTRAN-10** interpreter in Python.

`pyf66` runs 1970s FORTRAN the way a PDP-10 did: the machine value model (36-bit
words, SIXBIT / 7-bit-packed character storage, `.TRUE.`=-1) and the front-end dialect
(octal `"nnn` literals, `nH` Hollerith, tab-format source) are both first-class and
**pluggable**, with PDP-10 / FORTRAN-10 as the default, shipped target.

It was extracted from an interpreter built to run the 1978 multiplayer game *DECWAR*
and Walter Bright's *Empire* unmodified, so it is exercised against real, gnarly
period code — not just toy snippets.

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

- **Machine target** — `f66.Target(word_bits, chars_per_word, logical_true)`; `f66.PDP10`
  is the default (36-bit, 5 chars/word, `.TRUE.`=-1). Pass `Engine(..., target=...)` to
  change the representation.
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

# Getting started

`forterp` is usable as a library: parse and run FORTRAN from Python, inspect the result,
swap the value model or dialect, embed the engine in a host program, or instrument it. The
package root exposes a focused surface; deeper machinery lives in explicit namespaces.

## The public surface

`import forterp` gives exactly these names (everything else is in a namespace, below):

| Name | What |
|------|------|
| `run_source(text, …)` | parse + run a source string; returns the `Engine` |
| `parse_source(text, …)` | parse → `{name: ProgramUnit}` (raises `ParseError`) |
| `f66`, `fortran10`, `f77` | prebuilt, ready-to-run interpreters |
| `Interpreter` | roll your own (target + dialect + runtime) |
| `F66`, `FORTRAN10`, `F77`, `Dialect` | the front-end dialect axis |
| `NATIVE`, `PDP10`, `LP64LE`, `VAX`, `Target` | the machine value-model axis |
| `ParseError`, `SourceOptions` | the parse error; source-recovery options |

## Run and inspect

`run_source` returns the `Engine`, so you read results out of it after the run. By
convention, programs write results into a `COMMON` block, which the engine exposes as a flat
list of words:

```python
import forterp

src = """      PROGRAM T
      COMMON /OUT/ V(40)
      V(1) = 2 ** 10
      END
"""
eng = forterp.run_source(src, dialect=forterp.FORTRAN10)
print(eng.commons["OUT"][0])        # 1024
```

`run_source(text, program=None, dialect=F66, options=None, include_dir=".", **kwargs)`:
`program` picks the main unit (default: the first); `dialect` is `F77` (default),
`FORTRAN10`, or `F77`; `include_dir` is where `INCLUDE` resolves; extra `**kwargs` pass through to the
`Engine` (see [Embedding](04-running-embedding.md#embedding-and-io)).

`parse_source(text, dialect=F66, on_error=None, options=None, include_dir=".")` parses
without running and returns `{name: ProgramUnit}`. It raises `ParseError` (with every
diagnostic in the message) unless you pass `on_error(statement, message)`, which receives
each diagnostic and keeps the partial result.
